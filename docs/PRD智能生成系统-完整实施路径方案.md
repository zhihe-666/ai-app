# PRD 智能生成系统 — 完整实施路径方案

> **关联文档**: `PRD智能生成系统方案.md`（完整方案）、`PRD智能生成系统 MVP 实施方案.md`（MVP 方案）
> **技术栈**: Flask + React 19 + TypeScript + Ant Design 6
> **知识库**: 无矩 2.0 FastAPI 微服务（:8000）/ drag MCP
> **当前状态**: MVP（简单模式 + 中等模式）已完成

---

## 一、现状总览

### 1.1 已实现功能（MVP Phase 1）

| 模块 | 功能 | 状态 |
|------|------|------|
| **简单模式** | 输入 → 大纲 → 自动逐章节流式生成 → 编辑/导出 | ✅ |
| **中等模式** | 7 话题问答 → 回顾审查屏 → 大纲 → 逐章节生成 → 编辑/导出 | ✅ |
| **输入层 A1** | 文字需求描述 | ✅ |
| **输入层 A2** | 飞书妙记链接解析（复用 `feishu_client`） | ✅ |
| **输入层 A3** | 文件上传（.md/.txt/.docx，临时/长期分类） | ✅ |
| **编辑器** | Markdown 渲染 + 内联编辑 + Diff 对比（react-diff-viewer-continued）+ 版本管理（3 版） | ✅ |
| **输出层** | Markdown 导出（Content-Disposition: attachment） | ✅ |
| **Prompt 体系** | Sr. PM persona + 9 章节 Prompt + 质量门禁 + 前序章节内容摘要注入 | ✅ |
| **话题推进** | 关键词强制推进 + 3 轮上限兜底 + 回顾审查屏 + 修改话题 | ✅ |
| **后端架构** | 13 个 API 端点 + 4 张 SQLite 表 + SSE 流式 + 5 层 JSON 容错 | ✅ |
| **前端架构** | 940 行 PrdGen.tsx 页面 + 完整 TypeScript 类型 + 零错误 | ✅ |

### 1.2 待实现功能（完整方案）

按完整方案文档，分为 3 个 Phase：

```
Phase 2a：知识基建（RAG + 飞书同步）    ← 当前优先级最高
Phase 2b：知识图谱（实体关系推理）
Phase 3： 深度模式（4 Agent + 编排引擎）
Phase 4： 原型生成（JSON Schema + 渲染引擎 + Spec 输出）
```

---

## 二、整体架构（最终目标）

```
┌─────────────────────────────────────────────────────────────────────┐
│                          交互层 (PrdGen.tsx)                        │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ 输入区   │ │ Q&A 区   │ │ 大纲区    │ │ 编辑器    │ │ 冲突面板 │  │
│  │ A1/A2/A3│ │ 流式对话  │ │ 章节触发  │ │ Diff/版本 │ │ 多源冲突 │  │
│  └─────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
┌──────────────────────────────────┴──────────────────────────────────┐
│                         处理层 (prd_gen_service.py)                  │
│                                                                    │
│  ┌──────┐  ┌──────────┐  ┌────────────────┐  ┌────────────────┐   │
│  │ 简单  │  │ 中等     │  │ 深度模式        │  │ 校验器矩阵      │   │
│  │ 模式  │  │ 模式     │  │ Agent 1→2→3→4  │  │ Schema/Scope/   │   │
│  │      │  │          │  │ LangGraph 编排   │  │ Citation/Accept │   │
│  └──────┘  └──────────┘  └────────────────┘  └────────────────┘   │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                   上下文组装                                  │  │
│  │  user_input + collected_info + minutes_extract               │  │
│  │  + 前序章节摘要 + RAG 参考片段 + 知识图谱影响范围              │  │
│  └──────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
┌──────────────────────────────────┴──────────────────────────────────┐
│                        知识层                                       │
│                                                                    │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐    │
│  │ 知识库（无矩2.0 RAG）   │  │ 知识图谱（NetworkX/Neo4j）       │    │
│  │  ├─ prd_history       │  │ 实体：功能/模块/接口/角色        │    │
│  │  ├─ 平台架构文档       │  │ 关系：依赖/影响/调用/包含       │    │
│  │  └─ 代码知识图谱       │  │ 推理：影响范围分析/缺失检测      │    │
│  └──────────────────────┘  └──────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 三、Phase 2a：知识基建（P0，预计 3 天）

### 概述

将历史 PRD 导入现有知识库，在 PRD 生成时实时检索最相关的历史片段作为 Few-shot 参考，同时补齐飞书文档同步能力。

### 前置条件确认（2026-07-10）

| # | 条件 | 状态 | 备注 |
|---|------|------|------|
| 1 | 历史 PRD 文档（约 15 份） | ⏳ 待提供 | 用户后续提供，放入 `docs/prd_history/` |
| 2 | 多模态 LLM API Key（图片→文字） | ⏳ 待提供 | 用于图片描述生成，建议 GPT-4o |
| 3 | 无矩 2.0 微服务（:8000） | ✅ 已确认运行 | 知识库检索/POST 导入均可用 |
| 4 | `prd_history` collection | ✅ 用户手动创建 | 导入脚本只负责写入内容 |
| 5 | 前端 RAG 开关 | ✅ 确认添加 | Checkbox 控制"参考历史 PRD"是否启用 |
| 6 | `lark-cli` 飞书文档权限 | ✅ 有权限 | 飞书文档同步可立即实施 |

### 与现有架构的关系

```
prd_gen_service.py
    │
    ├── _build_collected_info_text()  ← 增加 RAG 参考上下文注入
    │       │
    │       └── _retrieve_reference_context()
    │               │
    │               └── HTTP POST → 无矩2.0 /api/query/stream
    │                       │
    │                       └── collection: "prd_history"
    │
    └── export_to_feishu()
            │
            └── feishu_client.create_doc_xml()
```

### 3.1 历史 PRD 预处理（步骤 1）⏳ 依赖用户提供 PRD 文档 + LLM Key

#### 背景

现有十几个 PRD 文档，内含图片。需将图片转换为文字描述，确保入库质量。**当前状态：搁置，等待用户提供文档和 API Key。**

#### 实现方案

**新建** `backend/tools/preprocess_prd_docs.py`（独立工具脚本，不入生产代码）：

```python
"""
preprocess_prd_docs.py — 历史 PRD 预处理工具

用途：
  1. 读取 docs/ 目录下的 PRD markdown 文件
  2. 检测图片 markdown 语法 ![alt](path)
  3. 调用多模态 LLM 生成图片文字描述
  4. 替换图片为文字描述
  5. 输出处理后的纯文本版本

用法：
  python preprocess_prd_docs.py --input-dir docs/ --output-dir /tmp/prd_processed/
"""

import re
import base64
import os
from openai import OpenAI

def process_prd_file(filepath: str, client: OpenAI) -> str:
    """
    处理单份 PRD 文件：
    1. 读取原始内容
    2. 检测所有图片链接
    3. 对每张图片调用多模态 LLM 生成描述
    4. 替换图片为 [图片描述]
    5. 返回处理后的文本
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    def _describe_image(match):
        alt = match.group(1)
        img_path = match.group(2)
        # 读取图片 → base64 → 多模态 LLM
        if os.path.exists(img_path):
            with open(img_path, 'rb') as img_f:
                b64 = base64.b64encode(img_f.read()).decode()
            try:
                resp = client.chat.completions.create(
                    model="gpt-4o",  # 或其他支持多模态的模型
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请用一句话准确描述这张图片的内容，说明它在PRD文档中的作用。"},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                        ]
                    }],
                    max_tokens=200,
                )
                description = resp.choices[0].message.content
                return f'\n[图片：{alt} — {description}]\n'
            except Exception as e:
                return f'\n[图片：{alt} — （描述生成失败: {e}）]\n'
        return f'\n[图片：{alt} — （图片文件不存在: {img_path}）]\n'

    return re.sub(r'!\[(.*?)\]\((.*?)\)', _describe_image, content)
```

**操作流程：**

1. 收集所有历史 PRD 文档到 `docs/prd_history/` 目录
2. 运行脚本处理
3. 人工抽检 2-3 份，确认图片描述质量
4. 处理后的文件输出到 `/tmp/prd_processed/`

#### 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `backend/tools/preprocess_prd_docs.py` | 独立工具脚本，不入生产 |
| 新建 | `docs/prd_history/` | 存放原始历史 PRD 文档 |

---

### 3.2 导入知识库（步骤 2）⏳ 依赖步骤 1 完成

#### 方案

通过现有知识库管理 API 将处理后的 PRD 导入无矩2.0 知识库，集合名为 `prd_history`。**当前状态：搁置，依赖步骤 1 处理后的文档。**

> **注意：** `prd_history` collection 由用户手动创建，导入脚本只负责写入内容。

#### 执行脚本

```python
"""
import_prd_to_kb.py — 将处理后的 PRD 导入知识库

用法：
  python import_prd_to_kb.py --input-dir /tmp/prd_processed/
"""

import os
import json
import requests

KB_API = "http://localhost:8000/api/admin"
COLLECTION = "prd_history"

def import_prd(filepath: str):
    """导入单份 PRD 到知识库"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    filename = os.path.basename(filepath)
    title = filename.replace('.md', '')

    # 提取 metadata（从文件名或内容中提取功能名）
    feature = title.replace('PRD-', '').strip()

    resp = requests.post(
        f"{KB_API}/import",
        json={
            "content": content,
            "title": title,
            "collection": COLLECTION,
            "metadata": {
                "type": "prd_history",
                "feature": feature,
                "source": "ai_center_docs",
                "imported_at": "2026-07-08",
            }
        },
        timeout=30,
    )
    return resp.json()
```

#### 知识库集合结构

```
collection: "prd_history"
├── doc: "PRD-模型版本管理功能"
│   ├── content: 处理后的纯文本（图片已替换为描述）
│   └── metadata: {type: "prd_history", feature: "模型版本管理", ...}
├── doc: "PRD-训练任务调度优化"
│   ├── content: ...
│   └── metadata: {type: "prd_history", feature: "训练任务调度", ...}
├── doc: "PRD-... (共15份)"
│   └── ...
```

#### 验证方式

```bash
# 查看 collection 列表
curl http://localhost:8000/api/admin/collections

# 预期看到：
# {"status": "success", "data": {
#   "collections": [
#     {"name": "prd_history", "count": 15, "type": "manual_kb", ...}
#   ]
# }}
```

#### 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `backend/tools/import_prd_to_kb.py` | 独立工具脚本 |
| 无修改 | 现有知识库 API | 直接复用 |

---

### 3.3 PRD 生成时 RAG 检索注入（步骤 3，核心）✅ 可立即实施

#### 架构

```
prd_gen_service.py

generate_section(session_id, section)
    │
    ├── _build_collected_info_text(session)  ← 改为实例方法，新增 current_section 参数
    │
    ├── _retrieve_reference_context(session, section)  ← 新增
    │       │
    │       ├── 构建 query: 用户需求 + 章节名
    │       ├── POST /api/query/stream → 无矩2.0
    │       │       └── collections=["prd_history"]
    │       └── 返回格式化参考文本（前 3 个片段，各截断 500 字）
    │
    ├── _build_preceding_sections_text(session, section)  ← 已有
    │
    └── → 组装完整 Prompt 给 LLM
```

#### 新增方法

在 `PRDGenService` 类中新增 `_retrieve_reference_context()`。

```python
def _retrieve_reference_context(self, session: dict, current_section: str) -> str:
    """
    从知识库检索与当前 PRD 需求最相似的历史 PRD 片段。

    调用无矩2.0 知识库搜索 API /api/query/stream，
    获取最相关的前 3 个片段，注入 Prompt 作为 Few-shot 参考。

    返回格式：
        【参考历史PRD片段】
        参考1：「PRD-模型版本管理」
        ... 片段内容（截断 500 字）...

        参考2：「PRD-训练任务调度优化」
        ... 片段内容 ...

        ⚠️ 以上为历史PRD参考，当前PRD应基于实际需求设计，不要盲目照搬。
    """
    user_input = session.get('user_input', '') or ''
    section_name = _SECTION_NAMES.get(current_section, current_section)
    query = f"{user_input} {section_name}"[:200]  # 限制长度

    if not query.strip():
        return ''

    try:
        resp = requests.post(
            f"{KB_BASE_URL}/api/query/stream",
            json={
                "query": query,
                "collections": ["prd_history"],
                "top_k": 3,
                "similarity_threshold": 0.5,
                "page_size": 3,
            },
            timeout=15,
            stream=True,
        )

        # 解析 SSE 响应，提取 sources
        sources = []
        for line in resp.iter_lines():
            if not line:
                continue
            decoded = line.decode('utf-8', errors='ignore')
            if decoded.startswith('data: '):
                try:
                    data = json.loads(decoded[6:])
                    if data.get('type') == 'sources':
                        sources = data.get('sources', [])
                except json.JSONDecodeError:
                    continue

        if not sources:
            logger.info(f'[PRDGen] RAG 检索无结果: query="{query}"')
            return ''

        parts = ['【参考历史PRD片段】']
        for i, src in enumerate(sources[:3], 1):
            title = src.get('title', '未知PRD')
            content = src.get('content', '')[:500]
            score = src.get('score', '')
            parts.append(
                f'参考{i}：「{title}」'
                + (f' (相似度: {score:.2f})' if isinstance(score, (int, float)) else '')
                + f'\n{content}'
            )

        parts.append('')
        parts.append('参考以上历史PRD的写法，但当前PRD应基于实际需求设计，不要盲目照搬。')
        logger.info(f'[PRDGen] RAG 检索到 {len(sources)} 个参考片段')
        return '\n\n'.join(parts)

    except requests.exceptions.ConnectionError:
        logger.warning('[PRDGen] RAG 检索失败: 知识库服务未启动')
        return ''
    except Exception as e:
        logger.warning(f'[PRDGen] RAG 检索异常: {e}')
        return ''
```

#### 修改 `_build_collected_info_text`

将 `_build_collected_info_text` 从 `@staticmethod` 改为实例方法，新增 `current_section` 参数：

```python
def _build_collected_info_text(self, session: dict, current_section: str = '') -> str:
    """构建完整上下文（用户输入 + 问答收集 + 妙记提取 + RAG 参考）"""
    parts = []

    # 1. 用户原始输入（原有）
    user_input = session.get('user_input', '').strip()
    if user_input:
        parts.append(f'【用户原始需求】\n{user_input}')

    # 2. 问答阶段收集（原有）
    collected = json.loads(session.get('collected_info', '{}') or '{}')
    # ... 原有逻辑 ...

    # 3. 飞书妙记提取（原有）
    # ... 原有逻辑 ...

    # 4. RAG 参考上下文（新增）
    if current_section:
        rag_context = self._retrieve_reference_context(session, current_section)
        if rag_context:
            parts.append(rag_context)

    return '\n\n'.join(parts) if parts else '（暂无补充信息）'
```

#### 修改 `generate_section` 调用

```python
# 改前
collected_info = self._build_collected_info_text(session)

# 改后
collected_info = self._build_collected_info_text(session, current_section=section)
```

`simple_generate()` 和 `generate_section()` 均需修改。

#### 前端配置

在 `PrdGen.tsx` 新增开关，控制是否启用 RAG 参考。**默认开启**，关闭后不调用 `_retrieve_reference_context()`：

```tsx
// 新增状态
const [ragEnabled, setRagEnabled] = useState(true)

// 渲染 — 放在输入区域的配置栏目
<Checkbox checked={ragEnabled} onChange={e => setRagEnabled(e.target.checked)}>
  参考历史 PRD
</Checkbox>
```

后端接收 `rag_enabled` 参数，为 `false` 时跳过 RAG 检索。

#### 涉及文件

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `backend/services/prd_gen_service.py` | 新增 `_retrieve_reference_context()`，修改 `_build_collected_info_text()`，修改 `generate_section()` 和 `simple_generate()` 调用 |
| 修改 | `frontend/src/pages/PrdGen.tsx` | 新增"参考历史 PRD"开关 |
| 修改 | `frontend/src/api/prdGen.ts` | 传递 ragEnabled 参数 |

---

### 3.4 飞书文档同步（步骤 4）✅ 可立即实施

> **前置条件确认：** `lark-cli` 有创建文档权限，目标空间使用用户默认空间。

在 `PRDGenService` 中新增：

```python
def export_to_feishu(self, session_id: str, api_key: str, base_url: str, model: str) -> dict:
    """将生成的 PRD 写入飞书文档"""
    from .feishu_client import create_doc_xml

    session = self.get_session(session_id)
    if not session:
        return {'error': '会话不存在'}

    markdown = self.export_prd(session_id)
    if not markdown or markdown.startswith('# PRD'):
        return {'error': 'PRD 内容尚未生成'}

    # 提取标题
    user_input = session.get('user_input', '') or '未命名PRD'
    title = f"PRD-{user_input[:30]}"

    # 将 Markdown 简化为 XML（复用 feishu_client 的现有逻辑）
    # create_doc_xml 接受 title + content（markdown）
    result = create_doc_xml(title, markdown)
    if 'error' in result:
        return {'error': result['error']}

    # 保存文档 URL 到 session
    self.update_session(session_id, feishu_doc_url=result.get('url', ''))

    return {
        'url': result.get('url', ''),
        'title': title,
    }
```

#### 新增 API 端点

```python
@prd_gen_bp.route('/sessions/<id>/export/feishu', methods=['POST'])
def export_prd_to_feishu(id):
    """导出 PRD 到飞书文档"""
    cfg = _get_llm_config()
    if not cfg['api_key']:
        return {'error': '请先配置 LLM API Key'}, 400

    result = service.export_to_feishu(id, cfg['api_key'], cfg['base_url'], cfg['model'])
    if 'error' in result:
        return result, 400
    return result
```

#### 前端新增按钮

```tsx
{sessionStatus === 'done' && (
  <Button
    icon={<LinkOutlined />}
    onClick={async () => {
      try {
        const result = await exportPRDToFeishu(sessionId!)
        window.open(result.url, '_blank')
        message.success('飞书文档已创建')
      } catch (e: any) {
        message.error(e?.message || '导出失败')
      }
    }}
  >
    导出到飞书文档
  </Button>
)}
```

#### 涉及文件

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `backend/services/prd_gen_service.py` | 新增 `export_to_feishu()` |
| 修改 | `backend/routers/prd_gen.py` | 新增 `POST /sessions/{id}/export/feishu` 端点 |
| 修改 | `frontend/src/api/prdGen.ts` | 新增 `exportPRDToFeishu()` 函数 |
| 修改 | `frontend/src/pages/PrdGen.tsx` | 新增"导出到飞书文档"按钮 |

---

### Phase 2a 验证清单

| # | 验证项 | 验证方式 |
|---|--------|----------|
| 1 | 预处理后的 PRD 图片描述准确 | 人工抽检 2-3 份 |
| 2 | 知识库 `prd_history` 集合包含 15 份文档 | `GET /api/kb-manage/collections` |
| 3 | 生成 PRD 时日志输出 RAG 检索结果 | 后端日志 `[PRDGen] RAG 检索到 N 个参考片段` |
| 4 | 开启 RAG 时 Prompt 包含参考片段 | 在生成内容的完整性检查中确认 |
| 5 | 飞书文档导出成功，内容完整 | 点击导出 → 打开飞书文档 → 检查内容 |
| 6 | 关闭 RAG 开关时行为不变 | 关闭后生成，日志无 RAG 检索 |
| 7 | TypeScript 零错误 | `npx tsc --noEmit` |

### 实施优先级

| 步骤 | 内容 | 依赖 | 状态 |
|------|------|------|------|
| 3.3 | RAG 检索注入（核心代码改动） | 无 | ✅ **可立即实施** |
| 3.4 | 飞书文档同步 | 无 | ✅ **可立即实施** |
| 3.1 | 历史 PRD 预处理 | 用户提供文档 + LLM Key | ⏳ 搁置 |
| 3.2 | 导入知识库 | 步骤 3.1 完成 | ⏳ 搁置 |

---

## 四、Phase 2b：知识图谱初始化（P1，预计 4-5 天）

### 4.1 背景概念

#### PRD 知识图谱 vs 代码知识图谱

| 维度 | 代码知识图谱（已有） | PRD 业务知识图谱（新增） |
|------|---------------------|------------------------|
| 视角 | 代码视角（文件/组件/API） | 产品视角（功能/模块/业务规则） |
| 来源 | 代码仓库 AST 扫描 | PRD 文档 + 架构文档 |
| 实体 | `PageA.tsx`, `api/batchImport` | "模型版本管理", "灰度发布" |
| 关系 | import / 调用 / 继承 | 依赖 / 影响 / 包含 |
| 用途 | 代码变更影响范围 | 业务功能设计时的依赖和冲突 |

#### 两者关系

```
PRD 业务知识图谱（产品视角）
    ↑ 映射到（通过功能名匹配）
代码知识图谱（代码视角）
    ↑ 扫描
代码仓库（AST）
```

代码知识图谱可以辅助 PRD 知识图谱：当 PRD 提到"模型版本管理"时，代码知识图谱告诉你该功能对应的代码目录是 `apps/algorithm/ml-main/pages/ModelVersion/`。

### 4.2 图谱 Schema 定义

#### 实体类型

| 实体类型 | 标识 | 示例 | 来源 |
|---------|------|------|------|
| 业务功能 | `business_function` | "模型版本管理"、"灰度发布" | 历史 PRD |
| 平台模块 | `platform_module` | "模型训练模块"、"模型服务模块" | 架构文档 |
| 接口/API | `api_endpoint` | `TrainingService.submit` | 架构文档/代码扫描 |
| 数据实体 | `data_entity` | "模型版本(ModleVersion)" | 历史 PRD |
| 用户角色 | `user_role` | "算法工程师"、"平台管理员" | 历史 PRD |

#### 关系类型

| 关系类型 | 定义 | 示例 |
|---------|------|------|
| `depends_on` | 功能 A 依赖模块 B | "模型版本管理" → depends_on → "模型存储服务" |
| `affects` | 修改 A 会影响 B | "模型版本管理" → affects → "模型服务模块" |
| `calls` | 功能 A 调用接口 C | "模型版本管理" → calls → "ModelService.registerVersion" |
| `belongs_to` | 接口 C 属于模块 B | "ModelService.registerVersion" → belongs_to → "模型服务模块" |
| `uses` | 角色 R 使用功能 A | "算法工程师" → uses → "模型版本管理" |
| `similar_to` | 功能 A 与功能 E 相似 | "灰度发布" → similar_to → "A/B 测试" |

### 4.3 图谱构建流程

#### 步骤 1：从历史 PRD 提取实体关系

对每份历史 PRD，调用 LLM 提取结构化实体关系：

```python
_EXTRACT_GRAPH_PROMPT = """你是一个产品知识图谱分析师。请从以下 PRD 文档中提取实体和关系。

## 实体类型
- business_function: 业务功能（PRD 中描述的核心功能点）
- platform_module: 平台模块（功能依赖的已有平台模块）
- data_entity: 数据实体（功能涉及的核心数据模型）
- user_role: 用户角色（使用该功能的角色）

## 关系类型
- depends_on: 功能 A 依赖模块 B
- affects: 修改 A 会影响 B（跨模块影响）
- calls: 功能 A 调用接口 C
- uses: 角色 R 使用功能 A

## 输出格式（严格 JSON）
{
  "entities": [
    {"id": "model-version-mgmt", "name": "模型版本管理", "type": "business_function"},
    {"id": "model-storage", "name": "模型存储服务", "type": "platform_module"}
  ],
  "relations": [
    {"source": "model-version-mgmt", "target": "model-storage", "type": "depends_on"}
  ]
}

PRD 文档：
{prd_content}"""

def extract_graph_from_prd(prd_content: str, llm_client) -> dict:
    """从单份 PRD 提取实体关系"""
    resp = llm_client.chat(
        system=_EXTRACT_GRAPH_PROMPT,
        user=prd_content[:8000],  # 限制长度
    )
    result = parse_json_safe(resp, {'entities': [], 'relations': []})
    return result
```

#### 步骤 2：合并去重

所有 PRD 提取完成后，合并实体关系，去重同名实体：

```python
def merge_graphs(extractions: list[dict]) -> dict:
    """合并多份 PRD 的提取结果，去重同名实体"""
    all_entities = {}
    all_relations = []

    for ext in extractions:
        for ent in ext.get('entities', []):
            eid = ent.get('id', '')
            if eid and eid not in all_entities:
                all_entities[eid] = ent

        for rel in ext.get('relations', []):
            # 去重（相同 source+target+type 只保留一条）
            key = (rel.get('source'), rel.get('target'), rel.get('type'))
            if key not in {(r['source'], r['target'], r['type']) for r in all_relations}:
                all_relations.append(rel)

    return {
        'entities': list(all_entities.values()),
        'relations': all_relations,
    }
```

#### 步骤 3：存储与查询

初期使用 NetworkX（轻量，无需额外部署）：

```python
import networkx as nx

class PRDKnowledgeGraph:
    """PRD 业务知识图谱

    使用 NetworkX 存储实体关系，提供影响范围查询。
    """

    def __init__(self):
        self.graph = nx.DiGraph()

    def load_from_json(self, data: dict):
        """从 PRD 提取结果加载图谱"""
        for ent in data.get('entities', []):
            self.graph.add_node(ent['id'], **ent)
        for rel in data.get('relations', []):
            self.graph.add_edge(rel['source'], rel['target'],
                                relation=rel['type'])

    def query_impact(self, entity_id: str) -> list[dict]:
        """
        查询修改某个实体后会影响哪些下游实体。

        返回：
        [
            {"entity": "模型服务模块", "path": ["模型版本管理", "模型服务模块"], "hops": 1},
            {"entity": "灰度发布", "path": ["模型版本管理", "模型服务模块", "灰度发布"], "hops": 2}
        ]
        """
        if entity_id not in self.graph:
            return []

        results = []
        for target in nx.descendants(self.graph, entity_id):
            path = nx.shortest_path(self.graph, entity_id, target)
            results.append({
                'entity': self.graph.nodes[target].get('name', target),
                'path': [self.graph.nodes[n].get('name', n) for n in path],
                'hops': len(path) - 1,
            })
        return sorted(results, key=lambda r: r['hops'])
```

#### 步骤 4：与代码知识图谱对接

当你的代码知识图谱成熟后，在实体名上做映射：

```python
def map_to_code_entities(self, prd_entity_name: str, code_knowledge: dict) -> str:
    """
    将 PRD 业务实体映射到代码模块。

    示例：
      "模型版本管理" → "apps/algorithm/ml-main/pages/ModelVersion/"

    通过 LLM 或模糊匹配实现。
    """
    # 简单实现：通过代码知识图谱的应用名/模块名匹配
    for app in code_knowledge.get('applications', []):
        if prd_entity_name in app.get('name', '') or app.get('name', '') in prd_entity_name:
            return app.get('path', '')
    return ''
```

### 4.4 影响范围推理场景

有了图谱后，Agent 2（内部上下文分析 Agent）在深度模式中自动注入：

```
输入：当前功能 = "灰度发布"

图谱推理结果：
⚠️ 影响范围预警：
1. 「灰度发布」→ 依赖 → 「模型版本管理」（需要版本号来标识灰度版本）
2. 「灰度发布」→ 影响 → 「模型服务模块」（需要路由流量到灰度版本）
3. 「灰度发布」→ 影响 → 「监控告警模块」（灰度期间需要对比指标）

建议在 PRD 中覆盖：
- 版本号管理策略（如何标识灰度版本）
- 灰度流量路由规则
- 灰度期间监控指标对比
```

### 4.5 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `backend/services/knowledge_graph.py` | `PRDKnowledgeGraph` 类，NetworkX 封装 |
| 新建 | `backend/tools/extract_prd_graph.py` | 批量提取历史 PRD 实体关系 |
| 新建 | `backend/data/knowledge/prd_graph.json` | 图谱数据持久化文件 |
| 修改 | `backend/services/prd_gen_service.py` | 深度模式中注入图谱影响范围推理 |
| 修改 | `backend/requirements.txt` | 新增 `networkx` 依赖 |

---

## 五、Phase 3：深度模式与 Agent 编排（P2，预计 6-8 天）

### 5.1 深度模式 4 Agent 流水线

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Agent 1  │    │ Agent 2  │    │ Agent 3  │    │ Agent 4  │
│ 需求萃取  │ →  │ 上下文分析│ →  │ 功能规格  │ →  │ PRD 撰写  │
│ 协同模型  │    │ 强推理模型│    │ 强推理模型│    │ 协同模型  │
│          │    │          │    │          │    │          │
│ 输入：    │    │ 输入：    │    │ 输入：    │    │ 输入：    │
│ A1/A2/A3 │    │ Agent1出 │    │ Agent2出 │    │ Agent3出 │
│          │    │ + 图谱    │    │ + 校验器  │    │ + 模板    │
├──────────┤    ├──────────┤    ├──────────┤    ├──────────┤
│ 输出：    │    │ 输出：    │    │ 输出：    │    │ 输出：    │
│ 结构化    │    │ 影响范围  │    │ 功能规格  │    │ MD PRD + │
│ 需求信息  │    │ 分析报告  │    │ 书        │    │ Spec     │
│ + 冲突清单│    │ + 预警    │    │ + 验收标准│    │          │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
     │               │               │               │
     └───────────────┴───────────────┴───────────────┘
                         │
                    ┌────┴────┐
                    │ 校验器   │
                    │ 矩阵     │
                    │ 6 个校验 │
                    └─────────┘
```

### 5.2 Agent 职责定义

#### Agent 1：需求萃取与澄清智能体

| 属性 | 说明 |
|------|------|
| 调用模型 | 协同模型（DeepSeek-V4-flash） |
| 输入 | A1/A2/A3 任意组合 |
| 输出 | 结构化需求基础信息 + 补全信息 + 冲突清单 |
| 核心能力 | 多源信息融合、冲突检测、信息缺口识别 |

#### Agent 2：内部上下文分析智能体

| 属性 | 说明 |
|------|------|
| 调用模型 | 强推理模型（DeepSeek-V4-pro） |
| 输入 | Agent 1 输出 + 知识图谱 + 平台架构快照 |
| 输出 | 平台上下文分析报告 + 影响范围预警 |
| 核心能力 | 跨模块影响分析、缺失依赖检测 |

#### Agent 3：功能规格定义智能体

| 属性 | 说明 |
|------|------|
| 调用模型 | 强推理模型（DeepSeek-V4-pro） |
| 输入 | Agent 1 + Agent 2 输出 |
| 输出 | 结构化功能规格书（JSON Schema） |
| 核心能力 | 功能拆解、用户故事编写、验收标准定义 |

#### Agent 4：PRD 撰写与格式化智能体

| 属性 | 说明 |
|------|------|
| 调用模型 | 协同模型（DeepSeek-V4-flash） |
| 输入 | Agent 1/2/3 输出 + 模板 |
| 输出 | 最终 PRD Markdown + spec_schema.json |
| 核心能力 | 模板组装、润色、完整性校验 |

### 5.3 校验器矩阵

| 校验器 | 触发位置 | 检查内容 | 失败处理 |
|--------|---------|---------|---------|
| Schema Validator | Agent 1 之后 | 必填字段是否完整 | 回退 Agent 1 追问 |
| Scope Validator | Agent 3 之后 | 是否超范围（范围蔓延检测） | 标记超范围项，用户决定 |
| Citation Validator | Agent 3 之后 | 内容是否有依据（防幻觉） | 标注无依据内容 |
| Acceptance Validator | Agent 3 之后 | 功能点是否都有验收标准 | 回退 Agent 3 补充 |
| Permission Validator | Agent 3 之后 | 是否遗漏权限设计 | 提示补充 |
| Risk Validator | Agent 4 之后 | 是否缺失异常处理/性能/审计 | 标记缺失项 |

### 5.4 人工闸口

| 闸口 | 位置 | 触发条件 | 交互方式 |
|------|------|---------|---------|
| 冲突确认闸口 | Agent 1 之后 | 多源输入检测到语义冲突 | 冲突提示面板 |
| 影响范围确认闸口 | Agent 2 之后 | 输出影响范围预警 | 勾选确认 + 补充说明 |
| 功能规格确认闸口 | Agent 3 之后 | 校验器全部通过 | 逐项确认/修改/驳回 |

### 5.5 LangGraph 编排引擎

引入 LangGraph 状态图管理 Agent 流转：

```python
# 示意架构（非完整实现）
from langgraph.graph import StateGraph, END

class DeepModeState:
    """深度模式状态图的状态"""
    requirements: dict = {}      # Agent 1 输出
    context_analysis: dict = {}   # Agent 2 输出
    spec: dict = {}              # Agent 3 输出
    prd_markdown: str = ''       # Agent 4 输出
    validation_results: list = []
    user_approvals: dict = {}
    errors: list = []

# 构建状态图
workflow = StateGraph(DeepModeState)

workflow.add_node("agent1_extract", Agent1Node)
workflow.add_node("agent2_analyze", Agent2Node)
workflow.add_node("agent3_spec", Agent3Node)
workflow.add_node("agent4_write", Agent4Node)
workflow.add_node("human_review", HumanReviewNode)

workflow.add_edge("agent1_extract", "agent2_analyze")
workflow.add_edge("agent2_analyze", "human_review")  # 人工闸口
workflow.add_conditional_edges(
    "human_review",
    lambda state: "approved" if state.user_approvals.get("impact") else "rejected",
    {"approved": "agent3_spec", "rejected": "agent2_analyze"}
)
# ...
```

### 5.6 双模型路由

在 `llm_client.py` 基础上新增路由逻辑：

```python
class ModelRouter:
    """
    按模式/Agent 自动路由到合适的模型。

    配置：
        simple: flash
        medium: flash
        deep_agent_1: flash
        deep_agent_2: pro  (强推理)
        deep_agent_3: pro  (强推理)
        deep_agent_4: flash
    """

    MODEL_MAP = {
        'simple': 'deepseek-v4-flash',
        'medium': 'deepseek-v4-flash',
        'deep_agent_1': 'deepseek-v4-flash',
        'deep_agent_2': 'deepseek-v4-pro',    # 强推理
        'deep_agent_3': 'deepseek-v4-pro',    # 强推理
        'deep_agent_4': 'deepseek-v4-flash',
    }

    @classmethod
    def get_model(cls, route_key: str, user_model: str = '') -> str:
        """获取指定路由的模型"""
        if route_key in ('deep_agent_2', 'deep_agent_3'):
            return cls.MODEL_MAP[route_key]
        return user_model or cls.MODEL_MAP.get(route_key, 'deepseek-v4-flash')
```

### 5.7 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `backend/services/deep_agents.py` | 4 个 Agent 节点实现 |
| 新建 | `backend/services/validators.py` | 6 个校验器实现 |
| 新建 | `backend/services/model_router.py` | 双模型路由逻辑 |
| 修改 | `backend/services/prd_gen_service.py` | 深度模式入口 `deep_generate()` |
| 修改 | `backend/requirements.txt` | 新增 `langgraph`、`networkx` 依赖 |
| 修改 | `backend/routers/prd_gen.py` | 新增深度模式端点 |
| 修改 | `frontend/src/pages/PrdGen.tsx` | 新增深度模式 UI（模式选择 + 审批面板） |
| 修改 | `frontend/src/api/prdGen.ts` | 新增深度模式 API 函数 |

---

## 六、Phase 4：原型生成与研发闭环（P3，预计 8-10 天）

### 6.1 UI 组件库 JSON Schema 抽象

将平台现有 Ant Design 组件抽象为 JSON Schema 规范：

```json
{
  "component": "Table",
  "props": {
    "columns": [
      {"title": "模型名称", "dataIndex": "modelName", "key": "modelName"},
      {"title": "版本", "dataIndex": "version", "key": "version"},
      {"title": "状态", "dataIndex": "status", "key": "status"}
    ],
    "dataSource": [],
    "pagination": {"pageSize": 10}
  },
  "children": []
}
```

每个组件定义：
- 类型标识（component）
- 属性 Schema（props）
- 嵌套规则（children）
- 样式约束（style token）

### 6.2 动态渲染引擎

前端 Render Engine 读取 JSON Schema 递归渲染为真实页面：

```tsx
function RenderEngine({ schema }: { schema: ComponentSchema }) {
  const Component = COMPONENT_MAP[schema.component] || FallbackComponent

  // 递归渲染 children
  const children = schema.children?.map((child, i) => (
    <RenderEngine key={i} schema={child} />
  ))

  return <Component {...schema.props}>{children}</Component>
}
```

### 6.3 Machine-Readable Spec 双轨输出

Agent 4 同步输出 `spec_schema.json`，包含：

```json
{
  "feature": "模型版本管理功能",
  "version": "1.0",
  "endpoints": [
    {
      "path": "/api/model/register",
      "method": "POST",
      "auth": {"required": true, "roles": ["algorithm_engineer"]},
      "request": {
        "body": {
          "modelName": {"type": "string", "required": true, "maxLength": 64}
        }
      },
      "response": {
        "200": {"modelId": "string", "version": "string"},
        "400": {"error": "INVALID_ARTIFACT"}
      }
    }
  ],
  "dataModels": [
    {
      "name": "ModelVersion",
      "fields": [
        {"name": "modelId", "type": "string", "primaryKey": true}
      ]
    }
  ],
  "businessRules": [
    "同一模型仅允许一个版本处于production状态"
  ]
}
```

### 6.4 模板自动提取

定时扫描历史 PRD，统计高频章节结构，自动生成/更新模板。可复用 Phase 2a 已入库的知识库数据，无需额外文档收集。

### 6.5 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `backend/services/spec_generator.py` | Machine-Readable Spec 生成器 |
| 新建 | `frontend/src/components/RenderEngine.tsx` | JSON Schema 动态渲染引擎 |
| 新建 | `frontend/src/data/component_schema.json` | UI 组件库 Schema 定义 |
| 新建 | `backend/tools/extract_template.py` | 模板自动提取工具 |
| 修改 | `backend/services/prd_gen_service.py` | 深度模式 Agent 4 输出 Spec |
| 修改 | `frontend/src/pages/PrdGen.tsx` | 原型预览面板 |

---

## 七、实施路线图总览

### 7.1 阶段依赖关系

```
Phase 2a (知识基建 - RAG)
    │
    ├── 依赖：无（直接使用现有知识库 API）
    ├── 产出：RAG 参考注入 + 飞书文档同步
    └── 前置条件：无矩2.0 微服务运行中
    │
Phase 2b (知识图谱)
    │
    ├── 依赖：Phase 2a（历史 PRD 已入库）
    ├── 产出：业务知识图谱 + 影响范围推理
    └── 前置条件：历史 PRD 已处理并导入
    │
Phase 3 (深度模式)
    │
    ├── 依赖：Phase 2b（图谱推理能力）
    ├── 产出：4 Agent 流水线 + 校验器 + 人工闸口
    └── 前置条件：知识图谱可用
    │
Phase 4 (原型闭环)
    │
    ├── 依赖：Phase 3（深度模式 Agent 4 输出 Spec）
    ├── 产出：JSON Schema 原型 + Machine-Readable Spec
    └── 前置条件：深度模式可用
```

### 7.2 优先级与排期

| 优先级 | Phase | 模块 | 预估天数 | 依赖 |
|--------|-------|------|---------|------|
| **P0** | 2a | 历史 PRD 预处理 + 导入知识库 | 1 天 | 无 |
| **P0** | 2a | RAG 检索注入 | 1.5 天 | 知识库导入完成 |
| **P0** | 2a | 飞书文档同步 | 0.5 天 | 无 |
| **P1** | 2b | 知识图谱 Schema 定义 + 实体提取 | 2 天 | 历史 PRD 已入库 |
| **P1** | 2b | 图谱存储 + 影响范围查询 | 1 天 | 实体提取完成 |
| **P1** | 2b | 双模型路由 | 0.5 天 | 无 |
| **P2** | 3 | 深度模式 4 Agent 流水线 | 3 天 | 知识图谱可用 |
| **P2** | 3 | 校验器矩阵 + 人工闸口 | 2 天 | Agent 流水线完成 |
| **P2** | 3 | LangGraph 编排引擎 | 2 天 | Agent 流水线完成 |
| **P3** | 4 | UI 组件库 Schema | 2 天 | 无 |
| **P3** | 4 | 动态渲染引擎 | 3 天 | 组件库 Schema |
| **P3** | 4 | Machine-Readable Spec | 2 天 | 深度模式 Agent 4 |
| **P3** | 4 | 模板自动提取 | 1 天 | 历史 PRD 已入库 |
| | | **总计** | **~21 天** | |

### 7.3 快速启动建议

当前可以从 Phase 2a 的第一步开始，不依赖任何前置条件：

```
Day 1-2:   PRD 预处理脚本 + 导入知识库
Day 3-4:   RAG 检索注入 + 前端开关
Day 5:     飞书文档同步
--- 验收 Phase 2a ---
Day 6-7:  知识图谱 Schema + 实体提取
Day 8:    图谱存储 + 查询接口
--- 验收 Phase 2b ---
```

---

## 八、关键技术决策

### 8.1 知识库 vs 直接 SQLite 存储

| 方案 | 优点 | 缺点 |
|------|------|------|
| 使用现有知识库（无矩2.0） | 统一管理、已有向量检索、可在 KbManage 页面查看 | 依赖微服务可用性 |
| 自建 SQLite + embedding | 无外部依赖、控制力强 | 需要额外实现向量检索、管理复杂 |

**决策：** 使用现有知识库。原因：① 你已在知识库中积累内容，统一管理更合理；② 现有 `kb_manage.py` 代理层可直接复用；③ 向量检索能力已有，无需重复实现。

### 8.2 飞书同步复用现有代码

`feishu_client.py` 中已有 `create_doc_xml()` 方法，接受 Markdown 内容创建飞书文档。直接复用，不需要重新对接飞书 API。

### 8.3 图片处理策略

| 方案 | 适用场景 | 推荐 |
|------|---------|------|
| 保留图片链接 | 图片不重要，仅作参考 | ❌ |
| 多模态 LLM 生成描述 | 图片含关键信息（架构图、流程图） | ✅ 推荐 |
| 图片 OCR 提取文字 | 图片含大量文字 | ❌（PRD 图片通常不是纯文字） |

**决策：** 使用多模态 LLM 生成描述。十几个 PRD，图片数量有限，成本可控。

### 8.4 知识图谱存储

| 方案 | 优点 | 缺点 |
|------|------|------|
| NetworkX（Python） | 零部署、内存操作、与 Flask 同一进程 | 数据量有限、不支持持久化查询 |
| Neo4j | 生产级、支持复杂查询、持久化 | 需要额外部署、运维成本高 |

**决策：** 初期使用 NetworkX + JSON 文件持久化。当实体数量超过 1000 或需要复杂查询时迁移至 Neo4j。

---

## 九、风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| 无矩2.0 微服务停机 | RAG 检索不可用，PRD 生成降级（无参考） | 中 | 代码层 try/catch 捕获，降级到无 RAG 模式 |
| 历史 PRD 图片质量差 | LLM 生成的图片描述不准 | 低 | 人工抽检 + 手动修正 |
| LangGraph 引入成本高 | 学习曲线陡峭，开发周期延长 | 中 | MVP 阶段先用 Flask 状态机，满足后再替换 |
| 深度模式 Token 消耗大 | 成本超预期 | 中 | 双模型路由（简单用 flash，深度用 pro），非所有场景都用 pro |

---

## 十、附录

### 10.1 完整文件清单

| Phase | 操作 | 文件 |
|-------|------|------|
| 2a | 新建 | `backend/tools/preprocess_prd_docs.py` |
| 2a | 新建 | `backend/tools/import_prd_to_kb.py` |
| 2a | 修改 | `backend/services/prd_gen_service.py` |
| 2a | 修改 | `backend/routers/prd_gen.py` |
| 2a | 修改 | `frontend/src/pages/PrdGen.tsx` |
| 2a | 修改 | `frontend/src/api/prdGen.ts` |
| 2b | 新建 | `backend/services/knowledge_graph.py` |
| 2b | 新建 | `backend/tools/extract_prd_graph.py` |
| 2b | 新建 | `backend/data/knowledge/prd_graph.json` |
| 2b | 修改 | `backend/services/prd_gen_service.py` |
| 2b | 修改 | `backend/requirements.txt` |
| 3 | 新建 | `backend/services/deep_agents.py` |
| 3 | 新建 | `backend/services/validators.py` |
| 3 | 新建 | `backend/services/model_router.py` |
| 3 | 修改 | `backend/services/prd_gen_service.py` |
| 3 | 修改 | `backend/routers/prd_gen.py` |
| 3 | 修改 | `frontend/src/pages/PrdGen.tsx` |
| 3 | 修改 | `frontend/src/api/prdGen.ts` |
| 4 | 新建 | `backend/services/spec_generator.py` |
| 4 | 新建 | `frontend/src/components/RenderEngine.tsx` |
| 4 | 新建 | `frontend/src/data/component_schema.json` |
| 4 | 新建 | `backend/tools/extract_template.py` |
| 4 | 修改 | `backend/services/prd_gen_service.py` |
| 4 | 修改 | `frontend/src/pages/PrdGen.tsx` |

### 10.2 与现有代码的复用点

| 现有代码 | 本方案复用方式 |
|---------|--------------|
| `feishu_client.py` | 飞书文档同步（`create_doc_xml()`） |
| `kb_manage.py` | 知识库导入（`POST /api/kb-manage/import`） |
| `llm_client.py` + `LLMConfigProvider` | 双模型路由（已有 Provider 切换逻辑） |
| `code_analyze_service.py` | 代码知识图谱对接（实体名称映射） |
| `utils/sse.ts` | SSE 流式接收（深度模式流式输出） |
| 代码知识图谱（代码变更分析模块） | PRD 业务实体 → 代码模块路径映射 |

### 10.3 与现有知识库的关系

```
知识库（无矩2.0）
├── collection: "prd_history"        ← Phase 2a 导入
│   └── 历史 PRD 文档（含图片描述）
├── collection: "manual_kb"          ← 已有（手动导入）
├── collection: "auto_kb"            ← 已有（代码同步）
└── ... 其他已有 collection ...

PRD 生成时：
  1. 调 /api/query/stream 搜索 "prd_history" collection
  2. 获取最相关的前 3 个片段
  3. 注入 Prompt
```

---

> **文档版本**: v1.0
> **最后更新**: 2026-07-08
> **编写说明**: 基于《PRD智能生成系统方案.md》完整方案 + 与用户的深度讨论（代码知识图谱 vs PRD 业务知识图谱的区分、RAG 优先的实施策略）