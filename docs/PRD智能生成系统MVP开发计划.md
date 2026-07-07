# PRD 智能生成系统 — MVP 开发计划

> **关联文档**: `PRD智能生成系统方案.md`（完整方案）、`PRD智能生成系统 MVP 实施方案.md`（MVP 方案）
> **技术栈**: Flask + React 19 + TypeScript + Ant Design 6
> **预计工期**: 5 天

---

## 文件清单

### 新建文件

| 文件 | 用途 |
|------|------|
| `backend/services/prd_gen_service.py` | PRD 生成核心业务逻辑（会话管理、LLM 调用、状态机） |
| `backend/routers/prd_gen.py` | Flask Blueprint，12 个 API 端点 |
| `backend/project_context.md` | 平台架构快照文件，作为 System Prompt 注入 |
| `frontend/src/api/prdGen.ts` | 前端 API 封装层 |
| `frontend/src/pages/PrdGen.tsx` | PRD 生成主页面 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `backend/services/db.py` | 新增 4 张表（prd_sessions / prd_versions / prd_files / prd_chat_messages） |
| `backend/services/llm_client.py` | 新增 `chat_stream()` 流式方法 |
| `backend/app.py` | 注册 `prd_gen_bp` Blueprint |
| `frontend/src/App.tsx` | 新增 `/prd-gen` 路由 |
| `frontend/src/components/AppLayout.tsx` | 从 comingSoonItems 移到 activeNavItems |

---

## Phase 1: 数据库扩展 — 新增 4 张表

**目标**: 在 `db.py` 中新增 PRD 模块所需的 SQLite 表，全部使用 TEXT 类型存储 JSON。

### 新增表结构

#### prd_sessions

```sql
CREATE TABLE IF NOT EXISTS prd_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'simple',
    status TEXT NOT NULL DEFAULT 'init',
    user_input TEXT NOT NULL DEFAULT '',
    collected_info TEXT NOT NULL DEFAULT '{}',
    minutes_extract TEXT NOT NULL DEFAULT '{}',
    current_round INTEGER NOT NULL DEFAULT 0,
    completeness REAL NOT NULL DEFAULT 0.0,
    outline TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

> collected_info、minutes_extract、outline 均为 TEXT 存 JSON 字符串，Python 层用 `json.loads/dumps` 处理。

#### prd_versions

```sql
CREATE TABLE IF NOT EXISTS prd_versions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    section TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    version_num INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

> 每次重新生成前插入新版本。只保留最近 3 个版本（插入时清理最旧的）。Diff 由前端实时计算，不存储。

#### prd_files

```sql
CREATE TABLE IF NOT EXISTS prd_files (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    filename TEXT NOT NULL DEFAULT '',
    file_type TEXT NOT NULL DEFAULT 'temporary',
    storage_path TEXT NOT NULL DEFAULT '',
    text_content TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### prd_chat_messages

```sql
CREATE TABLE IF NOT EXISTS prd_chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'system',
    content TEXT NOT NULL DEFAULT '',
    round INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 任务清单

- [ ] 在 `db.py` 的 `init_db()` 中添加 4 个 CREATE TABLE 语句
- [ ] 编写对应的 CRUD 函数：`create_prd_session()`、`get_prd_session()`、`update_prd_session()`
- [ ] `save_prd_version()`、`get_prd_versions()`、`cleanup_old_versions()`（保留最近 3 版）
- [ ] `save_prd_file()`、`get_prd_files()`
- [ ] `add_chat_message()`、`get_chat_messages()`

---

## Phase 2: LLM 流式支持

**目标**: 在 `llm_client.py` 中新增 `chat_stream()` 方法，支持 SSE 流式输出。

```python
def chat_stream(
    self,
    system: str,
    user: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> Generator[str, None, None]:
    """流式 Chat 调用，逐 chunk 产出内容

    用于 SSE 流式场景，前端逐字展示生成内容。
    """
    resp = self.client.chat.completions.create(
        model=self.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in resp:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content
```

### 任务清单

- [ ] 在 `LLMClient` 类中添加 `chat_stream()` 方法
- [ ] 验证：调用 `chat_stream()` 能正确 yield 内容片段

---

## Phase 3: 后端核心服务 — `prd_gen_service.py`

**目标**: 实现 PRD 生成的核心业务逻辑。

### 服务类设计

```python
class PRDGenService:
    """PRD 生成核心服务

    管理会话生命周期、LLM 调用、Prompt 组装、完备度检查。
    不依赖 Flask 上下文，方便单元测试。
    """
```

### 3.1 会话管理

| 方法 | 用途 |
|------|------|
| `create_session(mode, user_input)` | 创建会话，返回 session_id |
| `get_session(session_id)` | 获取会话信息 |
| `update_session(session_id, **kwargs)` | 更新会话状态 |

### 3.2 Prompt 模板

所有 Prompt 集中管理，便于维护：

```python
# project_context 从文件加载
PROJECT_CONTEXT_PATH = os.path.join(os.path.dirname(__file__), 'project_context.md')

_SYSTEM_PROMPT_TEMPLATE = """你是机器学习平台的产品需求文档撰写助手。以下为平台背景信息：
{project_context}"""

# 大纲生成
_OUTLINE_PROMPT = """请根据以下需求描述，生成 PRD 大纲（仅返回章节标题列表，JSON 格式）：
{{
  "sections": ["overview", "roles", "features", "stories", "boundaries", "nonfunctional"]
}}

需求描述：{user_input}"""

# 章节生成
_SECTION_PROMPT = """已收集的需求信息：
{collected_info}

请撰写 PRD 的"{section_name}"章节。要求：
- 内容基于已收集的需求信息，不要臆造未提及的功能。
- 使用 Markdown 格式。
- 语言简洁、准确。
- 不要重复生成其他章节已包含的内容。"""

# 问答引导
_QUESTION_PROMPT = """已收集的需求信息：
{collected_info}

当前缺失的信息项：{missing_items}

请根据已有信息，生成一个针对用户的引导问题，用于补充缺失信息。问题应简洁、具体。"""

# 妙记需求提取
_MINUTES_EXTRACT_PROMPT = """你是机器学习平台的需求分析助手。请从以下飞书会议纪要中提取与产品功能需求相关的信息。

会议纪要：
{minutes_text}

请提取以下信息，以 JSON 格式返回：
{{
  "featurePoints": ["功能需求点1", "功能需求点2"],
  "stakeholders": ["涉及的干系人/角色"],
  "constraints": ["约束条件/限制"],
  "background": "需求产生的背景和动机"
}}"""
```

### 3.3 简单模式

```python
def simple_generate(
    self, session_id: str, api_key: str, base_url: str, model: str
) -> Generator[str, None, None]:
    """简单模式生成流程

    1. 生成大纲 → 存入 session.outline
    2. 逐章节生成 → 每章节 SSE section_complete 事件
    """
    session = self.get_session(session_id)
    llm = LLMClient(api_key, base_url, model)

    # Step 1: 生成大纲
    yield sse_event('progress', {'step': 'outline', 'message': '正在生成大纲...'})
    outline_text = llm.chat(
        system=self._build_system_prompt(),
        user=_OUTLINE_PROMPT.format(user_input=session['user_input']),
    )
    outline = self._parse_outline(outline_text)
    self.update_session(session_id, outline=json.dumps(outline))
    yield sse_event('section_complete', {'section': 'outline', 'outline': outline})

    # Step 2: 逐章节生成
    for section in outline:
        yield sse_event('progress', {'step': section, 'message': f'正在生成章节 {section}...'})
        content = self._generate_section(session_id, section, llm)
        yield sse_event('section_complete', {'section': section, 'content': content})

    yield sse_event('complete', {'sessionId': session_id})
```

### 3.4 中等模式 — 对话轮次

```python
def chat_round(
    self, session_id: str, answer: str, api_key: str, base_url: str, model: str
) -> dict:
    """处理一轮对话

    1. 保存用户回答到 collected_info
    2. 检查完备度
    3. 如果完备度 >= 0.8，返回 ready_for_outline
    4. 否则生成下一个引导问题
    """
    session = self.get_prd_session(session_id)
    llm = LLMClient(api_key, base_url, model)

    # 保存用户回答
    collected = json.loads(session['collected_info'] or '{}')
    round_num = session['current_round'] + 1
    self.add_chat_message(session_id, 'user', answer, round_num)

    # 更新 collected_info（LLM 从回答中提取结构化信息）
    # ...

    # 检查完备度
    completeness = self._check_completeness(collected)
    self.update_prd_session(session_id, current_round=round_num, completeness=completeness)

    if completeness >= 0.8:
        return {'status': 'ready_for_outline', 'completeness': completeness}

    # 生成下一个问题
    question = self._generate_question(collected, llm)
    self.add_chat_message(session_id, 'system', question, round_num)

    return {
        'round': round_num,
        'question': question,
        'completeness': completeness,
    }
```

### 3.5 信息完备度检查

6 项核心信息，缺失 <= 1 项即达标：

```python
def _check_completeness(self, collected: dict) -> float:
    """检查信息完备度

    6 项核心信息，返回 0-1 分数。
    """
    checks = [
        bool(collected.get('featureOverview')),
        bool(collected.get('userRoles')),
        bool(collected.get('corePath')),
        bool(collected.get('boundaries')),
        bool(collected.get('inputOutput')),
        bool(collected.get('dependencies')),  # 可跳过
    ]
    # 最后一项"依赖模块"可跳过，分母为 5
    met = sum(1 for c in checks[:5] if c)
    return met / 5.0
```

### 3.6 章节生成

```python
def generate_section_stream(
    self, session_id: str, section: str, llm: LLMClient
) -> Generator[str, None, None]:
    """流式生成单个章节，返回 SSE 事件"""
    session = self.get_prd_session(session_id)
    collected = json.loads(session['collected_info'] or '{}')

    is_new = not self._section_exists(session_id, section)
    if not is_new:
        # 保存当前版本快照
        self._save_version_snapshot(session_id, section)

    section_name = self._SECTION_NAMES.get(section, section)
    full_content = ''
    for chunk in llm.chat_stream(
        system=self._build_system_prompt(),
        user=_SECTION_PROMPT.format(
            collected_info=session.get('user_input', '') or json.dumps(collected, ensure_ascii=False),
            section_name=section_name,
        ),
    ):
        full_content += chunk
        yield sse_event('progress', {'chunk': chunk, 'section': section})

    # 保存章节内容
    self._save_section_content(session_id, section, full_content)

    if is_new:
        version_id = self._save_version_snapshot(session_id, section)
    else:
        version_id = self._get_latest_version_id(session_id, section)

    yield sse_event('section_complete', {'section': section, 'content': full_content, 'versionId': version_id})
```

### 3.7 版本管理

```python
def _save_version_snapshot(self, session_id: str, section: str) -> str:
    """保存当前章节版本快照

    1. 读取当前章节内容
    2. 插入 prd_versions 表
    3. 清理该章节超过 3 个版本的旧记录
    """
    content = self._get_section_content(session_id, section)
    version_id = str(uuid.uuid4())
    version_num = self._get_next_version_num(session_id, section)

    save_prd_version(version_id, session_id, section, content, version_num)
    cleanup_old_versions(session_id, section, keep=3)

    return version_id
```

### 3.8 妙记解析

直接复用 `feishu_client.py` 和 `meeting_todo_service.py` 的现有代码：

```python
def parse_minutes(
    self, session_id: str, url: str, api_key: str, base_url: str, model: str
) -> dict:
    """解析飞书妙记链接，提取需求要点

    复用现有 feishu_client.get_minute_info() + get_transcript()
    """
    from services.meeting_todo_service import parse_minutes_link
    from services.feishu_client import get_minute_info, get_transcript

    minute_token = parse_minutes_link(url)
    if not minute_token:
        return {'status': 'error', 'message': '无效的妙记链接'}

    minute_info = get_minute_info(minute_token)
    transcript = get_transcript(minute_token)

    llm = LLMClient(api_key, base_url, model)
    result_text = llm.chat(
        system="你是机器学习平台的需求分析助手。",
        user=_MINUTES_EXTRACT_PROMPT.format(minutes_text=transcript[:80000]),
    )

    extracted = self._parse_json_safe(result_text, {
        'featurePoints': [], 'stakeholders': [],
        'constraints': [], 'background': '',
    })

    # 存入会话上下文
    self.update_prd_session(session_id, minutes_extract=json.dumps(extracted, ensure_ascii=False))

    return {
        'status': 'success',
        'minuteTitle': minute_info.get('data', {}).get('minute', {}).get('title', ''),
        'extractedPoints': extracted,
    }
```

### 3.9 导出

```python
def export_prd(self, session_id: str) -> str:
    """导出完整 PRD Markdown

    按章节顺序拼接所有章节内容，返回完整 Markdown 字符串。
    """
    session = self.get_prd_session(session_id)
    outline = json.loads(session.get('outline', '[]') or '[]')

    sections = []
    for section in outline:
        content = self._get_section_content(session_id, section)
        if content:
            sections.append(content)

    return '\n\n---\n\n'.join(sections) if sections else '# PRD\n\n（内容尚未生成）'
```

### 3.10 文件上传

```python
def handle_file_upload(self, session_id: str, file_storage, file_type: str) -> dict:
    """处理文件上传

    支持 .md / .txt / .docx，不超过 10MB。
    临时文件存入 /tmp/sessions/{session_id}/，长期文件存入 data/knowledge/permanent/
    """
    import os
    from werkzeug.utils import secure_filename

    # 校验
    filename = secure_filename(file_storage.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ('.md', '.txt', '.docx'):
        return {'error': '不支持的文件格式，仅支持 .md / .txt / .docx'}

    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > 10 * 1024 * 1024:
        return {'error': '文件大小超过 10MB 限制'}

    # 存储
    base_dir = '/tmp/sessions' if file_type == 'temporary' else 'data/knowledge/permanent'
    os.makedirs(f'{base_dir}/{session_id}', exist_ok=True)
    save_path = f'{base_dir}/{session_id}/{filename}'
    file_storage.save(save_path)

    # 提取文本
    text_content = self._extract_text(file_storage, ext)

    # 存入数据库
    file_id = str(uuid.uuid4())
    save_prd_file(file_id, session_id, filename, file_type, save_path, text_content)

    return {'id': file_id, 'filename': filename, 'file_type': file_type, 'text_preview': text_content[:500]}
```

### 任务清单

- [ ] 创建 `prd_gen_service.py`，实现 `PRDGenService` 类
- [ ] 实现 `create_session()` / `get_session()` / `update_session()`
- [ ] 实现 Prompt 模板常量
- [ ] 实现 `simple_generate()` — 大纲 + 逐章节 SSE 流式
- [ ] 实现 `chat_round()` — 问答轮次 + 完备度检查
- [ ] 实现 `_check_completeness()` — 6 项核心信息检查
- [ ] 实现 `generate_section_stream()` — 单章节流式生成
- [ ] 实现 `_save_version_snapshot()` — 版本快照 + 保留最近 3 版
- [ ] 实现 `parse_minutes()` — 复用 feishu_client 解析妙记
- [ ] 实现 `export_prd()` — 拼接完整 Markdown
- [ ] 实现 `handle_file_upload()` — 文件上传与文本提取
- [ ] 创建 `project_context.md` 默认模板

---

## Phase 4: Flask Blueprint — `routers/prd_gen.py`

**目标**: 实现 12 个 API 端点，统一注册在 `/api/prd/*` 路径下。

```python
prd_gen_bp = Blueprint('prd_gen', __name__)

service = PRDGenService()
```

### 端点列表

| 方法 | 路径 | 用途 | 说明 |
|------|------|------|------|
| POST | `/api/prd/sessions` | 创建会话 | 需 mode + userInput |
| POST | `/api/prd/sessions/{id}/simple-generate` | 简单模式 SSE 生成 | 返回 outline + section_complete 事件 |
| POST | `/api/prd/sessions/{id}/chat` | 中等模式对话 | 返回引导问题或 ready_for_outline |
| GET | `/api/prd/sessions/{id}/completeness` | 查询完备度 | 返回 completeness 分数 + 缺失项 |
| POST | `/api/prd/sessions/{id}/outline` | 生成大纲 | 调用 LLM 生成大纲 |
| POST | `/api/prd/sessions/{id}/sections/{section}/generate` | 章节流式生成 | SSE 流式返回章节内容 |
| PUT | `/api/prd/sessions/{id}/sections/{section}` | 编辑章节 | 保存用户编辑内容 |
| POST | `/api/prd/sessions/{id}/sections/{section}/regenerate` | 重新生成章节 | 保存版本快照后 SSE 流式返回 |
| GET | `/api/prd/sessions/{id}/versions` | 获取版本列表 | 返回所有章节的版本列表 |
| GET | `/api/prd/sessions/{id}/export` | 导出 PRD | `Content-Disposition: attachment` 返回 .md 文件 |
| POST | `/api/prd/files/upload` | 上传文件 | multipart/form-data，带 file_type 参数 |
| POST | `/api/prd/sessions/{id}/minutes` | 解析妙记 | 复用 feishu_client 提取需求要点 |

### 关键实现细节

**SSE 流式路由** (Flask 模式):

```python
@prd_gen_bp.route('/sessions/<id>/simple-generate', methods=['POST'])
def simple_generate(id):
    session = service.get_prd_session(id)
    if not session:
        return {'error': '会话不存在'}, 404

    llm_config = getattr(g, 'llm_config', {})
    api_key = llm_config.get('api_key', '')
    base_url = llm_config.get('base_url', '')
    model = llm_config.get('model', '')

    if not api_key:
        return sse_stream(lambda: iter([sse_event('error', {'message': '请先配置 LLM API Key'})]))

    def generate():
        yield from service.simple_generate(id, api_key, base_url, model)

    return sse_stream(generate)
```

**导出路由** (GET 文件下载):

```python
@prd_gen_bp.route('/sessions/<id>/export', methods=['GET'])
def export_prd(id):
    """导出 PRD 为 Markdown 文件（GET 请求）"""
    markdown = service.export_prd(id)
    session = service.get_prd_session(id)
    filename = f"PRD-{session.get('user_input', 'untitled')[:20]}.md"
    response = Response(
        markdown,
        mimetype='text/markdown',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}.md"',
        },
    )
    return response
```

**文件上传路由** (multipart/form-data):

```python
@prd_gen_bp.route('/files/upload', methods=['POST'])
def upload_file():
    """上传文件（带分类标记）"""
    if 'file' not in request.files:
        return {'error': '请选择文件'}, 400

    file = request.files['file']
    file_type = request.form.get('file_type', 'temporary')
    session_id = request.form.get('session_id', '')

    if not session_id:
        return {'error': '缺少 session_id'}, 400

    result = service.handle_file_upload(session_id, file, file_type)
    if 'error' in result:
        return result, 400
    return result
```

### 任务清单

- [ ] 创建 `routers/prd_gen.py`，注册 Blueprint
- [ ] 实现 `POST /sessions` — 创建会话
- [ ] 实现 `POST /sessions/{id}/simple-generate` — SSE 流式生成
- [ ] 实现 `POST /sessions/{id}/chat` — 对话轮次
- [ ] 实现 `GET /sessions/{id}/completeness` — 完备度查询
- [ ] 实现 `POST /sessions/{id}/outline` — 大纲生成
- [ ] 实现 `POST /sessions/{id}/sections/{section}/generate` — SSE 流式章节生成
- [ ] 实现 `PUT /sessions/{id}/sections/{section}` — 编辑章节
- [ ] 实现 `POST /sessions/{id}/sections/{section}/regenerate` — 重新生成 + 版本快照
- [ ] 实现 `GET /sessions/{id}/versions` — 版本列表
- [ ] 实现 `GET /sessions/{id}/export` — 导出(Content-Disposition: attachment)
- [ ] 实现 `POST /files/upload` — 文件上传(multipart)
- [ ] 实现 `POST /sessions/{id}/minutes` — 妙记解析
- [ ] 在 `app.py` 中注册 `prd_gen_bp`

---

## Phase 5: 前端 API 层 — `api/prdGen.ts`

### 类型定义

```typescript
// 会话
interface PRDSession {
  sessionId: string
  mode: 'simple' | 'medium'
  status: 'init' | 'chatting' | 'writing' | 'done'
  completeness: number
  currentRound: number
  outline: string[]
}

// 会话创建
interface CreateSessionRequest {
  mode: 'simple' | 'medium'
  userInput: string
}

// 对话轮次
interface ChatRequest {
  answer: string
}

interface ChatResponse {
  round: number
  question?: string
  status?: 'ready_for_outline'
  completeness: number
}

// 章节生成 SSE 事件
interface SectionProgressEvent {
  chunk: string
  section: string
}

interface SectionCompleteEvent {
  section: string
  content: string
  versionId: string
}

// 大纲
interface OutlineEvent {
  section: 'outline'
  outline: string[]
}

// 导出
interface ExportResult {
  url: string
}

// 文件上传
interface FileUploadResult {
  id: string
  filename: string
  file_type: 'temporary' | 'permanent'
  text_preview: string
}

// 妙记解析
interface MinutesParseResult {
  status: string
  minuteTitle: string
  extractedPoints: {
    featurePoints: string[]
    stakeholders: string[]
    constraints: string[]
    background: string
  }
}
```

### API 函数

```typescript
export async function createSession(req: CreateSessionRequest): Promise<PRDSession>
export async function simpleGenerate(id: string, callbacks: SimpleGenerateCallbacks, signal?: AbortSignal): Promise<void>
export async function chatRound(id: string, req: ChatRequest): Promise<ChatResponse>
export async function getCompleteness(id: string): Promise<{ completeness: number; missingItems: string[] }>
export async function generateOutline(id: string): Promise<{ outline: string[] }>
export async function generateSection(id: string, section: string, callbacks: SectionCallbacks, signal?: AbortSignal): Promise<void>
export async function updateSection(id: string, section: string, content: string): Promise<void>
export async function regenerateSection(id: string, section: string, callbacks: SectionCallbacks, signal?: AbortSignal): Promise<void>
export async function getVersions(id: string, section?: string): Promise<VersionInfo[]>
export async function exportPRD(id: string): Promise<void>  // 触发浏览器下载
export async function uploadFile(sessionId: string, file: File, fileType: string): Promise<FileUploadResult>
export async function parseMinutes(id: string, url: string): Promise<MinutesParseResult>
```

### 任务清单

- [ ] 创建 `api/prdGen.ts`，定义完整类型和 API 函数
- [ ] 导出接口统一使用 `API_BASE` + `/api/prd/...`
- [ ] SSE 接口复用 `streamRequest()` 模式
- [ ] 导出接口使用 `window.open()` 或 `<a>` 标签触发下载

---

## Phase 6: 前端页面 — `pages/PrdGen.tsx`

**目标**: 实现完整的 PRD 生成工作台页面。

### 页面布局

```
┌─────────────────────────────────────────────────┐
│  PRD 智能生成工作台                              │
├─────────────────────────────────────────────────┤
│  [步骤条] 选择输入 → 补充需求 → 生成大纲 → 撰写    │
├─────────────────────────────────────────────────┤
│  ┌─ 输入区 ─────────────────────────────────┐   │
│  │  [Tab: 文字描述] [Tab: 上传文件] [Tab: 妙记] │   │
│  │  ┌──────────────────────────────────┐    │   │
│  │  │ TextArea / Upload / 链接输入      │    │   │
│  │  └──────────────────────────────────┘    │   │
│  │  模式: [Simple] [Medium]  [生成]        │   │
│  └──────────────────────────────────────────┘   │
├─────────────────────────────────────────────────┤
│  ┌─ Q&A 区（Medium 模式）────────────────────┐  │
│  │  问题: "请描述这次功能的核心目标？"          │  │
│  │  TextArea → [发送]  completeness: ████░░  │  │
│  └──────────────────────────────────────────┘   │
├─────────────────────────────────────────────────┤
│  ┌─ 大纲区 ─────────────────────────────────┐   │
│  │  1. 功能概述  [生成] ✓                    │   │
│  │  2. 用户角色  [生成] ✓                    │   │
│  │  3. 功能清单  [生成] ▶ (流式生成中)        │   │
│  │  4. 用户故事  [生成]                      │   │
│  │  5. 边界条件  [生成]                      │   │
│  └──────────────────────────────────────────┘   │
├─────────────────────────────────────────────────┤
│  ┌─ 编辑器区 ───────────────────────────────┐  │
│  │  [Tab: 功能概述]  [Tab: 用户角色]  ...     │  │
│  │  ┌──────────────────────────────────┐    │  │
│  │  │ Markdown 渲染 / 编辑区            │    │  │
│  │  └──────────────────────────────────┘    │  │
│  │  [重新生成] [编辑] [版本回退] [导出]      │  │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### 组件拆分

建议将 PrdGen.tsx 拆分为几个子组件，避免单文件过大：

| 组件 | 职责 |
|------|------|
| `PrdGen.tsx` | 主页面，状态管理，步骤控制 |
| `InputSection.tsx` | 输入区（文字/文件/妙记 Tab） |
| `QASection.tsx` | 中等模式问答交互 |
| `OutlineSection.tsx` | 大纲展示 + 章节触发生成 |
| `PRDEditor.tsx` | 章节编辑器 + Diff 对比 + 版本管理 |

### 状态管理

```typescript
interface PrdGenState {
  // 会话
  sessionId: string | null
  mode: 'simple' | 'medium'
  status: 'init' | 'chatting' | 'writing' | 'done'

  // 输入
  userInput: string
  uploadedFiles: FileUploadResult[]
  minutesExtract: MinutesParseResult | null

  // 中等模式
  chatHistory: { role: string; content: string }[]
  currentQuestion: string
  completeness: number

  // 大纲与章节
  outline: string[]
  sectionContents: Record<string, string>
  sectionVersions: Record<string, VersionInfo[]>
  currentSection: string | null

  // 生成状态
  generatingSection: string | null
  streamingContent: string
}
```

### 关键交互流程

**简单模式**:
1. 用户输入文字 → 点击"生成"
2. 调用 `POST /api/prd/sessions` (mode=simple)
3. 调用 `POST /api/prd/sessions/{id}/simple-generate` (SSE)
4. 监听 `progress` 事件更新流式内容
5. 监听 `section_complete` 事件更新章节
6. 监听 `complete` 事件结束

**中等模式**:
1. 用户输入文字（可选）→ 点击"开始"
2. 调用 `POST /api/prd/sessions` (mode=medium)
3. 循环调用 `POST /api/prd/sessions/{id}/chat` 直到 `ready_for_outline`
4. 调用 `POST /api/prd/sessions/{id}/outline` 生成大纲
5. 用户逐章节点击 → 调用 `POST /api/prd/sessions/{id}/sections/{section}/generate`

**重新生成 + Diff 对比**:
1. 用户点击"重新生成"
2. 调用 `POST /api/prd/sessions/{id}/sections/{section}/regenerate` (SSE)
3. 保存当前内容到版本历史
4. 新内容流式返回
5. 前端使用 `react-diff-viewer` 展示新旧对比
6. 用户逐条接受/拒绝

**Diff 对比实现**（前端实时计算）:

```tsx
import ReactDiffViewer from 'react-diff-viewer-continued'

function DiffViewer({ oldContent, newContent, onAccept, onReject }) {
  return (
    <ReactDiffViewer
      oldValue={oldContent}
      newValue={newContent}
      splitView={false}
      leftTitle="修改前"
      rightTitle="修改后"
    />
  )
}
```

### 任务清单

- [ ] 创建 `PrdGen.tsx` 主页面骨架
- [ ] 实现步骤条（4 步：选择输入 → 补充需求 → 生成大纲 → 撰写）
- [ ] 实现输入区（3 个 Tab：文字描述/上传文件/妙记链接）
- [ ] 实现简单模式完整流程
- [ ] 实现中等模式 Q&A 交互
- [ ] 实现信息完备度指示器
- [ ] 实现大纲展示与章节触发
- [ ] 实现章节编辑器（Markdown 渲染 + 编辑切换）
- [ ] 实现重新生成 + Diff 对比视图
- [ ] 实现版本管理（版本列表 + 回退）
- [ ] 实现导出（触发浏览器下载）
- [ ] 状态管理：loading、empty、error、streaming 四种状态覆盖

---

## Phase 7: 路由注册 + 侧边栏集成

### App.tsx

```tsx
import PrdGen from './pages/PrdGen'

// 在 Routes 中新增
<Route path="/prd-gen" element={<PrdGen />} />
```

### AppLayout.tsx

从 `comingSoonItems` 移除 `/prd-gen`，加入 `activeNavItems`：

```tsx
const activeNavItems = [
  { key: '/meeting-todo', icon: <LikeOutlined />, label: '会议 TODO' },
  { key: '/iteration-stats', icon: <BarChartOutlined />, label: '迭代统计' },
  { key: '/ai-measure', icon: <FileTextOutlined />, label: '数据报告' },
  { key: '/chat', icon: <WechatOutlined />, label: '知识库问答' },
  { key: '/kb-manage', icon: <DatabaseOutlined />, label: '知识库管理' },
  { key: '/code-analyze', icon: <CodeOutlined />, label: '功能变更分析' },
  { key: '/prd-gen', icon: <FileTextOutlined />, label: 'PRD 智能生成' },  // 新增
]
```

### 任务清单

- [ ] `App.tsx` 新增路由
- [ ] `AppLayout.tsx` 从 comingSoonItems 移到 activeNavItems

---

## 验证方式

### 后端验证

```bash
# 1. 启动后端
cd backend && python run.py

# 2. 创建会话
curl -X POST http://localhost:5000/api/prd/sessions \
  -H "Content-Type: application/json" \
  -d '{"mode": "simple", "userInput": "开发一个模型版本管理功能"}'

# 3. 简单模式生成（SSE）
curl -N -X POST http://localhost:5000/api/prd/sessions/{id}/simple-generate \
  -H "Accept: text/event-stream"

# 4. 中等模式对话
curl -X POST http://localhost:5000/api/prd/sessions/{id}/chat \
  -H "Content-Type: application/json" \
  -d '{"answer": "用户可以对模型进行版本管理，包括注册、对比、回滚"}'

# 5. 导出
curl -O -J http://localhost:5000/api/prd/sessions/{id}/export
```

### 前端验证

```bash
cd frontend && npm run dev
```

1. 访问 `/prd-gen` 确认侧边栏跳转正确
2. 简单模式：输入需求 → 生成 → 流式输出 → 导出
3. 中等模式：输入 → 3-5 轮对话 → 完备度达标 → 大纲 → 章节生成
4. 文件上传：上传 .md/.txt/.docx 文件
5. 妙记解析：粘贴妙记链接 → 提取需求要点
6. 重新生成 + Diff 对比
7. 版本回退
8. TypeScript `tsc --noEmit` 零错误

---

## 验收标准（对应 MVP 文档 F1-F11）

| 编号 | 验收项 | 对应 Phase | 验证方式 |
|------|--------|-----------|---------|
| F1 | 简单模式 30 秒内流式输出，6 个章节 | Phase 3+6 | 输入需求 → 检查章节完整性 |
| F2 | 中等模式 3-5 轮问答，问题与回答相关 | Phase 3+6 | 开始对话 → 检查问题合理性 |
| F3 | 完备度检查，缺失 >1 项继续追问 | Phase 3 | 只给 3 项信息 → 预期继续追问 |
| F4 | 大纲生成，用户可确认 | Phase 3+6 | 阶段一完成后检查大纲展示 |
| F5 | 分章节流式生成，不阻塞 UI | Phase 6 | 点击章节 → 流式输出不受阻 |
| F6 | 重新生成 + Diff 对比 | Phase 6 | 重新生成 → 检查 Diff 视图 |
| F7 | 版本回退（最近 3 版） | Phase 3 | 多次重新生成 → 检查版本列表 |
| F8 | 文件上传 + 分类 | Phase 3+6 | 上传文件 → 检查分类标记 |
| F9 | 妙记链接解析 | Phase 3 | 粘贴妙记链接 → 提取结构化需求 |
| F10 | 多源融合 | Phase 3+6 | 同时提供文字 + 妙记 → 结果体现两来源 |
| F11 | 导出 Markdown | Phase 5+6 | 导出 → 检查文件格式和内容 |

---

## 依赖关系

```
Phase 1 (数据库) ──→ Phase 3 (服务层) ──→ Phase 4 (路由)
                        ↑                       ↓
Phase 2 (LLM 流式) ───┘           Phase 5 (API 层) ──→ Phase 6 (页面) ──→ Phase 7 (路由集成)
```

- Phase 1-2 可并行
- Phase 3 依赖 Phase 1 + Phase 2
- Phase 4 依赖 Phase 3
- Phase 5 依赖 Phase 4（接口可用后，也可并行定义类型）
- Phase 6 依赖 Phase 5
- Phase 7 独立