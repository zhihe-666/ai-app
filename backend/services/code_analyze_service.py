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
        if os.path.exists(self.snapshot_path):
            try:
                with open(self.snapshot_path) as f:
                    snapshot = json.load(f)
                generated_at = datetime.fromisoformat(snapshot["generatedAt"])
                if (datetime.now() - generated_at).days < 3:
                    return
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
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
            group_prompt = """你是 Algorithm Monorepo 项目的代码变更分析师。项目是机器学习模型训练与管理平台。

请为以下**一个**代码变更 Feature Group 生成业务描述。

**输入：**
- type: 变更类型（NEW_FEATURE=新增, FEATURE_MODIFY=修改, STYLE_ONLY=样式, 等）
- files: 涉及的文件列表
- signals: AST 信号类型列表
- commit_messages: 本次迭代的 commit 信息
- file_content: 变更后版本的文件内容（含行号，供参考上下文）

**输出格式：** 仅输出一个 JSON 对象，不要包含其他内容：
{
  "category": "10字以内概括，如"PS服务类型支持"、"队列选择优化"，以"新增"/"修改"/"下线"/"调整"等动词开头",
  "description": "详细描述（100-200字），在{文件}中做了什么、为什么、具体字段名/状态码",
  "type": "NEW_FEATURE | FEATURE_MODIFY | STYLE_ONLY | ..."
}

**type 修正规则：**
1. type 默认等于输入中的 AST type，先判断是否合理
2. 有明确证据时才修正。STYLE_ONLY→FEATURE_MODIFY 允许（如通过样式实现权限控制）
3. 禁止 STYLE_ONLY→NEW_FEATURE。禁止随意提升级别。
4. 如果 category 以"新增"或"新建"开头，type 必须为 NEW_FEATURE，不可归入其他类别

**描述规则：**
1. 必须提及具体字段名、状态码、文件名
2. 禁止"优化了代码"、"完善了功能"等模糊词汇
3. 如果是 STYLE_ONLY/UI 类，简要描述样式或交互变更即可"""

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
                        llm_type = result.get("type") or fg.get("type", "UNKNOWN")

                        # Code-level override: category starts with 新增/新建 → NEW_FEATURE
                        if category.startswith("新增") or category.startswith("新建"):
                            llm_type = "NEW_FEATURE"
                        elif category.startswith("移除") or category.startswith("删除"):
                            llm_type = "FEATURE_REMOVAL"

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
                        return {"category": fallback_name, "description": str(e), "type": fg.get("type", "UNKNOWN")}

            # Run per-group LLM calls in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(describe_group, fg) for fg in feature_groups]
                results = [f.result(timeout=120) for f in futures]

            # Build output from AST categories + LLM descriptions
            new_features = []
            modified_features = []
            removed_features = []
            ui_updates = []

            for fg, desc_result in zip(feature_groups, results):
                # Use LLM's type if provided, fallback to AST type
                gtype = desc_result.get("type") or fg.get("type", "UNKNOWN")
                confidence = fg.get("confidence", 0.5)
                files = [f.get("path") if isinstance(f, dict) else f for f in (fg.get("files") or [])]
                name = desc_result.get("category") or ""
                desc = desc_result.get("description") or ""

                # If LLM returned empty category, use file-based fallback name
                if not name:
                    name = files[0].split('/')[-1].replace('.tsx', '').replace('.ts', '') if files else "未知变更"

                if gtype in ("NEW_FEATURE",):
                    new_features.append({
                        "name": name,
                        "description": desc,
                        "confidence": float(confidence),
                        "evidence_files": files,
                        "user_visible": True,
                    })
                elif gtype in ("FEATURE_MODIFY", "INFRA_CHANGE", "UI_INTERACTION"):
                    modified_features.append({
                        "name": name,
                        "description": desc,
                        "confidence": float(confidence),
                        "evidence_files": files,
                        "user_visible": False,
                    })
                elif gtype in ("FEATURE_REMOVAL",):
                    removed_features.append({
                        "name": name,
                        "description": desc,
                        "evidence_files": files,
                    })
                else:
                    # STYLE_ONLY, UNKNOWN → UI updates
                    ui_updates.append(name or f"{gtype} - {files[0].split('/')[-1] if files else 'unknown'}")

            llm_result = {
                "new_features": new_features,
                "modified_features": modified_features,
                "removed_features": removed_features,
                "ui_updates": ui_updates,
                "summary": {
                    "functional_changes": len(new_features) + len(modified_features) + len(removed_features),
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
        new_features = []
        modified = []
        removed_list = []
        ui_updates = []

        for g in groups:
            gtype = g.get("type", "UNKNOWN")
            files = g.get("files", [])
            evidence = [f.get("path", f) if isinstance(f, dict) else f for f in files]
            signals = g.get("allSignals", [])

            # Build a descriptive name from signals + file count
            file_names = [ef.split('/')[-1] for ef in evidence[:3]]
            name = f"{gtype} - {', '.join(file_names)}"

            if gtype in ("NEW_FEATURE",):
                new_features.append({"name": name, "evidence_files": evidence, "confidence": 0.5})
            elif gtype in ("FEATURE_MODIFY",):
                modified.append({"name": name, "evidence_files": evidence, "confidence": 0.5})
            elif gtype in ("FEATURE_REMOVAL",):
                removed_list.append({"name": name, "evidence_files": evidence, "description": ""})
            else:
                ui_updates.append(name)

        return {
            "new_features": new_features,
            "modified_features": modified,
            "removed_features": removed_list,
            "ui_updates": ui_updates,
            "summary": {
                "functional_changes": len(new_features) + len(modified) + len(removed_list),
                "ui_changes": len(ui_updates),
                "analyzed_files": ast_result.get("summary", {}).get("totalChangedFiles", 0),
                "feature_groups": len(groups),
            },
        }


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