# 关键发现

## 飞书 Device Code Flow 需要 app_secret 🚫

**发现时间：** 2026-06-23 16:00-17:40

**错误假设：** Device Code Flow 只需要 app_id，不需要 app_secret

**实际验证：**
1. 端点 `/open-apis/auth/v3/device/code` 返回 404（根本不是 `open-apis` 下的接口）
2. 正确端点路径（从 lark-cli 日志中发现）：
   - `POST accounts.feishu.cn/oauth/v1/device_authorization`（获取 device_code）
   - `POST open.feishu.cn/open-apis/authen/v2/oauth/token`（换取 token）
3. Device Code Flow 使用的是 **Basic Auth**：`base64(app_id:app_secret)` 放在 Authorization header
4. **app_secret 不能绕过** — 飞书所有 OAuth 流程（含 Device Code Flow）都需要

**结论：** ⚠️ 任何声称"Device Code Flow 不需要 app_secret"的说法都是错误的（针对飞书平台）。

---

## `lark-cli api` 是最佳飞书 REST 网关 ✅

**发现时间：** 2026-06-23 17:30

**验证内容：**
- `lark-cli api GET|POST /open-apis/...` 是通用 REST 网关
- 自动从 macOS keychain 读取 app_secret
- 自动管理 token（刷新、续期）
- subprocess 继承 keychain 权限
- 已有授权用户（黎国友），token 会自动续期至 6-30

**适用场景：** 任何飞书 Open API 调用都应走 `lark-cli api`

---

## 飞书妙记 API 调用的正确路径

- `GET /open-apis/minutes/v1/minutes/{minute_token}` — 获取妙记基础信息（标题、时长等）
  - 注意：返回结构为 `data.minute.title` 而非 `data.title`
- `GET /open-apis/minutes/v1/minutes/{minute_token}/transcript` — 直接获取逐字稿内容（text/plain）
  - lark-cli 保存为文件，需用 `--output` + 相对路径
  - `--output` 只接受**相对路径**（需配合 `cwd=tmpdir`）
- `POST /open-apis/vc/v1/minutes/{minute_token}/notes` — **已失效**（返回 404，不是公开 API）
- `lark-cli minutes minutes get --params '{"minute_token":"..."}'` — 也可用 lark-cli 原生命令

注意：妙记搜索需要额外 scope `minutes:minutes.search:read`，当前用户未授权此 scope。

---

## Flask 子进程必须注入 `LARKSUITE_CLI_CONFIG_DIR`

**发现时间：** 2026-06-23 18:00

**问题：** Flask 通过 `subprocess.run(['lark-cli', 'api', ...])` 调用时，lark-cli 使用默认配置而非指定的 bot 配置，导致 `unauthorized [99991679]: scope not covered`

**根因：** lark-cli 通过 `LARKSUITE_CLI_CONFIG_DIR` 环境变量确定配置目录，Flask 子进程未继承此变量

**修复：** 在 `feishu_client.py` 中定义 `_lark_env()` 函数返回注入后的环境变量，所有 `subprocess.run` 调用传入 `env=_lark_env()`

```python
_LARK_CONFIG_DIR = "/Users/admin/.dewuclaw/lark-cli-config/cli_aa847daba1bc1bb3"

def _lark_env() -> dict:
    env = os.environ.copy()
    env["LARKSUITE_CLI_CONFIG_DIR"] = _LARK_CONFIG_DIR
    return env
```

---

## 飞书多用户 token 管理的正确做法

**错误做法：** 自行实现 Device Code Flow 管理多用户 token（需要 app_secret）

**正确做法：** 用 `lark-cli auth login` 新增授权用户（但 agent 上下文中会被系统拦截），或让用户在飞书中与 bot 对话完成授权。所有 API 调用走 `lark-cli api`，由 lark-cli 自动管理 token 选择。

当前已有用户：黎国友（ou_5df3accc2134f25bbe480cb9134b032b）

---

## SSE 请求头注入方式

**修复时间：** 2026-06-23

**问题：** SSE 请求和 axios 请求从不同 localStorage key 读取 LLM 配置，导致一端配置了但另一端没有

**修复：** 统一从 `ai_center_llm_config` 读取，SSE 用 `EventSource` 的 `headers` 属性（需 fetch + ReadableStream polyfill 或 XHR），axios 用拦截器

---

## `lark-cli docs +create --api-version v2 --content` 直接创建含内容的文档

**发现时间：** 2026-06-23 17:45

**示例：** 
```bash
lark-cli docs +create --api-version v2 --content '<title>标题</title><h1 sec="auto">章节</h1><p>内容</p>'
```

返回包含 `document_id` 和 `url` 的 JSON，直接可用。

---

## ★ 后端导出和写入时合计行需手动追加

**发现时间：** 2026-06-24 18:03

**问题**：导出的 xlsx 和写飞书多维表格中的数据只有各项目行，没有"合计"汇总行。

**根因**：前端用 `computeSummary()` 计算 `summaryRow` 并只在页面表格中展示，但 `handleWriteBitable` 和 `handleExport` 只发了 `result.rows`（各项目原始数据），没包含合计行。后端 xlsx 导出和 bitable 写入也只在传入的数据上操作，不会自动追加。

**修复**：在 `api/iterationStats.ts` 新增 `computeRawSummary()`（基于 `RawStatsRow[]` 计算合计行，返回 `RawStatsRow` 类型），`handleWriteBitable` 和 `handleExport` 均 `[...result.rows, computeRawSummary(result.rows)]`。

**bitable 写入特殊处理**：合计行 `project_name="合计"` 不会匹配到任何飞书记录，自然进入 `unmatched` 列表，但不会阻塞其他项目的更新。

**教训**：前端计算的汇总/统计行如果不是后端返回的，就必须在写入和导出时手动追加。不要假设展示层和导出层共享同一份数据。

---

## ★ bitable TL 字段返回的是 mention 格式 list

**发现时间：** 2026-06-24 18:03

**问题**：TL 列显示为 `"@黎国友"` 而不是 `"黎国友"`。

**根因**：飞书多维表格的 TL （人员列）通过 bitable API 返回时是 list 格式，每个 item 是 `{"text": "@姓名", "type": "mention", ...}`。代码只拼接了 `item["text"]`，没有去除 `@` 前缀。

**修复**：`.lstrip("@")` 处理每个文本片段。

**教训**：飞书多维表格的人员字段类型（User/Mention），通过 bitable API 读取时是 list of rich text objects，而不是纯文本。无论哪个端点都要对齐清洗逻辑——`_fetch_bitable_project_map()` 和 `/projects` 端点的 TL 清洗是重复逻辑，必须保持一致。

---

## ★ 后端返回字段名必须与前端接口定义一致

**发现时间：** 2026-06-24 17:43

**问题**：飞书写入完成后 Alert 显示"成功更新飞书多维表格 — undefined 条记录"。

**根因**：前端 TypeScript 接口 `BitableWriteResult` 定义的是 `updated_count`，但后端 `batch_update_bitable()` 返回的 dict 中字段名是 `"updated"`。`res.updated_count` 是 `undefined`。

**教训**：Flask 后端没有类型系统，返回的 dict 字段名很容易与前端接口定义产生偏差。在写前端 API 封装层代码时，必须逐字段对照后端实际返回的 JSON。

**检查方法**：在浏览器控制台 `console.log(res)` 或用 Postman 先调一次后端接口确认返回结构，再写前端代码。

---

## ★ 后端 xlsx 导出时 ratio 字段类型必须处理

**发现时间：** 2026-06-24 17:43

**问题**：导出 xlsx 时 `f'{ps.get("aicoding_ratio", 0):.2f}%'` 抛出 `ValueError: Unknown format code 'f' for object of type 'str'`。

**根因**：`aicoding_ratio` 从上传解析后得到的是字符串格式如 `"25.0%"`（带百分号），但导出代码假设它是数值并用 `:.2f` 格式化。

**修复**：对 ratio 字段先做类型判断，字符串直接使用，数值再格式化。
```python
a_ratio = ps.get("aicoding_ratio", "")
if isinstance(a_ratio, (int, float)):
    a_ratio = f"{a_ratio:.1f}%"
```

**教训**：同一个项目中的数据流（上传→展示→写入→导出）中，每个环节的字段格式必须一致或做转型。特别是 ratio 这种在显示层和计算层有不同表示方式的字段。上传层用字符串格式时，导出层不能假设是数值。

---

## ★ 前端 POST 传 `rows` 但后端写死 `data["project_stats"]`

**发现时间：** 2026-06-24 17:43

**问题**：导出 xlsx 报 500，错误信息为 `TypeError: 'NoneType' object is not iterable`。

**根因**：导出端点已有兼容处理 `project_stats = data.get("project_stats") or data.get("rows", [])` 并将结果赋值给 `project_stats` 变量，但遍历循环中写的是 `for row_idx, ps in enumerate(data["project_stats"], 2):`。当请求 JSON 中只有 `"rows"` 没有 `"project_stats"` 时，`data["project_stats"]` 为 `None` → 500。

**教训**：定义局部变量后一定要在后续所有地方使用该变量，不要混用局部变量和 `data[...]` 直接访问。建议在端点入口处就统一字段名：
```python
# 统一为 project_stats，后续全部用 project_stats
data = request.get_json(silent=True)
project_stats = data.get("project_stats") or data.get("rows", [])
# ... 接下来每处都用 project_stats，不再碰 data
```

---

## ★ 飞书 bitable 字段格式多样性

**发现时间：** 2026-06-24 (Phase 3 实现期间)

**教训**：飞书多维表格的字段值可能是多种格式：纯文本、Markdown 链接 `[name](url)`、@提及格式 `[@name(英文)](url)`、甚至是数组 `[{text: "...", link: "..."}, ...]`

- 不能简单用 `str.replace()` 或单一正则——必须多层兜底：先检测字符串类型，再尝试多种格式匹配
- 项目名称字段：`[95分算法 5.93（0529）](iwork_url)` → 提取 `[...](` 中间的部分
- TL 字段：`[@岱锋(Terralloy Yu)](avatar_url)` → 提取 `[@?...](` 中的中文名（去掉 @ 和英文名后缀）
- 好的做法：先打印原始值的 `repr()` 看清楚格式再写解析逻辑

---

## ★ 项目名称模糊匹配策略

**发现时间：** 2026-06-24 (Phase 3 实现期间)

bitable 中的项目名称包含版本信息（`5.93（0529）Dsearch搜索引擎版本迭代`），但用户上传的 xlsx 只包含简称（`Dsearch搜索引擎版本迭代`）

**解决方案**：双层匹配策略。第一层精确匹配，第二层子串包含匹配（`pname in fullname or fullname in pname`）

同时返回 `available_projects` 和 `unmatched` 列表，方便前端 debug。

---

## ★ 项目名称清洗: `_extract_project_name()` 统一函数 (2026-06-24 20:22)

**背景**：3 处代码重复实现了类似的清洗逻辑（markdown 链接提取 + 富文本数组拼接），且都未处理版本前缀

**设计模式**：
1. 先处理 markdown 链接格式 `[name](url)` → 提取 name
2. 再处理富文本数组 → 拼接 text
3. 最后用正则 `^\d+\.\d+[（(]\d+[）)]\s*` 去除版本前缀（如 `5.93（0529）`）

**优点**：一处定义，三处一致使用，避免后续修改遗漏。正则只匹配开头，防止误删项目名中间的数字。

**涉及的 3 处代码**：
- `_fetch_bitable_project_map()` — bitable 记录 → API 响应
- `/projects` 端点 — bitable 记录 → 项目列表
- write-bitable 中 `exact_map` 构建 — bitable 记录 → 匹配映射

---

## ★ 合计行自动创建到飞书：`create_bitable_record()` (2026-06-24 20:22)

**问题**：write-bitable 通过匹配 project_name 到 bitable records 来更新现有记录，而"合计"行不匹配任何 bitable record → 落入 unmatched → 不写入

**解决方案**：在 write-bitable 检测 unmatched 中 project_name="合计" 时，自动调用 `create_bitable_record()` 创建记录

**`create_bitable_record` 实现的要点**：
- 使用 `lark-cli base +record-batch-create --json '{"fields":[...],"rows":[[...]]}'` 
- fields 是列名数组（需包含"项目名称""TL"等所有字段）
- rows 是行值数组（按 fields 顺序）
- 占比字段必须格式化为字符串（如"68.57%"），不能传数字
- 新建记录由飞书自动分配 record_id，返回 JSON 中包含
- 后续处理：先创建记录拿到 record_id → 添加到 records_data → 执行 batch_update_bitable 写入统计值

---

## `edit_file` 空字符串 old_text 会损坏文件 🚨

**发现时间：** 2026-06-24 (多次触发)

使用 `edit_file` 时若 `old_text=""`（空字符串），工具会替换所有字符间位置，导致文件从 ~150 行膨胀到 ~465,692 行（35MB）

**教训**: `edit_file` 的 old_text 参数**不能为空字符串**。要追加内容应使用 `write_file` 读取全部内容后修改再写入，或确保 old_text 是文件中确实存在的非空字符串。

**恢复方法**: 使用 `write_file` 重新写入正确内容即可恢复。

**此 bug 触发了 3 次**（MEMORY.md 79K行、progress.md 794行、findings.md 4348行、BLOG_RECORD.md 23K行），每次都用 `write_file` 全文重写恢复。

---

## Ant Design Dragger 的 showUploadList 陷阱

**发现时间：** 2026-06-24 ~16:26

`Dragger` 组件的 `showUploadList` 默认 `true`，意味着拖拽区本身会渲染文件列表。在紧凑布局中，Dragger 的文件列表会突破 `maxHeight` 限制，子元素撑大容器。

**解决方案**：任何需要固定尺寸的拖拽上传区，都应该设置 `showUploadList={false}`，把文件列表移到外部用紧凑组件（Tag/List）展示。

---

## 文档同步自动化脚本设计 (doc_sync.sh)

**创建时间：** 2026-06-24 ~14:30

核心思路：不是靠"记得去更新"，而是靠"被强制检查"——类似 pre-commit hook 或 CI 门禁。

**实现三件套**：
1. 脚本 (`tools/doc_sync.sh`) — 比较代码文件的最新修改时间 vs 每个文档的修改时间
2. 硬规则 (AGENTS.md) — "完成前强制检查"规则
3. 提示位 (MEMORY.md 头部 banner)

**设计逻辑**：代码更新在前 / 文档更新在后 = 已同步；反过来 = 过期。exit code 1 可做程序化阻断。

**已知局限**：doc_sync.sh 只看文件修改时间戳，不能区分"文档内容已覆盖该修改"和"文档根本没提这个修改"。需要手动阅读过期文档确认是否真正需要更新。

---

## 项目原有骨架状态 (Phase 3 开始前)

| 层 | 文件 | 状态 |
|----|------|------|
| backend | `routers/iteration_stats.py` | 3 个 stub (upload/crawl/write-bitable 全部返回 501) |
| backend | `models.py` | 已有 IterStatsCrawlRequest, IterStatsUploadRequest |
| frontend | `pages/IterationStats.tsx` | UI stub (mode switch + upload/crawl tabs) |
| frontend | `api/iterationStats.ts` | 3 个 API 函数 (uploadStats/crawlStats/writeBitable) |
| App | `App.tsx` | 已注册 `/iteration-stats` 路由 |
| AppLayout | `components/AppLayout.tsx` | 侧边栏已有"迭代数据统计"入口 |

---

## 桌面 iteration-stats Skill 参考文件

| 文件 | 行数 | 作用 |
|------|------|------|
| `scripts/stats_from_xlsx.py` | ~530 | 核心：读 xlsx → 列头匹配 → 统计 6 项指标 → 一致性校验 → 输出表格 |
| `scripts/update_feishu_table.py` | ~160 | 用 lark-cli base +record-upsert 写回飞书多维表格 |
| `scripts/calculate_stats_engine.py` | ~300 | 旧版浏览器数据统计引擎（参考用） |
| `references/statistics_rules.md` | | 统计规则详细定义 |
| `references/field_mapping.md` | | 飞书多维表格字段映射（base_token=B5exbr9..., table_id=tbllFUF...） |
| `references/error_codes.md` | | 错误码 E001-E005 / W001-W003 |
| `references/api_reference.md` | | API 参考 |

---

## stats_engine.py 核心设计

- `parse_project_xlsx(filepath)` → 读取 xlsx，自动识别列
- `find_engineering_hour_columns(df)` → 自动匹配含"工程"+"估时/工时"的列
- `check_responsible(row)` → 检查是否有负责人
- `calculate_stats(df)` → 逐行统计: 总需求, 完全排期数, 算法工程需求数, AIcoding数, SDD数, 端到端数, 各项占比
- `consistency_check(stats)` → 校验: 完全排期 >= 工程 >= AIcoding >= SDD
- 占比公式: AI占比 = AIcoding/工程 (分母0则0), SDD占比 = SDD/AIcoding (分母0则0)
- 列名匹配要用优先级列表：`["自定义标签", "自...标签", "标签", "需求标签"]`
- 从桌面 skill 移植时列名必须逐行对照，不能凭记忆缩写

---

## Bitable 字段 ID 映射 (base_token=B5exbr9..., table_id=tbllFUF...)

| 字段 | ID |
|------|----|
| 项目名称 | fld7QjxfNI |
| TL | fld4DBSjUt |
| 算法工程需求 | fldAg8vyIE |
| AICoding占比 | fldHGhJD6M |
| AIcoding数 | fldHTXRfxN |
| SDD占比 | fldJ6fNeqH |
| SDD数 | fldkYOh0uy |
| 端到端 | fldOpiGKkk |
| 总需求数 | fldygU4n03 |

---

## 跟进人提取最终规则 (Prompt 定版)

1. **主动认领** ("我来/我负责/我去看") → **仅说话人本人**
2. **找人/协作** ("找XX了解/与XX对齐/和XX确认/跟XX沟通") → **说话人本人 + 被提及者 均提取**
3. **移交** ("给XX验收/提交给XX/让XX看") → **仅被提及者**
4. 未明确提到任何人 → 留空 (标注 ⚠️)

---

## 描述清洗三类场景

- **找人型**: "线下找广智了解JVM参数" → "线下了解JVM参数"
- **协作型**: "与瘦子对齐配置" → "对齐配置"
- **移交型**: "给云锦验收" → "验收"

---

## ★ 直接 HTTP API 调用替代 subprocess 脚本 (Phase 4, 2026-06-24)

**背景**：`ai-measure-query` skill 中的 `ai_measure.py` / `dept_stats.py` / `skills_query.py` 等脚本输出的是格式化表格文本（非 JSON），无法直接被 Python 解析。

**方案对比**：

| 方案 | 优点 | 缺点 |
|------|------|------|
| subprocess 调用脚本，正则解析表格 | 复用已有代码 | 脆弱（表格格式变化就崩）、难调试、跨平台问题 |
| **直接 HTTP 调用 API** | 稳定、返回 JSON、可控 | 需要独立实现 HTTP 客户端、了解 API 结构 |
| 脚本改输出为 JSON | 灵活 | 会修改 skill 脚本、可能导致 skill 使用者受影响 |

**结论**：直接 HTTP 调用 REST API（`ep-copilot2` 的 drilldown、`skills.dewu-inc.com`）更可靠。原脚本作为参考备份保留在 `ai_measure_scripts/` 目录。

**涉及 API**：
- `{ep_host}/v1/ai-tool-measure/drilldown` — 查询 AI 编程工具使用明细（按人/项目/时间）
- `{skills_host}/v1/skills` — 查询技能列表（按贡献人聚合）

**Skills API 的输出结构**：返回自描述 schema 而非固定字段，需要在客户端动态映射。

---

## ★ Phase 5 知识库问答实际实现与方案差异 (2026-06-30)

**实际实现与方案文档的 5 个差异**：

| 方案文档 | 实际实现 | 原因 |
|---------|---------|------|
| `services/kb_agent.py` 知识库 Agent | 无，后端纯 HTTP 代理 | 已有无矩2.0 微服务，无需重复调 LLM |
| `components/ChatMessage.tsx` | 消息渲染内联在 Chat.tsx | 组件简单无需提取 |
| 左侧会话列表 + 右侧对话区 | 单屏对话（无历史列表） | MVP 阶段简化 |
| API 调用走 `api/chat.ts`（axios） | Chat.tsx 直接用原生 fetch | 避免 axios 拦截器干扰 SSE 流式 |

**教训**：方案文档只是起点，实际开发时会发现更简单/更合适的方案。如果发现偏离，应在改动完成后立刻更新方案文档，避免文档和代码长期不一致。

**发现时间**：2026-06-30 (Phase 4 AI 编程数据报告调试)

**问题**：active_rate 模块数据正常返回但前端显示"查询失败"。Console 输出 `completedRef` 缺 1 个，后端 curl 测试 4 模块全部成功。

**根因**：`sse.ts` 按 `\n` 逐行解析。当 `section_complete` 事件 payload 跨 TCP chunk 时，截断的 JSON 行 `JSON.parse` 失败 → 静默丢弃。后续 chunk 中 `event:` 覆盖 `eventType`，残留 data 被错误分发。

```
Chunk 1: event: section_complete\ndata: {"section":"active_rate","rows":[{"name":"大怪兽(Danie
                                                ↑ JSON 中断 → 解析失败 → 丢弃
Chunk 2: l)",...]}\n\nevent: progress\ndata: ...
         ↑ 这里的 event: 覆盖 eventType，后续 data 被误匹配
```

**修复**：解析器按 `\n\n`（SSE 规范事件分隔符）切分，保证始终拿到完整事件块后再解析内部字段。

```javascript
const parts = buffer.split('\n\n')
buffer = parts.pop() || ''
for (const part of parts) {
    const {eventType, dataStr} = parseSseBlock(part)
    // dataStr 完整 → JSON.parse 不会失败
}
```

**教训**：手写 SSE 解析器时不要按 `\n` 逐行匹配。必须按 `\n\n` 边界切分事件块，再解析块内的 `event:` 和 `data:`。这是 SS 规范的基础要求，不是可选优化。

**涉及的 3 个修复**：
1. `sse.ts` — 解析器重写（按 `\n\n` 切分）
2. `sse_helpers.py` — 使用 `stream_with_context` 确保实时推送
3. `AiMeasure.tsx` — `completedRef` 避免 React batch 覆盖状态

**发现时间**：2026-06-24 (Phase 4 实现期间)

**问题**：SSE 的事件流使用 `event:` 字段命名，前后端必须完全一致。稍有拼写差异（如 `section_complete` vs `sectionComplete`）就会导致前端 `addEventListener` 收不到事件。

**本次采用的命名约定**：
- `progress` — 模块执行中（含 `section` + `message`）
- `section_complete` — 模块完成（含 `section`, `title`, `row_count`, `markdown`, `status: "complete"`）
- `section_error` — 模块出错（含 `section`, `message`, `status: "error"`）
- `complete` — 全部完成（含 `report_markdown`, `sections_completed`, `total_sections`）

**SSE 在 Flask 中的实现**：
```python
from flask import Response, stream_with_context

def generate():
    yield f"event: progress\ndata: {json.dumps(data)}\n\n"
    yield f"event: complete\ndata: {json.dumps(data)}\n\n"

return Response(stream_with_context(generate()), mimetype='text/event-stream')
```

**前端使用现有 `streamRequest`**（来自 `utils/sse.ts`）：
- 传入 callbacks: `{onProgress, onSectionComplete, onSectionError, onComplete, onError}`
- streamRequest 内部解析 `event:` 和 `data:` 并分发到对应回调

---

## 飞书文档写入：Markdown→XML 简化转换

**发现时间**：2026-06-24 (Phase 4 实现期间)

**问题**：`feishu_client.create_doc_xml()` 接受 XML 格式内容，但报告生成的是 Markdown。

**转换策略**（不求 100% 完美，MVP 够用）：
- `# ` → `<h1>`
- `## ` → `<h2>`
- `### ` → `<h3>`
- `- ` → `<li>`
- 表格 `|---|` → `<table><tr><td>...</td></tr></table>`（关键：先拆表头行和分隔行，再拆数据行）
- 加粗 `**text**` → `<strong>text</strong>`
- 简单文本段落 → `<p>text</p>`

**注意**：飞书 docx 不支持跨行合并（colspan/rowspan），表格中数据跨列时需要重复值。

**教训**：不要在 report_generator 里直接把 Markdown 转 XML，而是让 report_generator 返回结构化数据（`section_rows`），write-to-feishu 端点再根据数据构建 XML。这样数据层和展示层解耦，也便于未来改报告格式。

---

## TL 固定名单硬编码 (Phase 4, 2026-06-24)

**背景**：AI 编程数据报告中需要按 TL 维度统计使用情况，但没有独立的 TL 查询 API。TL 名单目前是固定的 27 人。

**不足之处**：
- 名单变更时需要改代码
- 从 drilldown API 查全部数据再过滤效率低
- 如果 TL 名单有遗漏，TL 使用统计就会不准

**未来计划**：
- 从飞书通讯录或 OKR 系统动态读取 TL 名单
- 或从 AI 编程系统的组织架构 API 获取

---

## ★ 项目名称版本号可能出现在末尾 (2026-06-24 20:53)

**问题**：`_PROJECT_VERSION_RE` 正则 `^\d+\.\d+[（(]\d+[）)]\s*` 只匹配**开头**的版本号，但实际数据中版本号也在末尾出现，如 `DPP双周迭代 5.93版本（0529）`。

**修复**：正则增加后缀匹配分支：
```python
_PROJECT_VERSION_RE = re.compile(
    r'^\d+\.\d+[（(]\d+[）)]\s*'                # prefix: 5.93（0529）项目名
    r'|\s*\d+\.\d+版本?[（(]?\d*[）)]?\s*$'     # suffix: 项目名 5.93版本（0529）
)
```

**教训**：检查匹配范围是否覆盖了可能的位置（开头/结尾/中间），不能假设所有格式一致。

---

## ★ TL 多人提取须用 re.findall() 而非 re.search() (2026-06-24 20:53)

**问题**：`_fetch_bitable_project_map()` 和 `/projects` 端点两处 TL 清洗都用了 `re.search()`，只返回**第一个**匹配项。当 TL 字段有多个人员时（`[@樊少(Fs)](url) [@张三(Sam)](url)`），只有第一个人被提取。

**修复**：`re.search()` → `re.findall()`，全部匹配后用 `",".join()` 拼接。

**教训**：重复代码导致修复遗漏。虽然两处代码逻辑相同但写法略有差异（变量命名、注释等），说明 review 时不会像第一次写那样仔细对照。这次同样花了时间确认两处都改了。最好的做法是**提取统一函数**。

---

## ★ ratio 格式化错误的第三次出现 (2026-06-24 20:53)

**问题**：`update_bitable_record()` 中 `f'{stats.get("aicoding_ratio", 0):.2f}%'` 没有做类型判断。当 `aicoding_ratio` 已是字符串时（如 `"68.57%"`），`:.2f` 抛 `ValueError: Unknown format code 'f' for object of type 'str'`。

**背景**：这是 Phase 3 中**第三次**遇到 ratio 格式化问题：
1. 导出 xlsx（export 端点）← 已修（加 `isinstance` 判断）
2. 导出 xlsx 二次 ← `data["project_stats"]` vs 局部变量混用（变量名 bug）
3. **本次**：`update_bitable_record` ← 没修

**修复**：`create_bitable_record` 中已有 `_fmt_ratio()` 本地嵌套函数用来处理同一问题，但 `update_bitable_record` 中没有。将 `_fmt_ratio` 提升为模块级函数，两处共用。

**教训**：同一问题的第 3 次出现说明系统性治理手段还不够——需要在 `feishu_client.py` 的 bitable 相关函数入口处统一处理数据格式，而不是每个函数各自兜底。或者写一个 schema 层，所有 bitable 更新前都经过数据转换。

---

## ★ 不要用正则解析飞书 bitable 项目名称——硬编码更可靠 (2026-06-24 21:31)

**反复修正 4 轮后的最终方案：硬编码 PROJECT_MAP**

**背景**：正则版本号清洗无论如何补都覆盖不全。从 bitable 实际数据看到 5+ 种版本号格式：
- `95分算法 5.93（0529）` — 后缀纯数字
- `DPP双周迭代 5.93版本（0529）` — 后缀+"版本"
- `商业化V5.93迭代（5月29日灰度）` — V前缀+中文日期
- `交易搜索5.93（5月29日灰度）` — 纯数字+中文日期
- `5.93（0529）Dsearch搜索引擎版本迭代` — 前缀纯数字

**方案**：枚举空间有限的场景（12 个固定项目），硬编码比解析更稳定。

```python
PROJECT_MAP = [
    ("DPP双周迭代", "樊少"),
    ("Dsearch搜索引擎版本迭代", "樊少"),
    # ... 12 条
]
```

**匹配策略**：不再从 bitable "提取"项目名和 TL，而是用 `标准名 in bitable名` 子串反向匹配，仅从 bitable 获取 `record_id`。

**删除的代码**：
- `_PROJECT_VERSION_RE` 正则
- `_extract_project_name()` 函数
- `_fetch_bitable_project_map()` 中的 TL 解析逻辑
- `/projects` 端点中的 TL 解析逻辑
- write-bitable 中的 exact_map + 模糊匹配
- `import re` 整个模块（~60 行）

**教训**：当数据源是人工输入的非结构化文本时，解析器永远在追赶数据格式的变化。有限枚举空间的场景用硬编码，承认"这个赌局不可赢"。

---

## ★ 知识库管理代理模式 — 三层异常捕获 + 通用代理函数 (2026-06-30)

**模式**：`kb_manage.py` 用 4 个通用函数封装所有代理请求：

```python
def _proxy_get(path, params=None):
def _proxy_post(path, json_body=None):
def _proxy_delete(path, json_body=None):
def _proxy_files(path, files, data):
```

每个函数捕获三种异常并返回统一 `{"status":"error", "data":None, "error":"..."}` 格式。

**三层 catch 顺序**：
1. `ConnectionError` — "无法连接到知识库服务（localhost:8000），请确认无矩2.0 已启动。"
2. `Timeout` — 独立的 30s 超时提示
3. `RequestException` — 兜底

**教训**：10 个代理端点共用同一套异常处理，比每个端点自己 try/catch 简洁得多。但注意文件上传代理需要用 `requests.post(..., files=files, data=data)`，不能序列化为 JSON。

---

## event.ts matchAll 必须用 global regex

**发现时间：** 2026-07-01（Phase 1b）

**错误：** `String.prototype.matchAll` 要求正则表达式带 `/g` 标志，否则抛 `TypeError`。

**修复：** `const eventPattern = /\b(on[A-Z]\w+)\s*=\s*\{/g;`

---

## HOOK_DEF 正则需覆盖函数声明括号

**发现时间：** 2026-07-01（Phase 1b）

**错误：** 信号提取器 `hooks.ts` 正则只匹配 `useXxx =` 或 `useXxx:`，但函数声明格式是 `function usePermissionCheck() {`。

**修复：** `/use[A-Z]\w+\s*(?:=|\(|:)/` 增加 `(` 分支。

---

## Cluster 空组 Bug — visited 复用导致第二阶段全空

**发现时间：** 2026-07-01（Phase 1b）

**根因：** 第一遍 BFS 后 visited 集合已包含所有文件，第二遍聚类直接返回空。

**修复：** 改用 `allVisited` 跟踪，isolated 文件单独走目录聚类兜底 + 最后一层"每个文件独自成簇"保底。

---

## 路由 `path:` 键在 Umi config 中无引号

**发现时间：** 2026-07-01（Phase 1a）

**根因：** REGEX `["']path["']` 要求有引号，但 Umi config `routes: [{ path: '/a', ... }]` 的键无引号。

**修复：** REGEX `["']?path["']?` 支持可选引号。

---

## 编排器 git log 路径参数须用 `--` 分隔符

**发现时间：** 2026-07-01（Phase 3 验证）

**错误：**
```python
["git", "log", "--format=%s", f"{base}..{target}"] + frontend_paths
```
不生效，commit messages 返回空列表。

**根因：** git 的 pathspec 参数必须放在 `--` 之后，否则被解释为 ref 名称。

**修复：** 在 `..{target}` 后插入 `"--"`：
```python
["git", "log", "--format=%s", f"{base}..{target}", "--"] + frontend_paths
```

---

## 生成器函数必须 yield 才能被 `yield from` 调用

**发现时间：** 2026-07-01（Phase 3 验证）

**根因：** `analyze()` 用 `yield from self._generate_diff(...)` 调用，但 `_generate_diff()` 末尾没有 `yield` 语句，导致 `TypeError: 'NoneType' object is not iterable`。

**修复：** 在 `_generate_diff()` 末尾加 `yield`。

---

## code_analyze_service 须适配 LLMClient 类而非函数

**发现时间：** 2026-07-01（Phase 3）

**根因：** `llm_client.py` 暴露的是 `LLMClient` 类（`LLMClient.chat(system=, user=)`），但 `code_analyze_service.py` 写成了 `llm_complete()` 函数调用。

**修复：** 改为 `client = LLMClient(**g.llm_config)` + `client.chat(system=, user=)`。

---

## ★ Phase 1 已知优化点（MVP 后处理）

**记录时间：** 2026-07-01（Phase 1 真实仓库验证后）

### 1. JSON/非代码文件应过滤
- **现象**：`plugin_exec_result.json` 等 JSON 文件被纳入 AST 分析，产生 STYLE_ONLY 噪音
- **预期行为**：`.json`、`.md`、`.csv`、`.log` 等非代码文件应在 diff 层过滤或标记为跳过
- **待修复位置**：Flask 编排器 `generate_diff()` 的过滤规则，或 CLI 入口

### 2. NEW_PAGE 路径检测加固
- **现象**：`resolveBatchWarnState.ts`（工具函数）被误判为 NEW_PAGE，因为它含 `resolve` 关键词
- **根因**：NEW_PAGE 正则 `(/pages\/.*)\.(tsx|ts)` 匹配到了 `node_modules` 或非页面目录中的文件
- **预期**：需确认文件是否在 `pages/` 子目录下且有 `export default` 组件
- **待修复位置**：`signals/routes.ts`

### 3. page-logic 去重未生效
- **现象**：page-logic 文件（如 `podActions.ts`）和对应 pages 文件在不同目录聚类中，去重逻辑无法跨 cluster 合并
- **根因**：page-logic 的 `src/page-logic/` 和 pages 的 `src/pages/` 不在同一目录层级，目录聚类各自成簇
- **预期**：聚类后做一次全局扫描，合并路径中仅 `page-logic/` ↔ `pages/` 互换的 cluster
- **待修复位置**：`graph/cluster.ts` 聚类后处理

---

## 列表推导式变量名勿覆盖 Flask `g`

**发现时间：** 2026-07-02（Phase 7 生产调试）

**错误：**
```python
llm_input = {
    "feature_groups": [
        { "type": g.get("type") }  # 这里 g 是列表推导式变量，不是 Flask 的 g
        for g in ast_result.get("featureGroups", [])
    ],
}
# 后续调用 g.llm_config → AttributeError: 'NoneType' object has no attribute 'llm_config'
```

**根因：** 列表推导式中的循环变量名 `g` 覆盖了 `from flask import g` 的全局上下文引用。

**修复：** 改用 `for fg in ...` 避免命名冲突。

---

## LLM 返回格式不统一 — 需归一化层

**发现时间：** 2026-07-02（Phase 7 生产调试）

**现象：** 同一 Prompt 下 LLM 返回了至少 5 种不同格式：`{report: [...]}`、`{changeReport: [...]}`、`{changes: [...]}`、裸数组 `[...]`、`{new_features: [...]}`。

**根因：** 不同模型（deepseek-v4-flash）对 JSON 输出格式的遵守程度不可控。

**修复：** 后端归一化层先检查是否已有 `new_features` 字段，否则遍历所有 value 找第一个 list-of-dicts。

---

## create_doc_xml 须以 `<title>` 标签开头

**发现时间：** 2026-07-02（Phase 7 导出修复）

**现象：** 飞书文档创建成功（URL 正确），但文档内容为空。

**根因：** `feishu_client.py` 的 `create_doc_xml` 用 `lark-cli docs +create --content @file.xml`，要求 XML 以 `<title>...</title>` 开头。只用 `<text_tag>` 或 `<p>` 时内容为空。

**修复：** XML 开头加 `<title>报告标题</title>`。

---

## `conf` 变量在异常处理中可能残留

**发现时间：** 2026-07-02（Phase 7 生产调试）

**现象：** LLM 归一化代码 `float(conf)` 未报错，但 `conf` 值来自上层作用域残留变量，不是正确的 `matched_conf`。

**修复：** 显式使用 `float(matched_conf)`，避免依赖上层作用域变量。

---

## ★ LLM 批量归纳不可稳定 — 改为逐组调用

**发现时间：** 2026-07-03（生产验证）

**现象：** 三次相同输入，AST 输出完全一致（61 Feature Groups），但 LLM 输出项数分别为 59、27、92，每次不同。

**根因分析：**
1. `temperature=0` 不足以保证确定性——DeepSeek/OpenAI 分布式部署下，不同 GPU 节点浮点运算非确定性导致采样路径不同
2. 加 `seed=42` 仍然不够——模型对 seed 支持不彻底
3. **本质问题**：LLM 不适合做"N 个输入 → N 个输出"的批量归纳任务，它要么合并（61→27）要么拆分（61→92）

**修复：** 重构 `_llm_summarize`，改为按组逐一调用 LLM，AST 决策树决定分类，LLM 只做描述生成:
- 每个 Feature Group 单独调 LLM，输出 `{category, description}`
- `type` 字段直接决定归属（NEW_FEATURE→新增、FEATURE_MODIFY→修改、STYLE_ONLY→UI）
- AST confidence 直接作为输出 confidence
- ThreadPoolExecutor(max_workers=5) 并行，单组 120s 超时

**教训：** LLM 适合做"理解"和"描述"，不适合做"计数"和"分类"。分类决策应由确定性代码完成，LLM 只做语义描述。

---

## `app.py` 缺少 `request` 导入导致 500

**发现时间：** 2026-07-03

**现象：** 重启后端后 `/api/health` 返回 500

**根因：** `app.py:47` 新增 `request.headers.get('X-Git-Token')` 但未导入 `from flask import request`

**修复：** `from flask import Flask, jsonify, g, request`

---

## ★ 信号提取应从正则改为真实 AST（ts-morph 节点判断）

**发现时间：** 2026-07-03

**背景：** 当前信号提取是在 diff 的 addedLines 上做正则匹配，存在假阳性/漏检问题。

**正则匹配的局限性：**

| 信号 | 正则模式 | 假阳性场景 |
|------|---------|-----------|
| API_CALL | `api.get(` | 注释 `// api.get` 也会匹配 |
| STATE_ACTION | `set\w+\(` | `setTimeout(` 也会匹配 |
| PERMISSION | `role\|permission\|auth` | 变量名 `userRole` 也匹配 |
| DATA_MODEL | `interface\|type\|enum` | 注释或字符串中出现的也匹配 |

**修复方案：** 9 个信号提取器改为 ts-morph AST 节点判断，保持轻量模式（`skipFileDependencyResolution: true`），不启用 TypeChecker。

**不改 TypeChecker 的原因：** 需要加载 node_modules 和 tsconfig.json，qiankun 微前端项目加载 2-5 分钟，且可能因版本冲突崩溃，收益有限（所有信号提取都不需要类型推断）。

**API_CALL 特殊处理：** 加一道 import 来源正则检查，确认 `api` 来自项目内部的 request 模块（`import { api } from '@/request'`），而非第三方库。

---

## ★ LLM 逐组修正分类替代代码层 reconciliation

**发现时间：** 2026-07-03

**背景：** 逐组 LLM 调用时，AST 分类可能遗漏业务意图（如 STYLE_ONLY 的 CSS 实际上是权限控制）。原方案考虑代码层关键词 reconciliation，但关键词覆盖不准确。

**方案：** 在 LLM 逐组调用的输出中加 `type` 字段，让 LLM 同时确认或修正 AST 分类。

**约束：**
- LLM 只能修正，不能随意改——Prompt 中限定修正规则
- 只有找到明确证据时才能改分类
- 允许的修正方向：STYLE_ONLY ↔ FEATURE_MODIFY、UI_INTERACTION → FEATURE_MODIFY
- 禁止将 STYLE_ONLY 改为 NEW_FEATURE（样式不可能变成新功能）
- 每组独立调用，数量 1:1 对齐，不会出现批量归纳的合并/拆分问题

**Prompt 输出格式：**
```json
{
  "category": "简短概括",
  "description": "详细描述",
  "type": "NEW_FEATURE | FEATURE_MODIFY | STYLE_ONLY | ..."
}
```

---

## ★ AST 集中验证层（astValidator.ts）

**发现时间：** 2026-07-03

**背景：** 正则信号提取存在假阳性（如 `setTimeout` 误判为 STATE_ACTION、注释中的 `interface` 误判为 DATA_MODEL）。在每个提取器中加 AST 验证会导致 9 个文件大量重复 try/catch。

**方案：** 新增 `astValidator.ts`，接收正则发现的信号列表，用 ts-morph AST 节点统一过滤假阳性。正则提取器保持不变。

**设计原则：**
- 正则负责发现候选信号（召回率高）
- AST 负责过滤假阳性（精确率高）
- AST 解析失败时保留信号（保守兜底）
- 轻量模式（skipFileDependencyResolution=true），不加载 node_modules
- 仅加载 changed files 到 Project 中，不加载全项目

**验证逻辑：**

| 信号类型 | AST 验证 |
|---------|---------|
| STATE_ACTION | 排除 setTimeout/setInterval/setAttribute |
| API_CALL | 检查 import 来源，确认 api 来自项目 request 模块 |
| PERMISSION | 检查 IfStatement/ConditionalExpression/BinaryExpression 的条件 |
| DATA_MODEL | 检查 InterfaceDeclaration/TypeAliasDeclaration/EnumDeclaration 节点 |
| NEW_PAGE | 检查 export default 组件声明 |
| STYLE_ONLY | 检查是否有 FunctionDeclaration/VariableDeclaration/ClassDeclaration/IfStatement |
| EVENT_HANDLER | 检查 JsxAttribute 节点 |
| HOOK_DEF | 检查 FunctionDeclaration/VariableDeclaration 节点 |

---

## 功能变更分析模块 — 后续优化方向（2026-07-03 记录）

> 当前模块已具备可用性：输出稳定（逐组 LLM 调用 1:1 对齐）、分类合理（AST 决策树 + LLM type 修正）、信号准确（正则 + AST 验证双层过滤）。以下为后续迭代方向。

### 信号粒度优化

#### 方向 1：聚类后拆分 constant 文件
- **问题**：`constant.ts`/`types.ts` 文案文件和 `index.tsx` 功能组件通过 import 关系聚在同一组，LLM 描述时文案和功能混在一起
- **方案**：`cluster.ts` 加 post-processing 函数，检测组内是否有纯 `constant.ts`/`types.ts`/`contant.ts` 文件，如果它们没有其他 import 依赖，拆成独立组
- **改动量**：~50 行，单文件修改
- **优先级**：🔴 高

#### 方向 2：新增 TEXT_CHANGE / TYPE_CHANGE / TEST_CHANGE 信号类型
- **问题**：当前只有 10 类信号，粒度偏粗。文案更新、类型定义变更、测试变更没有独立信号
- **方案**：
  - `TEXT_CHANGE`：文件名匹配 `constant.ts`/`contant.ts`，内容只有字符串/对象字面量 → 归为"文案变更"类别
  - `TYPE_CHANGE`：`types.ts` 文件新增/修改 → 归为 INFRA_CHANGE
  - `TEST_CHANGE`：`*.test.ts`/`*.spec.ts` 文件变更 → 单独展示
- **改动量**：新增 2-3 个信号提取器，每个 ~20 行
- **优先级**：🔴 高

#### 方向 3：行号级信号定位
- **问题**：信号标记到文件级别，LLM 不知道具体哪行发生了什么变更
- **方案**：`Signal` 类型加 `line` 字段，提取器记录行号，LLM 输入中附带行号信息
- **改动量**：`types.ts` + 各提取器 + validator，~30 行
- **优先级**：🟢 低

### 描述质量优化

#### 方向 4：给 LLM 提供完整文件内容
- **问题**：当前只传 snippet 前 200 字，LLM 看不到完整上下文，描述不够具体
- **方案**：传完整文件内容（base 和 target 版本），通过 AST 标注"变更行"
- **代价**：token 消耗增加 2-3 倍
- **优先级**：🟢 低

#### 方向 5：两步描述法（先概括再展开）
- **问题**：一次调用既要概括 category 又要展开 description，难以兼顾
- **方案**：Step 1 生成 category（10 字概括），Step 2 基于 category + 完整代码生成 description
- **代价**：耗时翻倍（但并行调用可缓解）
- **优先级**：🟡 中

#### 方向 6：描述质量校验层
- **问题**：LLM 输出中可能出现"优化了代码"、"完善了功能"等模糊词汇
- **方案**：加校验规则。description 中不能出现模糊词汇 → 重新生成；必须包含至少一个具体字段名/文件名/状态码 → 否则降级使用文件名
- **改动量**：~50 行，后端校验函数
- **优先级**：🟡 中

#### 方向 7：模板化描述 + LLM 填空
- **问题**：LLM 自由生成导致描述风格不一致
- **方案**：给 LLM 模板，只填核心信息（文件、组件名、业务目的）
- **代价**：可能让描述显得死板
- **优先级**：🟢 低

---

## ★ PRD 中等模式对话 — LLM 判断信息完备度不可靠 (2026-07-06)

经过 4 轮迭代发现 LLM 对"信息是否足够"的判断标准与人类不一致。有效方案是 Prompt 约束体系（2-3 轮/话题、不答无关问题、参考历史避免重复） + 代码层兜底（3 轮强制推进），不能单纯依赖 LLM 判断。

**涉及文件**：`backend/services/prd_gen_service.py`

---

## ★ 代码变更分析模块 — 知识快照未注入 LLM (2026-07-06)

`_llm_summarize()` 接收 `snapshot` 参数但从未使用。LLM 只看到文件路径和信号类型，
没有项目背景（路由、模块、API 接口）。

**修复**：新增 `_format_snapshot_context()` 将快照压缩为摘要注入 `group_prompt`。

## ★ project_context.md 废弃原因 (2026-07-06)

`project_context.md` 只有 ML 平台的 6 个模块 + 技术栈描述，内容过于简略，
且 `.ai-rules/` 中对同一仓库的架构描述更完整。
**操作**：删除文件，清除 `prd_gen_service.py` 中所有引用。
