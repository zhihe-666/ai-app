# backend/services/code_analyze_service.py

import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from services.llm_client import LLMClient
from services.db import get_commit_cache, save_commit_cache

GIT_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data/git-cache')
SNAPSHOT_FILE = "knowledge_snapshot.json"
CLI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'tools/code-analyzer')

# Default repo for backward compatibility
_DEFAULT_REPO_URL = "https://gitlab.shizhuang-inc.com/du-monorepo/algorithm-monorepo.git"
_DEFAULT_BRANCH = "master"


class CodeAnalyzeService:
    """Orchestrator for code change analysis lifecycle."""

    def __init__(self):
        self.task_id = None
        self.base_worktree = None
        self.target_worktree = None
        self.bare_repo_path = None
        self.snapshot_path = None
        self.task_dir = None

    def _sanitize_task_id(self, raw: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_-]', '_', raw)

    # ---- SSE emit helpers (these ARE generators) ----

    def _emit_progress(self, step: str, message: str, percentage: int,
                       step_index: int = 0, total_steps: int = 8):
        yield f"event: progress\ndata: {json.dumps({
            'step': step, 'step_index': step_index, 'total_steps': total_steps,
            'message': message, 'percentage': percentage
        })}\n\n"

    def _emit_section_complete(self, section: str, message: str, **extra):
        data = {'section': section, 'message': message, **extra}
        yield f"event: section_complete\ndata: {json.dumps(data)}\n\n"

    def _emit_error(self, error: str):
        yield f"event: error\ndata: {json.dumps({'error': error})}\n\n"

    def _emit_complete(self, result: dict):
        yield f"event: complete\ndata: {json.dumps(result)}\n\n"

    # ---- Main orchestrator (generator: yields SSE events) ----

    def analyze(self, repo_url: str, branch: str, frontend_paths: list[str],
                start_time: str, end_time: str, git_token: str = ""):
        self.task_id = self._sanitize_task_id(str(uuid.uuid4()))
        self.task_dir = f"/tmp/analyze_{self.task_id}"
        self.base_worktree = f"{self.task_dir}_base"
        self.target_worktree = f"{self.task_dir}_target"
        self.snapshot_path = f"{self.task_dir}/{SNAPSHOT_FILE}"

        if not repo_url:
            repo_url = _DEFAULT_REPO_URL
        if not branch:
            branch = _DEFAULT_BRANCH

        # Save original URL for cache key (before token injection)
        cache_key_url = repo_url

        # Inject git token into URL for authentication
        if git_token and 'oauth2:' not in repo_url:
            # Insert oauth2:token before host
            if '://' in repo_url:
                protocol, rest = repo_url.split('://', 1)
                repo_url = f"{protocol}://oauth2:{git_token}@{rest}"

        repo_name = self._extract_repo_name(repo_url)
        self.bare_repo_path = f"{GIT_CACHE_DIR}/{repo_name}.git"
        self.frontend_paths = frontend_paths
        self.repo_url = cache_key_url
        os.makedirs(self.task_dir, exist_ok=True)

        try:
            yield from self._emit_progress("git_fetch", "拉取远程仓库...", 10, 1, 8)
            self._git_fetch(repo_url)

            yield from self._emit_progress("resolve_commits", "定位时间段 commits...", 20, 2, 8)
            base, target = self._resolve_commits(branch, start_time, end_time)

            yield from self._emit_progress("commit_messages", "收集 commit 信息...", 30, 3, 8)
            commit_messages = self._collect_commit_messages(base, target, frontend_paths)

            yield from self._emit_progress("checkout", "检出双版本代码...", 40, 4, 8)
            self._checkout_worktree(base, target)

            yield from self._emit_progress("snapshot", "生成知识快照...", 50, 5, 8)
            self._ensure_knowledge_snapshot()

            yield from self._emit_progress("diff", "生成 diff...", 60, 6, 8)
            diff_dir = f"{self.task_dir}/diff"
            self._generate_diff(base, target, frontend_paths, diff_dir)
            changed_count = self._count_changed_files(diff_dir)
            yield from self._emit_section_complete("diff", "Git diff 完成",
                                                    changed_files=changed_count)

            yield from self._emit_progress("ast", "正在执行 AST 信号提取...", 70, 7, 8)
            self._run_ast_analysis(diff_dir)

            result_file = f"{self.task_dir}/result.json"
            with open(result_file) as f:
                ast_result = json.load(f)
            yield from self._emit_section_complete("ast",
                "AST 分析完成", feature_groups=len(ast_result.get("featureGroups", [])))

            yield from self._emit_progress("llm", "LLM 正在归纳变更...", 85, 8, 8)
            snapshot = self._load_snapshot()
            yield from self._llm_summarize(ast_result, commit_messages, snapshot)

        except Exception as e:
            yield from self._emit_error(str(e))
        finally:
            self._preserve_debug_files()
            self._cleanup()

    def _preserve_debug_files(self):
        """Copy AST result.json and LLM response to persistent path before cleanup."""
        import shutil
        persist_dir = "/tmp/analyze_debug"
        os.makedirs(persist_dir, exist_ok=True)
        result_file = f"{self.task_dir}/result.json" if self.task_dir else None
        if result_file and os.path.exists(result_file):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(result_file, f"{persist_dir}/result_{ts}_{self.task_id}.json")
            print(f"[CodeAnalyze] AST result saved to {persist_dir}/result_{ts}_{self.task_id}.json")
        llm_debug = f"/tmp/llm_response_{self.task_id}.json"
        if os.path.exists(llm_debug):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(llm_debug, f"{persist_dir}/llm_response_{ts}_{self.task_id}.json")
            print(f"[CodeAnalyze] LLM response saved to {persist_dir}/llm_response_{ts}_{self.task_id}.json")

    # ---- Private helpers (NOT generators, called directly) ----

    def _extract_repo_name(self, repo_url: str) -> str:
        name = repo_url.rstrip('.git').split('/')[-1]
        return name

    def _git_fetch(self, repo_url: str):
        if not os.path.exists(self.bare_repo_path):
            os.makedirs(GIT_CACHE_DIR, exist_ok=True)
            result = subprocess.run(
                ["git", "clone", "--mirror", repo_url, self.bare_repo_path],
                cwd="/tmp", capture_output=True, text=True, timeout=600
            )
            if result.returncode != 0:
                raise RuntimeError(f"git clone failed: {result.stderr}")
        else:
            subprocess.run(
                ["git", "fetch", "--all", "--prune"],
                cwd=self.bare_repo_path, capture_output=True, text=True, timeout=120
            )

    def _resolve_commits(self, branch: str, start_time: str, end_time: str):
        # Check cache first — same repo + branch + time range = same commits
        cached = get_commit_cache(self.repo_url, branch, start_time, end_time)
        if cached:
            print(f"[CodeAnalyze] Using cached commits: {cached['base_commit'][:8]}..{cached['target_commit'][:8]}")
            return cached['base_commit'], cached['target_commit']

        base = subprocess.run(
            ["git", "rev-list", "-n", "1", "--before", start_time,
             f"refs/heads/{branch}"],
            cwd=self.bare_repo_path, capture_output=True, text=True, timeout=30
        ).stdout.strip()

        target = subprocess.run(
            ["git", "rev-list", "-n", "1", "--before", end_time,
             f"refs/heads/{branch}"],
            cwd=self.bare_repo_path, capture_output=True, text=True, timeout=30
        ).stdout.strip()

        if not base or not target:
            raise ValueError("指定时间段内无 commit")
        if base == target:
            raise ValueError("Base 和 Target 相同，时间段内无变更")

        # Persist cache for future runs
        save_commit_cache(self.repo_url, branch, start_time, end_time, base, target)
        return base, target

    def _collect_commit_messages(self, base: str, target: str,
                                  frontend_paths: list[str]) -> list[str]:
        result = subprocess.run(
            ["git", "log", "--format=%s", f"{base}..{target}", "--"] + frontend_paths,
            cwd=self.bare_repo_path, capture_output=True, text=True, timeout=30
        )
        return [line for line in result.stdout.strip().split('\n') if line]

    def _checkout_worktree(self, base: str, target: str):
        r1 = subprocess.run(
            ["git", "worktree", "add", self.base_worktree, base],
            cwd=self.bare_repo_path, capture_output=True, text=True, timeout=60
        )
        if r1.returncode != 0:
            raise RuntimeError(f"base worktree checkout failed: {r1.stderr}")
        r2 = subprocess.run(
            ["git", "worktree", "add", self.target_worktree, target],
            cwd=self.bare_repo_path, capture_output=True, text=True, timeout=60
        )
        if r2.returncode != 0:
            raise RuntimeError(f"target worktree checkout failed: {r2.stderr}")

    def _ensure_knowledge_snapshot(self):
        """每次分析都重新生成知识快照（5-15s，零 token 消耗）。"""
        self._generate_snapshot()

    def _generate_snapshot(self):
        cli_path = os.path.join(CLI_DIR, "dist/index.js")
        target_dir = self.target_worktree or ""
        output_path = self.snapshot_path or f"/tmp/{SNAPSHOT_FILE}"

        # Skip if no valid target directory (e.g. refresh-snapshot called independently)
        if not target_dir or not os.path.exists(target_dir):
            print("Warning: no valid target directory for snapshot generation")
            return

        result = subprocess.run(
            ["node", cli_path,
             "--target", target_dir,
             "--frontend-paths", ",".join(self._get_all_frontend_paths()),
             "--output", output_path,
             "--mode", "snapshot"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            print(f"Warning: snapshot generation failed: {result.stderr}")
        else:
            global _snapshot_cache
            try:
                with open(output_path) as f:
                    _snapshot_cache = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                pass

    def _generate_diff(self, base: str, target: str,
                        frontend_paths: list[str], diff_dir: str):
        os.makedirs(diff_dir, exist_ok=True)

        for fp in frontend_paths:
            safe_fp = fp.replace('/', '_')

            result = subprocess.run(
                ["git", "diff", "--name-status", "--find-renames=80%", base, target, "--", fp],
                cwd=self.bare_repo_path, capture_output=True, text=True, timeout=60
            )
            filtered_lines = [line for line in result.stdout.split('\n')
                             if line.strip() and not self._is_noise_file(line)]
            with open(f"{diff_dir}/{safe_fp}_name_status.txt", 'w') as f:
                f.write('\n'.join(filtered_lines))

            result = subprocess.run(
                ["git", "diff", "--numstat", "--find-renames=80%", base, target, "--", fp],
                cwd=self.bare_repo_path, capture_output=True, text=True, timeout=60
            )
            with open(f"{diff_dir}/{safe_fp}_numstat.txt", 'w') as f:
                f.write(result.stdout)

            result = subprocess.run(
                ["git", "diff", "--histogram", "--find-renames=80%", base, target, "--", fp],
                cwd=self.bare_repo_path, capture_output=True, text=True, timeout=60
            )
            filtered_patch = '\n'.join(
                line for line in result.stdout.split('\n')
                if not self._is_noise_path(line)
            )
            with open(f"{diff_dir}/{safe_fp}_patch.txt", 'w') as f:
                f.write(filtered_patch)

        with open(f"{diff_dir}/raw.patch", 'w') as out:
            for fp in frontend_paths:
                safe_fp = fp.replace('/', '_')
                pp = f"{diff_dir}/{safe_fp}_patch.txt"
                if os.path.exists(pp):
                    content = open(pp).read()
                    if content.strip():
                        out.write(content)
                        out.write('\n')

    NOISE_EXTENSIONS = frozenset({'.json', '.md', '.csv', '.log', '.svg', '.yaml', '.yml', '.html'})

    def _is_noise_file(self, line: str) -> bool:
        noise_patterns = [
            'node_modules', 'dist/', 'build/', 'coverage/', '__snapshots__/',
            '.map', '.min.js', 'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock',
            'plugin_exec_result.json',
        ]
        for pattern in noise_patterns:
            if pattern in line:
                return True
        # Filter non-code file extensions — extract path from status line
        # Format: "M\tpath/to/file.json"
        path_part = line.strip().split('\t')[-1]
        if any(path_part.endswith(ext) for ext in self.NOISE_EXTENSIONS):
            return True
        return False

    def _is_noise_path(self, line: str) -> bool:
        noise_patterns = [
            'node_modules', 'dist/', 'build/', 'coverage/', '__snapshots__/',
            '.map', '.min.js', 'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock',
            'plugin_exec_result.json',
        ]
        for pattern in noise_patterns:
            if pattern in line:
                return True
        # Filter non-code extensions in patch headers
        # Lines look like: "diff --git a/path/file.json b/path/file.json"
        # or "+++ b/path/file.json" / "--- a/path/file.json"
        raw = line.strip()
        for prefix in ['diff --git a/', '+++ b/', '--- a/']:
            if raw.startswith(prefix):
                path_part = raw[len(prefix):].split(' b/')[0]
                if any(path_part.endswith(ext) for ext in self.NOISE_EXTENSIONS):
                    return True
                break
        return False

    def _count_changed_files(self, diff_dir: str) -> int:
        total = 0
        for f in os.listdir(diff_dir):
            if f.endswith('_name_status.txt'):
                with open(f"{diff_dir}/{f}") as fh:
                    total += sum(1 for line in fh if line.strip())
        return total

    def _run_ast_analysis(self, diff_dir: str):
        cli_path = os.path.join(CLI_DIR, "dist/index.js")
        result = subprocess.run(
            ["node", cli_path,
             "--base", self.base_worktree,
             "--target", self.target_worktree,
             "--diff-dir", diff_dir,
             "--frontend-paths", ",".join(self._get_all_frontend_paths()),
             "--output", f"{self.task_dir}/result.json",
             "--mode", "analyze"],
            capture_output=True, text=True, timeout=180
        )
        if result.returncode != 0:
            raise RuntimeError(f"AST 分析失败: {result.stderr}")

    def _load_snapshot(self) -> dict:
        if os.path.exists(self.snapshot_path):
            with open(self.snapshot_path) as f:
                return json.load(f)
        return {}

    def _llm_summarize(self, ast_result: dict, commit_messages: list[str],
                        snapshot: dict):
        from flask import g

        # Skip LLM if no API key configured
        if not g.llm_config.get('api_key'):
            result = self._build_rule_based_result(ast_result)
            result["llm_status"] = "skipped"
            yield from self._emit_complete(result)
            return

        try:
            client = LLMClient(**g.llm_config)
            import concurrent.futures

            # Single comprehensive prompt per group (not two-step)
            # Format knowledge snapshot as compact context string
            snapshot_context = self._format_snapshot_context(snapshot)
            group_prompt = f"""你是 Algorithm Monorepo 项目的代码变更分析师。项目是机器学习模型训练与管理平台。

## 项目背景（知识快照）

{snapshot_context}

请为以下**一个**代码变更 Feature Group 生成业务描述。

**输入：**
- type: 变更类型（NEW_FEATURE=新增, FEATURE_MODIFY=修改, STYLE_ONLY=样式, 等）
- files: 涉及的文件列表
- signals: AST 信号类型列表
- commit_messages: 本次迭代的 commit 信息
- file_content: 变更后版本的文件内容（含行号，供参考上下文）

**输出格式：** 仅输出一个 JSON 对象，不要包含其他内容：
{{
  "category": "15字以内概括，如"PS服务类型支持"、"队列选择优化"，以"新增"/"修改"/"下线"/"调整"等动词开头",
  "description": "精炼的业务描述（50-150字），说明做了什么、为什么。**不要包含文件路径和代码定义**，用自然语言表达。",
  "type": "NEW_FEATURE | FEATURE_MODIFY | FEATURE_REMOVAL | STYLE_ONLY"
}}

**type 规则：**
- type 默认等于输入中的 AST type，**不要随意修改**
- 只有当你非常确信 AST 分类错误时才能修改 type
- 如果 category 以"新增"开头，type 必须为 NEW_FEATURE
- 如果 category 以"移除"开头，type 必须为 FEATURE_REMOVAL


**描述规则：**
1. 只描述业务功能，**不要包含文件路径、文件名、目录结构**
2. **不要包含代码中的变量名、函数名、参数名**等代码定义，用自然语言表达。如"首批次最大暂停秒数"而不是"首批次最大暂停秒数（resolveMaxFirstBatchPauseSeconds）"
3. 字数控制在 50-150 字
4. 语句要通顺完整，不能以"在"或"在...中"开头
5. 禁止"优化了代码"、"完善了功能"等模糊词汇
6. 如果是 STYLE_ONLY/UI 类，简要描述样式或交互变更即可"""

            feature_groups = ast_result.get("featureGroups", [])
            print(f"[CodeAnalyze] Per-group LLM call: {len(feature_groups)} groups")

            def _read_file_annotated(relative_path: str) -> str:
                """Read target version file with line numbers."""
                if not self.target_worktree:
                    return ""
                full_path = os.path.join(self.target_worktree, relative_path)
                if not os.path.exists(full_path):
                    return ""
                try:
                    lines = open(full_path, 'r', encoding='utf-8').readlines()
                    lines = lines[:50]
                    result = []
                    for i, line in enumerate(lines, 1):
                        result.append(f"{i}: {line.rstrip()}")
                    return '\n'.join(result)
                except Exception:
                    return ""

            # Use ThreadPoolExecutor to parallelize per-group calls
            def describe_group(fg: dict) -> dict:
                """Single LLM call for one group: output {category, description, type}."""
                nonlocal client, group_prompt, commit_messages
                files = [f.get("path") if isinstance(f, dict) else f for f in (fg.get("files") or [])]
                signals = fg.get("allSignals") or []

                # Read file content for context (first file, first 50 lines)
                file_content = ""
                if files:
                    file_content = _read_file_annotated(files[0])

                group_input = {
                    "type": fg.get("type"),
                    "files": files,
                    "signals": signals,
                    "commit_messages": commit_messages,
                    "file_content": file_content,
                }

                # Retry up to 2 times on failure
                for attempt in range(2):
                    try:
                        resp = client.chat(
                            system=group_prompt,
                            user=json.dumps(group_input, ensure_ascii=False),
                            temperature=0.0,
                            max_tokens=4096,
                            seed=42,
                        )
                        result = json.loads(resp)
                        if not isinstance(result, dict):
                            match = re.search(r'\{.*\}', resp, re.DOTALL)
                            result = json.loads(match.group()) if match else {}
                        category = result.get("category") or ""
                        description = result.get("description") or category
                        llm_type = result.get("type") or ""

                        return {
                            "category": category,
                            "description": description,
                            "type": llm_type,
                        }
                    except (json.JSONDecodeError, Exception) as e:
                        if attempt == 0:
                            continue
                        # Fallback: use file name as category
                        fallback_name = files[0].split('/')[-1].replace('.tsx', '').replace('.ts', '') if files else "未知"
                        return {"category": fallback_name, "description": str(e), "type": ""}

            # Run per-group LLM calls in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(describe_group, fg) for fg in feature_groups]
                results = [f.result(timeout=120) for f in futures]

            # 第一步：分类（不合并，先按 type 分到各个类别）
            functional_changes = []
            removed_features = []
            ui_updates = []

            for fg, desc_result in zip(feature_groups, results):
                # 分类优先级：LLM type > category 前缀 > AST type
                ast_type = fg.get("type", "UNKNOWN")
                llm_type = desc_result.get("type", "") or ""
                name = desc_result.get("category") or ""
                desc = desc_result.get("description") or ""

                if not name:
                    files_list = [f.get("path") if isinstance(f, dict) else f for f in (fg.get("files") or [])]
                    name = files_list[0].split('/')[-1].replace('.tsx', '').replace('.ts', '') if files_list else "未知变更"

                # 确定 gtype：category 前缀 > description 语义 > STYLE_ONLY 兜底 > LLM type > AST type
                if name.startswith("新增") or name.startswith("新建"):
                    gtype = "NEW_FEATURE"
                elif name.startswith("移除") or name.startswith("删除"):
                    gtype = "FEATURE_REMOVAL"
                elif "样式" in name or "样式" in desc:
                    gtype = "STYLE_ONLY"
                elif ast_type == "STYLE_ONLY":
                    gtype = "STYLE_ONLY"
                elif llm_type in ("NEW_FEATURE", "FEATURE_MODIFY", "FEATURE_REMOVAL"):
                    gtype = llm_type
                elif ast_type == "FEATURE_REMOVAL":
                    gtype = "FEATURE_REMOVAL"
                else:
                    gtype = ast_type

                confidence = fg.get("confidence", 0.5)
                files = [f.get("path") if isinstance(f, dict) else f for f in (fg.get("files") or [])]

                item = {
                    "name": name,
                    "description": desc,
                    "confidence": float(confidence),
                    "evidence_files": files,
                    "user_visible": True,
                }

                if gtype in ("NEW_FEATURE", "FEATURE_MODIFY", "INFRA_CHANGE", "UI_INTERACTION", "TEXT_CHANGE", "TYPE_CHANGE"):
                    functional_changes.append(item)
                elif gtype in ("FEATURE_REMOVAL",):
                    removed_features.append(item)
                else:
                    # 只有 STYLE_ONLY 和 UNKNOWN 归为 UI
                    ui_updates.append(name or f"{gtype} - {files[0].split('/')[-1] if files else 'unknown'}")

            # 第二步：过滤与平台功能无关的条目（常量/枚举/代码重构等）
            print(f"[CodeAnalyze] 过滤前: functional={len(functional_changes)}")
            functional_changes = self._filter_non_functional(functional_changes, client)
            print(f"[CodeAnalyze] 过滤后: functional={len(functional_changes)}")

            # 第三步：三大类各自合并去重
            print(f"[CodeAnalyze] 合并前: functional={len(functional_changes)}, removed={len(removed_features)}, ui={len(ui_updates)}")
            functional_changes = self._merge_similar_items(functional_changes, "functional", client)
            removed_features = self._merge_similar_items(removed_features, "removed", client)
            print(f"[CodeAnalyze] 合并后: functional={len(functional_changes)}, removed={len(removed_features)}")

            # 第三步：对合并结果批量打 user_visible 标签
            all_to_label = functional_changes + removed_features
            if all_to_label:
                labeled = self._label_visibility(all_to_label, client)
                if labeled and len(labeled) == len(all_to_label):
                    functional_changes = labeled[:len(functional_changes)]
                    removed_features = labeled[len(functional_changes):]

            llm_result = {
                "functional_changes": functional_changes,
                "removed_features": removed_features,
                "ui_updates": ui_updates,
                "summary": {
                    "functional_changes": len(functional_changes) + len(removed_features),
                    "ui_changes": len(ui_updates),
                    "analyzed_files": ast_result.get("summary", {}).get("totalChangedFiles", 0),
                    "feature_groups": len(feature_groups),
                },
                "llm_status": "success",
            }
            yield from self._emit_complete(llm_result)

        except concurrent.futures.TimeoutError:
            result = self._build_rule_based_result(ast_result)
            result["llm_status"] = "timeout"
            yield from self._emit_complete(result)
        except Exception as e:
            result = self._build_rule_based_result(ast_result)
            result["llm_status"] = "failed"
            result["llm_error"] = str(e)
            yield from self._emit_complete(result)

    def _build_rule_based_result(self, ast_result: dict) -> dict:
        groups = ast_result.get("featureGroups", [])
        functional = []
        removed_list = []
        ui_updates = []

        for g in groups:
            gtype = g.get("type", "UNKNOWN")
            files = g.get("files", [])
            evidence = [f.get("path", f) if isinstance(f, dict) else f for f in files]

            file_names = [ef.split('/')[-1] for ef in evidence[:3]]
            name = f"{gtype} - {', '.join(file_names)}"

            if gtype in ("NEW_FEATURE", "FEATURE_MODIFY", "INFRA_CHANGE", "UI_INTERACTION", "TEXT_CHANGE", "TYPE_CHANGE"):
                functional.append({"name": name, "evidence_files": evidence, "confidence": 0.5})
            elif gtype in ("FEATURE_REMOVAL",):
                removed_list.append({"name": name, "evidence_files": evidence, "description": ""})
            else:
                ui_updates.append(name)

        return {
            "functional_changes": functional,
            "removed_features": removed_list,
            "ui_updates": ui_updates,
            "summary": {
                "functional_changes": len(functional) + len(removed_list),
                "ui_changes": len(ui_updates),
                "analyzed_files": ast_result.get("summary", {}).get("totalChangedFiles", 0),
                "feature_groups": len(groups),
            },
        }


    def _format_snapshot_context(self, snapshot: dict) -> str:
        """Format knowledge snapshot as compact string for LLM prompt injection."""
        if not snapshot:
            return "（无项目上下文）"

        parts = []
        apps = snapshot.get("applications", [])
        for app in apps:
            name = app.get("name", "unknown")
            role = app.get("role", "")
            routes = app.get("routes", [])
            modules = app.get("modules", [])
            api_modules = app.get("apiModules", [])

            lines = [f"- 应用: {name} ({role})"]
            if routes:
                route_paths = [r.get("path", "") for r in routes if r.get("path")]
                lines.append(f"  路由: {', '.join(route_paths[:8])}")
                if len(route_paths) > 8:
                    lines[-1] += f" 等共{len(route_paths)}条"
            if modules:
                lines.append(f"  页面模块: {', '.join(modules)}")
            if api_modules:
                api_summary = [f"{m['name']}({len(m.get('endpoints',[]))}接口)" for m in api_modules]
                lines.append(f"  API 模块: {', '.join(api_summary)}")
            parts.append('\n'.join(lines))

        shared = snapshot.get("sharedPackages", [])
        if shared:
            sp_lines = []
            for pkg in shared:
                comps = pkg.get("components", [])
                sp_lines.append(f"- 共享包 {pkg.get('name','')}: {', '.join(comps[:10])}{'等' if len(comps)>10 else ''}")
            parts.append("共享包:\n" + '\n'.join(sp_lines))

        return '\n\n'.join(parts)


    def _merge_similar_items(self, items: list, category: str, client: LLMClient) -> list:
        """语义去重：LLM 直接输出去重精简后的结果列表。

        不依赖 LLM 选择"哪些合并"，而是要求 LLM 输出精简后的最终列表，
        迫使 LLM 自行判断哪些该合并。
        """
        if len(items) <= 1:
            return items

        entries = []
        for i, it in enumerate(items):
            name = it.get("name", "")
            desc = it.get("description", "")
            entries.append(f"{i+1}. {name} — {desc}")

        prompt = f"""以下是一次代码迭代中提取出的{len(entries)}个变更条目，其中有一些重复或高度相似的条目。

输入条目：
{chr(10).join(entries)}

请将这些条目**去重合并**为一份精简列表。输出严格 JSON（只输出 JSON 对象，不要其他内容）：

{{
  "items": [
    {{"name": "10字以内概括，动词开头", "description": "精炼描述（50-100字），说明做了什么"}}
  ]
}}

规则：
- 将描述同一功能模块、description相近或有重合的条目合并为一条，重点关注名称相近的条目
- 综合考虑 description 和名称判断，既不能漏掉相似条目，也不能误合并不同条目
- 多个描述同一功能的条目合并为一条，一个条目最多只能参与合并一次，避免合并后出现两个条目中存在重复的描述
- 合并后的 description 整合多条的核心信息，50-150 字，用自然语言表达
- 合并后的名称重新提炼，15 字以内，动词开头
- 合并后如果还有多个不同的条目，就输出多个"""
        try:
            resp = client.chat(system=prompt, user="", temperature=0.0, max_tokens=4096, seed=42)
            print(f"[CodeAnalyze] 合并响应前200字: {resp[:200]}")
            result = json.loads(resp)
            if not isinstance(result, dict):
                match = re.search(r'\[.*\]', resp, re.DOTALL)
                result = json.loads('[{"items":' + resp + '}]') if resp.startswith('[') else {}
            merged_list = result.get("items", [])

            if not merged_list:
                return items

            # 映射回原始 item 的元数据
            merged = []
            for merged_item in merged_list:
                merged_name = merged_item.get("name", "")
                merged_desc = merged_item.get("description", "")

                # 找原始 items 中名称最匹配的作为元数据基础
                best_match = items[0]
                best_score = 0
                for orig in items:
                    orig_name = orig.get("name", "")
                    # 简单前缀匹配
                    if merged_name and orig_name and merged_name[:4] == orig_name[:4]:
                        score = len(set(merged_name) & set(orig_name))
                        if score > best_score:
                            best_score = score
                            best_match = orig

                # 收集所有匹配原条目的 evidence_files 和 confidence
                all_files = list(best_match.get("evidence_files", []))
                max_conf = float(best_match.get("confidence", 0.5))
                for orig in items:
                    orig_name = orig.get("name", "")
                    if merged_name and orig_name and (merged_name[:4] == orig_name[:4] or orig_name[:4] in merged_name):
                        all_files.extend(orig.get("evidence_files", []))
                        try:
                            max_conf = max(max_conf, float(orig.get("confidence", 0)))
                        except (ValueError, TypeError):
                            pass

                # 去重 files
                seen_f = set()
                deduped_files = []
                for f in all_files:
                    if f not in seen_f:
                        seen_f.add(f)
                        deduped_files.append(f)

                merged.append({
                    "name": merged_name,
                    "description": merged_desc or best_match.get("description", ""),
                    "confidence": max_conf,
                    "evidence_files": deduped_files,
                    "user_visible": True,
                })

            if len(merged) < len(items):
                print(f"[CodeAnalyze] LLM合并: {len(items)} → {len(merged)} 条")
                return merged

            print(f"[CodeAnalyze] LLM 未合并，保留 {len(items)} 条")
            return items

        except (json.JSONDecodeError, Exception) as e:
            print(f"[CodeAnalyze] 语义合并失败 ({category}): {e}")
            return items


    def _label_visibility(self, items: list, client: LLMClient) -> list:
        """对合并后的结果批量打 user_visible 标签。"""
        if not items:
            return items

        entries = []
        for i, it in enumerate(items):
            name = it.get("name", "")
            desc = it.get("description", "")
            entries.append(f"{i+1}. {name} — {desc}")

        prompt = f"""以下是一次代码迭代的变更结果，请为每条结果判断用户可见程度。
输出严格 JSON：
{{"labels": [
  {{"index": 1, "user_visible": true}},
  {{"index": 2, "user_visible": false}}
]}}

条目：
{chr(10).join(entries)}

规则：
- true=用户可见（用户可直接感知的功能变化：新页面、新按钮、新功能入口、UI变化）
- false=用户不可见（纯后端逻辑、配置变更、基础设施调整）
- "partial"=部分可见（同一变更中既有前端可见也有后端不可见部分）"""
        try:
            resp = client.chat(system=prompt, user="", temperature=0.0, max_tokens=2048, seed=42)
            result = json.loads(resp)
            labels = result.get("labels", []) if isinstance(result, dict) else []
            if not labels:
                return items
            for label in labels:
                idx = label.get("index", 0) - 1
                if 0 <= idx < len(items):
                    items[idx]["user_visible"] = label.get("user_visible", True)
            return items
        except (json.JSONDecodeError, Exception) as e:
            print(f"[CodeAnalyze] 打标失败: {e}")
            return items


    def _filter_non_functional(self, items: list, client: LLMClient) -> list:
        """过滤与平台业务功能无关的条目（常量定义、枚举、代码重构、工具函数等）。"""
        if not items:
            return items

        entries = []
        for i, it in enumerate(items):
            name = it.get("name", "")
            desc = it.get("description", "")
            entries.append(f"{i+1}. {name} — {desc}")

        prompt = f"""以下是一次代码迭代中提取的变更条目，请根据描述判断每条属于哪一类。

条目：
{chr(10).join(entries)}

输出严格 JSON：
{{"keep": [1, 3], "filter": [2]}}

**分类标准：**

→ 应保留（keep）— 业务功能变更
条目的描述指向一个**具体的业务功能变化**，比如：
- 新增/修改了某个用户可操作的功能（页面、弹窗、按钮、列表、表单等）
- 新增/修改了某项业务逻辑（API调用、数据处理、状态管理、权限判断等）
- 新增/修改了某种交互行为（点击、跳转、筛选、排序、搜索等）
- 新增/修改了业务配置项、开关、策略等

→ 应过滤（filter）— 底层架构/基础设施修改
条目的描述指向**代码内部的技术调整**，对业务功能无直接影响，比如：
- 更新了底层数据结构或映射关系
- 新增了常量枚举、类型定义等纯代码层面的变更
- 重构了代码结构、提取公共方法、重命名等
- 调整了工具函数、纯数据转换逻辑
- 更新了注释、日志、格式化等非功能变更

**核心判断原则：** 看描述是否指向一个**具体的业务功能变化**。如果是就保留，如果只是代码层面的技术调整就过滤。拿不准时归入 keep。"""
        try:
            resp = client.chat(system=prompt, user="", temperature=0.0, max_tokens=2048, seed=42)
            result = json.loads(resp)
            keep = result.get("keep", []) if isinstance(result, dict) else []
            if not keep:
                return items
            kept = []
            for idx in keep:
                i = idx - 1
                if 0 <= i < len(items):
                    kept.append(items[i])
            if kept:
                filtered_count = len(items) - len(kept)
                print(f"[CodeAnalyze] 过滤非功能项: {filtered_count} 条")
                return kept
            return items
        except (json.JSONDecodeError, Exception) as e:
            print(f"[CodeAnalyze] 过滤失败: {e}")
            return items


    def _get_all_frontend_paths(self) -> list[str]:
        return self.frontend_paths if hasattr(self, 'frontend_paths') else [
            "apps/algorithm/ml-main",
            "apps/algorithm/ml-data",
            "apps/algorithm/_share",
        ]

    def _cleanup(self):
        for wt in [self.base_worktree, self.target_worktree]:
            if wt and os.path.exists(wt):
                subprocess.run(
                    ["git", "worktree", "remove", "--force", wt],
                    capture_output=True, text=True, timeout=30
                )
        if self.task_dir and os.path.exists(self.task_dir):
            shutil.rmtree(self.task_dir, ignore_errors=True)


_snapshot_cache: dict = {}

def get_snapshot_info() -> dict:
    return _snapshot_cache