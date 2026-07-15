# PRD 深度模式实施方案 v2

> **关联**: `docs/PRD智能生成系统-完整实施路径方案.md` (v1,2026-07-08) + `ju/docs/KB_DEEP_MODE_PLAN.md` (知识库侧)
> **日期**: 2026-07-15 → 2026-07-16
> **状态**: 已实施
> **v1→v2 修正**: v1 设想中控台自建 NetworkX 业务图谱 (Phase 2b) + 自抽象 antd 组件 schema (Phase 4)。实际知识库侧已把代码图谱影响分析 (A1-A4) + 模块索引 + 5 个对外 API + `component_registry.json` (606 组件) 全部做完。中控台不重造轮子,直接 HTTP 消费知识库产物。

---

## 一、决策已确认

| 决策项 | 选择 | 理由 |
|---|---|---|
| 历史 PRD 数据 | 暂不加载 | 代码先写,`_retrieve_reference_context` 无数据降级空串 |
| deepseek-v4-pro | 可用 | Agent 2/3 用 pro 强推理,Agent 1/4 用 flash |
| registry.json 取数 | 直接 HTTP 读微服务文件 | 微服务挂则原型功能不可用,降级提示 |
| LangGraph | **非必须,先状态机** | 见下节 |

## 二、LangGraph 讨论:非必须,先状态机

### 流水线形状

```
Agent1(萃取,flash) → V:Schema → [fail→A1]
  → Gate1(冲突确认,人工)
  → Agent2(上下文,pro,调KB图谱) → Gate2(影响确认,人工)
  → V:Scope/Citation/Acceptance/Permission → [fail→A3]
  → Agent3(规格,pro) → Gate3(规格确认,人工)
  → Agent4(撰写,flash) → V:Risk → done
```

本质:**线性 + 3 人工闸口 + 校验器回退**。非复杂分支/并行。

### LangGraph 给的(免费)

| 能力 | 需要? |
|---|---|
| 声明式状态图 + 条件边 | ✅ 有用,if/else 也能写 |
| Checkpoint 持久化 | ⚠️ 已有 `prd_sessions` 表存 state |
| 人工中断/恢复 primitive | ⚠️ Flask SSE generator 暂停 + POST 恢复,已能做 |
| Time travel / replay 调试 | ❌ PRD 会话 ~5min,不需跨天恢复 |
| 多 agent 并行 | ❌ 串行 |

### 已有(不需 LangGraph 重造)

- `prd_sessions` 表 → state 持久化
- `sse_helpers` → 流式
- `_parse_json_safe` 5 层容错 → LLM 结构化输出
- `inject_llm_config` → 模型配置注入

### 成本对比

| 方案 | 依赖 | 代码量 | 风险 |
|---|---|---|---|
| 纯状态机 | 0 | ~250 行 orchestrator + state enum | 手写 transition,线性简单 |
| LangGraph | langgraph + langchain-core (重,版本变动频繁) | 节点 + graph 声明 | 学习曲线 + 依赖锁版本 |

### 状态机→LangGraph 迁移成本

~1 天:节点逻辑不变,把 transition 搬进 graph node,swap checkpointer。不痛。

### 判断

**非必须**。理由:① 流水线线性+3 闸口,非复杂分支 ② 已有 SQLite state + SSE,LangGraph 的 checkpoint/resume 重复造轮子 ③ YAGNI — langchain 版本变动频繁,引入即背技术债 ④ 迁移成本 1 天,需要时再升不晚。

**引入信号**:跨天恢复半成品会话 或 agent replay 调试出现时。PRD 会话短生命周期,无此需求。

> 方案文档 v1 5.5 节 + 风险表亦写:"MVP 阶段先用 Flask 状态机,满足后再替换"。

### 状态机实现

```python
class DeepMode:
    INIT = 'init'
    AGENT1_DONE = 'agent1_done'       # 等 Gate1
    AGENT2_DONE = 'agent2_done'       # 等 Gate2
    AGENT3_DONE = 'agent3_done'       # 等 Gate3
    WRITING = 'writing'               # Agent4 流式中
    DONE = 'done'
    ERROR = 'error'
```

`prd_sessions` 表加 `deep_state` + `deep_artifacts` 两列(JSON 存各 Agent 产出 + 闸口确认)。

---

## 三、阶段 0:kb_manage graph 代理 + RAG 基建(无依赖,立即开始)

### 0.1 kb_manage.py 加 5 个 graph 代理端点

复用 `_proxy_get` 模式,代理到 `localhost:8000/api/admin/...`:

| Flask 路径 | 代理到 | 备注 |
|---|---|---|
| `GET /api/kb-manage/modules` | `/api/admin/modules` | 12 模块清单 |
| `GET /api/kb-manage/modules/<name>` | `/api/admin/modules/{name}` | 单模块架构快照 |
| `GET /api/kb-manage/graph/impact?node=&direction=&depth=` | `/api/admin/graph/impact` | 影响范围(direction: in/outgoing) |
| `GET /api/kb-manage/graph/flow?api=` | `/api/admin/graph/flow` | API 调用链 |
| `GET /api/kb-manage/graph/node/<node_id>` | `/api/admin/graph/node/{node_id}` | 节点详情 |

URL 中文模块名需 `quote`。响应信封 `{status, data, error}` 原样透传。

### 0.2 frontend api/kbManage.ts 加 5 函数 + 类型

```typescript
export interface PlatformModule { module_name: string; node_count: number; description?: string }
export interface ModuleOverview {
  module_name: string; controllers: any[]; apis: any[];
  frontend_pages: any[]; external_deps: any[]; description?: string;
}
export interface ImpactResult {
  origin: any; direction: 'outgoing'|'incoming';
  impacted: Array<{node: any; depth: number; path: string[]; edge_types_traversed: string[]}>;
  summary_by_type: Record<string, number>;
  candidates?: any[];  // 名称多候选
}

export async function listModules(): Promise<{modules: PlatformModule[]; total: number}>
export async function getModuleOverview(name: string): Promise<ModuleOverview>
export async function graphImpact(node: string, direction: 'in'|'out', depth?: number): Promise<ImpactResult>
export async function graphFlow(api: string): Promise<any>
export async function getGraphNode(nodeId: string): Promise<any>
```

### 0.3 RAG 检索注入(降级空串)

`prd_gen_service.py` 加 `_retrieve_reference_context(session, section)`:

- query = `user_input + 章节名`[:200]
- POST `localhost:8000/api/query/stream`,collections=`["prd_history"]`,top_k=3,similarity_threshold=0.5
- 解析 SSE 提 sources,各截断 500 字
- 3 层 try/catch:`ConnectionError`(微服务未启)→空串,`Exception`→空串+log warning
- 无 sources →空串

`_build_collected_info_text` 改实例方法加 `current_section` + `rag_enabled` 参数。`simple_generate`/`generate_section` 调用处加 `rag_enabled`。

**降级路径**:无 prd_history 集合 → 检索返回空 → 注入空串 → PRD 生成正常进行,无参考。日志 `[PRDGen] RAG 检索无结果`,前端不报错。

### 0.4 飞书导出

`export_to_feishu(session_id)` 复用 `feishu_client.create_doc_xml(title, markdown)`,存 `feishu_doc_url` 到 session。
端点 `POST /api/prd/sessions/<id>/export/feishu`。前端"导出到飞书文档"按钮(sessionStatus=done 显示)。

### 0.5 前端 ragEnabled 开关

`PrdGen.tsx` 加 `useState(true)`,Checkbox "参考历史 PRD"。生成请求带 `rag_enabled`。

### 阶段 0 文件清单

| 操作 | 文件 |
|---|---|
| 修改 | `backend/routers/kb_manage.py` (+5 端点) |
| 修改 | `frontend/src/api/kbManage.ts` (+5 函数+类型) |
| 修改 | `backend/services/prd_gen_service.py` (+`_retrieve_reference_context`,改 `_build_collected_info_text`) |
| 修改 | `backend/routers/prd_gen.py` (+`/export/feishu` 端点) |
| 修改 | `frontend/src/pages/PrdGen.tsx` (+ragEnabled 开关+飞书按钮) |
| 修改 | `frontend/src/api/prdGen.ts` (+`exportPRDToFeishu`+rag_enabled 透传) |

### 阶段 0 验证

```bash
# 1. graph 代理(微服务跑起后)
curl 'http://localhost:5000/api/kb-manage/modules' | python -m json.tool
curl 'http://localhost:5000/api/kb-manage/graph/impact?node=ClusterConfigJobController&direction=in&depth=3' | python -m json.tool

# 2. RAG 降级(无 prd_history 集合时)
# 后端日志: [PRDGen] RAG 检索无结果: query="xxx"
# 生成正常进行,无报错

# 3. 飞书导出
# 点击"导出到飞书文档"→ 打开飞书文档 → 内容完整

# 4. tsc 零错误
cd frontend && npx tsc --noEmit
```

---

## 四、阶段 1:深度模式 Agent 2 上下文分析(依赖阶段 0)

### 1.1 model_router.py(双模型路由)

```python
class ModelRouter:
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
        if route_key in ('deep_agent_2', 'deep_agent_3'):
            return cls.MODEL_MAP[route_key]
        return user_model or cls.MODEL_MAP.get(route_key, 'deepseek-v4-flash')
```

Agent 2/3 强制 pro,其余随用户配置。

### 1.2 _retrieve_platform_context(session) — Agent 2 核心

调知识库图谱,组装上下文:

```python
def _retrieve_platform_context(self, session: dict) -> str:
    """
    调知识库图谱 API,组装平台上下文 + 影响范围预警。
    供 Agent 2 注入 prompt。
    """
    user_input = session.get('user_input', '') or ''
    # Step 1: 提功能关键词 → 匹配模块
    #    调 GET /api/kb-manage/modules 拿 12 模块清单
    #    LLM 或字符串匹配 user_input → module_name (如 "集群配置" → "集群配置管理")
    # Step 2: 拿架构快照
    #    GET /api/kb-manage/modules/{module_name} → controllers/apis/frontend_pages/external_deps
    # Step 3: 拿影响范围(incoming: 谁依赖该模块)
    #    GET /api/kb-manage/graph/impact?node={controller_name}&direction=in&depth=3
    #    多候选时返回全部(质量优先)
    # Step 4: 组装文本
    #    【平台架构快照】模块 X: controllers=[...], apis=[...], frontend_pages=[...]
    #    【影响范围预警】改该模块影响: {summary_by_type}
    #    ⚠️ 建议在 PRD 覆盖这些下游影响
```

3 层 try/catch:`ConnectionError`→空串降级(微服务挂,深度模式仍可跑,无图谱上下文),`Exception`→空串+log。

**降级**:无匹配模块 → 架构快照空 → 影响范围空 → 上下文仅 `【提示】未匹配到平台模块,基于需求自由设计`。Agent 2 仍运行。

### 阶段 1 文件清单

| 操作 | 文件 |
|---|---|
| 新建 | `backend/services/model_router.py` |
| 修改 | `backend/services/prd_gen_service.py` (+`_retrieve_platform_context`) |

### 阶段 1 验证

```python
# 单元:session.user_input="集群配置管理功能"
# → _retrieve_platform_context 返回非空,含架构快照 + 影响范围
# 微服务挂 → 返回空串,无报错
```

---

## 五、阶段 2:4 Agent 流水线 + 校验器 + 人工闸口(依赖阶段 1)

### 2.1 deep_agents.py — 4 Agent 节点

每个 Agent = `prompt + llm.chat_stream + _parse_json_safe`,独立函数,接 state 返回新 state。

```python
# Agent 1: 需求萃取(flash)
def agent1_extract(state, session, llm) -> dict:
    """多源融合(A1文字/A2妙记/A3文件) → 结构化需求 + 冲突清单
    输入: user_input + collected_info + minutes_extract + files
    输出: {requirements: {...}, conflicts: [...], gaps: [...]}
    """

# Agent 2: 上下文分析(pro,调KB)
def agent2_analyze(state, session, llm) -> dict:
    """调 _retrieve_platform_context → 平台上下文 + 影响范围
    输出: {platform_snapshot: str, impact_analysis: str, missing_deps: [...]}
    """

# Agent 3: 功能规格(pro)
def agent3_spec(state, session, llm) -> dict:
    """结构化功能规格 + 验收标准
    输入: Agent1/2 输出
    输出: {features: [...], user_stories: [...], acceptance_criteria: [...]}
    """

# Agent 4: PRD 撰写(flash)
def agent4_write(state, session, llm) -> dict:
    """模板组装 → MD PRD + spec_schema.json
    输出: {prd_markdown: str, spec: {...}}
    """
```

### 2.2 validators.py — 6 校验器

```python
def validate_schema(agent1_out) -> list[Issue]:
    """必填字段完整"""
def validate_scope(agent3_out, user_input) -> list[Issue]:
    """范围蔓延检测"""
def validate_citation(agent3_out) -> list[Issue]:
    """防幻觉:内容是否有依据"""
def validate_acceptance(agent3_out) -> list[Issue]:
    """功能点是否都有验收标准"""
def validate_permission(agent3_out) -> list[Issue]:
    """是否遗漏权限设计"""
def validate_risk(agent4_out) -> list[Issue]:
    """是否缺失异常/性能/审计"""

# Issue = {level: 'error'|'warn', field: str, message: str, action: 'retry_agent1'|'mark'|'user_decide'}
```

### 2.3 deep_generate() — SSE 状态机编排

```python
def deep_generate(self, session_id, api_key, base_url, model, rag_enabled):
    """深度模式 SSE 流式编排

    状态流转: INIT → AGENT1 → V_SCHEMA → GATE1 → AGENT2 → GATE2
              → V_SCOPE/CITATION/ACCEPT/PERM → AGENT3 → GATE3
              → AGENT4 → V_RISK → DONE
    """
    state = DeepMode.INIT
    artifacts = {}

    # Agent 1
    yield sse_event('progress', {'agent': 'agent1', 'message': '需求萃取中...'})
    artifacts['agent1'] = agent1_extract(state, session, llm)
    yield sse_event('agent_complete', {'agent': 'agent1', 'data': artifacts['agent1']})

    # V: Schema
    issues = validate_schema(artifacts['agent1'])
    if issues:
        yield sse_event('validation', {'validator': 'schema', 'issues': issues})
        # 回退 Agent 1 (最多 2 次)
    yield sse_event('gate', {'gate': 'conflict', 'conflicts': artifacts['agent1']['conflicts']})
    # 暂停,等前端 POST /sessions/<id>/deep/approve gate=conflict
    # ... (Flask SSE generator 挂起,前端 POST 触发恢复)
```

### 2.4 人工闸口 — SSE 暂停 + POST 恢复

```
GET /api/prd/sessions/<id>/deep-generate  (SSE,流式)
  → yield gate 事件后 generator 挂起(等恢复信号)

POST /api/prd/sessions/<id>/deep/approve
  body: {gate: 'conflict'|'impact'|'spec', approved: bool, modifications: str}
  → 唤醒 generator 继续
```

实现:`threading.Event` + 全局 dict 存 `{session_id: Event}`,POST set,generator wait。

### 2.5 前端深度模式 UI

`PrdGen.tsx` 加:
- 模式 Radio: 简单/中等/深度
- 深度选中 → 显示 Agent 流水线进度条(4 Agent + 3 Gate)
- Gate 事件 → 弹 Modal 显示冲突/影响/规格,用户确认/修改/驳回
- Agent 4 完成 → 显示 PRD + spec_schema.json + "生成原型"按钮(阶段 3)

### 阶段 2 文件清单

| 操作 | 文件 |
|---|---|
| 新建 | `backend/services/deep_agents.py` (4 Agent) |
| 新建 | `backend/services/validators.py` (6 校验器) |
| 修改 | `backend/services/prd_gen_service.py` (+`deep_generate`) |
| 修改 | `backend/routers/prd_gen.py` (+`/deep-generate` SSE + `/deep/approve`) |
| 修改 | `frontend/src/pages/PrdGen.tsx` (+深度模式 UI) |
| 修改 | `frontend/src/api/prdGen.ts` (+`deepGenerate` SSE + `approveGate`) |
| 修改 | `backend/services/db.py` (`prd_sessions` 加 `deep_state`+`deep_artifacts` 列 migration) |

### 阶段 2 验证

```bash
# 1. 端到端: 输入需求 → 4 Agent 跑完 → 3 闸口确认 → PRD 输出
# 2. 微服务挂: Agent2 _retrieve_platform_context 降级空串,深度模式仍跑完
# 3. 校验器回退: 故意输入模糊需求 → Schema validator 报 issue → Agent1 重跑
# 4. tsc 零错误
```

---

## 六、阶段 3:原型生成(依赖阶段 2)

### 3.1 registry.json 取数(直接 HTTP 读微服务)

`backend/routers/prd_gen.py` 加端点:

```python
@prd_gen_bp.route('/component-registry', methods=['GET'])
def get_component_registry():
    """代理读微服务 component_registry.json,供前端 RenderEngine"""
    try:
        resp = requests.get('http://localhost:8000/api/admin/component-registry',
                            timeout=10)
        # 或直接读文件: open('../ju/data/component_registry.json')
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {'error': '微服务未启动,原型功能不可用'}, 503
```

**降级**:微服务挂 → 503,前端提示"微服务未启动,无法生成原型"。

### 3.2 RenderEngine.tsx — 动态渲染

```tsx
function RenderEngine({ spec, registry }: { spec: ComponentSchema[], registry: Component[] }) {
  return spec.map(node => {
    // 从 registry 找匹配组件(优先 project/business,带 props)
    const comp = findInRegistry(node.component, registry)
    || COMPONENT_MAP[node.component]  // antd 原生 fallback
    return <comp.Component {...node.props} />
  })
}
```

风格对齐:优先 `category=project/business`(带真实 props),antd 原生走官方组件。

### 3.3 spec_generator.py — Machine-Readable Spec

Agent 4 同步输出:

```json
{
  "feature": "...",
  "endpoints": [{path, method, auth, request, response}],
  "dataModels": [{name, fields}],
  "businessRules": ["..."],
  "uiSpec": [{"component": "Table", "props": {...}}]  // 供 RenderEngine
}
```

### 阶段 3 文件清单

| 操作 | 文件 |
|---|---|
| 新建 | `frontend/src/components/RenderEngine.tsx` |
| 新建 | `backend/services/spec_generator.py` |
| 修改 | `backend/routers/prd_gen.py` (+`/component-registry` 代理) |
| 修改 | `backend/services/deep_agents.py` (Agent4 输出 spec) |
| 修改 | `frontend/src/pages/PrdGen.tsx` (+原型预览面板) |
| 修改 | `frontend/src/api/prdGen.ts` (+`getComponentRegistry`) |

### 阶段 3 验证

```bash
# 1. Agent4 输出 spec 含 uiSpec
# 2. RenderEngine 读 registry 渲染原型页面
# 3. 微服务挂 → 503 降级提示
# 4. 原型组件风格与平台一致(用 project/business 组件,非裸 antd)
```

---

## 七、阶段 4:知识库侧收尾(并行,不阻塞中控台)

知识库 `KB_DEEP_MODE_PLAN.md` 残留:

| 项 | 状态 | 备注 |
|---|---|---|
| B4 防腐(incremental_update 集成 component_extractor/linker) | ⏳ | 与中控台并行 |
| 5 个测试文件 | ⏳ | test_graph_query/test_backend_call_linker/test_platform_module_index/test_component_extractor/test_admin_graph_api |
| 整体回归(图谱/Chroma 零丢失 + 检索不退化) | ⏳ | |

不阻塞中控台阶段 0-3,知识库侧独立完成。

---

## 八、排期

| 阶段 | 内容 | 预估 | 依赖 | 状态 |
|---|---|---|---|---|
| 0 | kb_manage graph 代理 + RAG 基建 + 飞书导出 | 2 天 | 无 | ✅ 完成 |
| 1 | model_router + Agent2 上下文分析 | 1.5 天 | 0 | ✅ 完成 |
| 2a | db migration + Agent1/2 + deep_generate 骨架 | 2 天 | 1 | ✅ 完成 |
| 2b | Agent3/4 + 6 校验器 + 3 闸口 + 前端深度 UI | 2 天 | 2a | ✅ 完成 |
| 3 | RenderEngine + registry.json + 原型预览 | 1 天 | 2b | ✅ 完成 |
| — | 优化: Agent1 伪 Agentic(双 pass+KB 查询) | 0.5 天 | 2b | ✅ 完成 |
| — | 优化: 闸口结构化编辑 + Agent 命名 | 0.5 天 | 2b | ✅ 完成 |
| — | 优化: Agent5 原型生成(HTML 直接输出+组件库) | 1 天 | 2b | ✅ 完成 |
| — | 优化: Agent1 审核闸口 + 原型手动触发 | 0.5 天 | 2b | ✅ 完成 |
| 4 | 知识库 B4 + 测试 + 回归(并行) | 2 天 | 无 | ✅ 用户确认完成 |
| | **合计(中控台串行)** | **~11 天** | | ✅ **全部完成** |

---

## 九、降级链路(关键)

| 故障 | 降级行为 |
|---|---|
| 微服务 :8000 挂 | RAG 空串 + 图谱上下文空串 + registry 503。PRD 仍可生成(无参考/无图谱/无原型) |
| 无 prd_history 集合 | RAG 检索返回空 → 注入空串。日志提示,前端无感 |
| Agent2 匹配不到模块 | 架构快照空 → 影响范围空 → Agent2 提示"未匹配模块,自由设计" |
| LLM JSON 解析失败 | `_parse_json_safe` 5 层容错,失败用默认值 |
| 校验器报 issue | error 级 → 回退 Agent 重跑(≤2 次);warn 级 → 标记继续 |

**核心原则**:深度模式任一环节降级,不阻塞 PRD 生成,仅损失对应能力。

---

## 十、复用点

| 现有代码 | 复用方式 |
|---|---|
| `kb_manage.py` `_proxy_get` | 5 graph 端点代理 |
| `feishu_client.create_doc_xml` | 飞书导出 |
| `sse_helpers` | 深度模式 SSE 流式 + 闸口挂起 |
| `_parse_json_safe` | Agent 结构化输出 |
| `LLMConfigProvider` + `inject_llm_config` | 模型配置注入 |
| `prd_sessions` 表 | state 持久化(加 2 列) |

---

## 十一、已知改进点

### 真 Agentic（后续增强）

Agent1 当前使用伪 Agentic（2-pass：先问 KB 再产最终版）。可以升级为真 Agentic：

1. LLMClient 加 OpenAI function calling 支持 → Agent 可自主调 `query_kb_agent(question)` / `query_graph(node, direction)` / `search_docs(keyword)` 等工具
2. Agent1/2/3 共享同一套 tools，Agent 推理中自主判断"我需要查资料"→ tool_call → 执行 → 结果回喂 → 继续推理
3. ≤3 轮循环防 runaway

**升级成本**:额外 1-2 天（tool loop 基础设施 + prompt 调整）。
**触发信号**:伪 Agentic 80% 场景够用，当需要更灵活的跨模块推理时升级。

### 缺陷 1：原型生成未切实参考页面布局和组件

**现状**:Agent5 prompt 虽然注入了 `design_layouts` 和 `component_registry`，但实际输出中几乎没有使用平台页面布局和组件。

**根因**:
- 模块匹配用关键词(如"模型训练"→`modalTraining`)，但用户需求文本可能不包含准确的模块名
- LLM 输出的结构化 sections(table/stat_grid/diff)与平台实际页面(DataTable/FilterBar/Tabs)差异大
- `prototype_renderer.py` 的 section types(table/stat_grid/diff)不够丰富，无法表达真实 UI

**改进方向**:
- 页面模板化：将 `design_layouts` 中匹配到的页面直接作为 section 模板，LLM 只填充数据不决定布局
- 模块匹配用 LLM 分类替代关键词匹配（"版本回滚" → "模型中心"）
- 匹配到的页面布局作为预设 section 结构，LLM 只需填入具体列名和数据

### 缺陷 2：Agent4 生成的 PRD 质量差

**现状**:Agent1/2/3 的产出质量可接受，但 Agent4 生成的 PRD Markdown 内容简陋、不够具体、与项目平台差异大。表现为：
- PRD 只有开头几句话（被截断或 Agent4 输出不完整）
- 内容泛泛，没有体现 Agent1 萃取的具体需求和 Agent2 的平台上下文
- 未充分利用 Agent3 产出的详细 features/user_stories/data_models

**根因分析**:
- Agent4 prompt 中 Agent1/2/3 的上下文以 JSON 字符串形式注入，LLM 阅读和理解效率低
- Agent4 用 flash 模型(max_tokens=12288)，复杂推理能力不足，难以综合多源长上下文
- prompt 未明确要求"引用 Agent1/2/3 的具体内容"，LLM 倾向于泛泛而谈
- `max_tokens=12288` 可能不足以生成完整 9 章节 PRD

**改进方向**:
- Agent4 改用 pro 模型（与 Agent2/3 相同），提高综合推理能力
- 将 Agent1/2/3 的产出转为更易读的自然语言摘要而非原始 JSON
- prompt 明确要求每个章节必须引用 Agent1 的具体需求点和 Agent2 的平台上下文
- 增加 `max_tokens` 到 16384 以上
- 考虑分章节生成（类似简单模式的逐章节 SSE），而非一次性输出全文
