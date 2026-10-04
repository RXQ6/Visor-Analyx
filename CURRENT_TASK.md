# CURRENT TASK

## 当前任务：证据工作台 UI（用户授权）

**证据工作台已实现并完成 dev / packaged / installed 验收；2026-10-04 完成交付记录。**
生产修改仅限 Renderer 的 index.html、index.ts、styles.css：左侧真实文件概览/字段，
中央回答/图表/持续提问，右侧实际事件与当前数据依据；空态增加引导与示例卡片，
窄屏自动折叠过程面板。没有前端计算分析事实或复制设计稿的示例数据。

三种形态 UI 专项 21/21、窗口/IPC 自动专项 24/24 PASS；两套真实 exe 双启动 smoke、
资源审计、私有 Provider/MCP 集成 PASS。Desktop 38/38、Electron smoke、dev E2E 10 步、
Node 13/13、Python 400/400、P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60、
Regression Gate 11/11 PASS，security violations=0、contract failures=0。
275 个受保护源码/测试哈希不变，安装/打包 Renderer 资源与当前构建逐字节一致。

实际安装程序：desktop/release/evidence-workbench-installed-final-20261002/Data Analysis Agent.exe。
最终安装包：desktop/release/evidence-workbench-final-20261002/Data Analysis Agent Setup 0.1.0.exe。
说明：docs/Desktop-Evidence-Workbench.md；证据：tests/results/evidence-workbench-ui-regression.json。
本次不推进业务 Phase，不改 Runtime/Provider/MCP/AgentLoop/Workflow/Session/HITL 或窗口逻辑。
原生 chooser 在本次自动专项中提供测试回答，不新增人工验收声明。历史 Phase 2.9 的首次
窗口消失根因仍未确认；Phase 2.3 的真实 OpenAI HTTP 429 缺口仍保留。
**Phase 2.9 仍不能标记为最终完全通过。**

## 历史阶段：Phase 2.9.1

**当前为 Phase 2.9.1：窗口生命周期专项排查与复验已完成，历史首次消失根因仍未证实。**
2026-10-02，dev、真实 unpacked exe、真实 installed exe 的原生 CSV 选择各完成 9 项
专项（27/27）；自动选择专项各 8 项（24/24）。showOpenDialog parent 正确，选择、取消、
真实 CSV 注册失败/重试、显式 Renderer reload 后窗口与 IPC/event listener 均存活；
真实分析结果 1580。三轮原生选择由用户完成，测试记录后续真实链路，其余专项 chooser
答案由测试提供，不混称全部人工覆盖。

本轮观察到工具 modal element cache 失效、窗口最小化及测试选错固定 fixture 后 runner
清理进程等验收干扰。最终正常可见启动没有产品关窗复现；这些证据不能追溯证明历史
首次消失的准确原因。未修改产品窗口逻辑，**Phase 2.9 暂不标记为最终完全通过**。
新增生产 Main/exe 专项 runner/probe，native 失败保留窗口，不加恢复补丁或 sleep。

最终回归：TypeScript、Desktop 38/38、Electron smoke、dev/packaged E2E 各 10 步、
unpacked/installed 双启动 smoke、sidecar/资源审核/两套集成检查、Node 13/13、Python
400/400、P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60、Regression Gate 11/11
均 PASS；security violations=0、contract failures=0。65 个受保护 Python 文件哈希未变。
Python Runtime、Provider/MCP contract、AgentLoop/Workflow/Session/HITL 和评测标准未改。
Phase 2.3 的历史 HTTP 429 缺口仍保留；没有真实模型请求、.env 加载或新安装包构建。
证据：docs/Desktop-Window-Lifecycle-Investigation.md；
tests/results/window-lifecycle-phase291-regression.json。停止在本阶段，等待后续指令。

## 历史阶段：Phase 2.9 打包与自动验收

**Phase 2.9 固定依赖打包、真实 NSIS 安装及安装 exe 自动验收已完成，停止在 Phase 2.9。**
2026-09-30，最新本地安装包 desktop/release/Data Analysis Agent Setup 0.1.0.exe；SHA256
B13822E0F59505593ECF48C292DF960259250F0B22834EAE87742AA9CB02F89A。
实际安装目录 desktop/release/phase29-installed-20260930，未发布到 GitHub Releases。

私有 runtime 包含最新 Provider/Settings、Python 3.12/Node、固定 MCP SDK/Server 及传递
依赖，运行无需开发 PATH 或全局解释器。29 个固定 Python distribution、103 个 npm 包；
公开 metadata fixture 根与 get_file_info 单工具不变，不打包 .env/用户配置/环境值。
安装环境 Node 缺失明确失败，不使用全局 Node；其他业务实现/协议未改。

实际安装 exe 两次启动：默认本地模式、Settings 外部字段与缺凭据错误、MCP 启停/只读、
CSV 1580、HITL 暂停/拒绝、拒绝后普通分析、退出/重启配置与 Session/Trace 恢复均 PASS。
资源审核和私有 runtime 的真实 MCP/schema/ToolResult/越界/缺依赖错误检查均 PASS。
补充 Windows 界面检查已确认首页/Settings/原生文件对话框显示；后续原生 CSV 选择因
窗口消失、验收工具无法重绑定未完成，原因未确认，不记为人工分析 PASS。实际 exe
自动 smoke 的 chooser 回答为确定性测试值，其余链路真实。

最终 PASS：TypeScript、Desktop 38/38、开发/打包 Electron E2E 各 10 步、packaged/installed
smoke、Provider 79/79、MCP 48/48、联调 18/18、Settings 14/14、新打包安全 4/4、Node 13/13、
Python 400/400、P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60、Regression Gate 11/11；
security violations=0、contract failures=0。打包 E2E 首轮窗口 1px 偏差，原样独立复跑 PASS。
64 个核心 Python 文件阶段前后 SHA256 一致。说明与证据：
docs/Desktop-Packaged-Provider-MCP-Acceptance.md；tests/results/packaged-integrations-phase29-regression.json。

**Phase 2.3 真实 OpenAI 验收仍未完成：历史两次 HTTP 429。** 本轮未读取真实 Key、未加载
.env、未请求外部模型。未签名、Windows x64、公开 fixture/非 OS 沙箱等限制保留。

## 历史阶段：Phase 2.8 Desktop Provider / MCP 配置接入

**Phase 2.8 Desktop Provider/MCP 配置接入已完成并通过全量回归，停止在 Phase 2.8。**
2026-09-28，Settings 支持 deterministic（本地 / 测试）与 openai-compatible（外部模型），
外部模式只填写 model_name、endpoint、api_key_env；显示已应用模式与凭据可用性，不接收
或返回真实 Key，不提供远端连接测试。Filesystem MCP 只可启停原固定公开目录的
get_file_info；展示只读、范围安全摘要和注册工具，其他集成仍规划中。

独立 Settings API 从 Renderer → sandboxed Preload → Main → Runtime 配置层 → 原
Provider Factory/MCPHost。Main userData/runtime-settings.json 只保存固定非敏感字段，
原 window.agent、已有分析/Session/HITL IPC 与 Runtime Event envelope 不变；配置
response 不广播、不写 Session/Trace。Supervisor 保留配置，通过私有 worker 环境传递
非敏感快照，在原组装位置注入模型/只读 MCP，不改 AgentLoop/Workflow/Skill。
首次 Desktop 默认 deterministic、MCP disabled；当前分析未结束时不能应用。缺字段、
缺凭据、非法 Provider/MCP 范围、存储损坏或 MCP 不可用均明确失败，不 fallback。
重启恢复非敏感配置，缺凭据保留外部模式与错误并阻止分析；有效显式保存可修复坏文件。

最终 PASS：新增 Desktop Settings 8/8、Python Settings 14/14；TypeScript、Desktop 38/38、
Electron smoke/E2E 10 步、Provider 79/79、MCP 48/48、Phase 2.7 联调 18/18、Node 13/13、
Python 396/396、P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60、Regression Gate 11/11；
security violations=0、contract failures=0，Day19 average/p95/max=0.244/0.652/0.803s。
实际 worker 的本机 HTTP/真实 MCP 闭环 2 轮 Provider、1 次 MCP，结果 78 bytes，Session/
Trace/日志无 Key、endpoint 或环境引用。79 个核心 Python 文件哈希一致；Provider/MCP
contract/实现、AgentLoop、Workflow、Skill、Session、Memory、HITL、Registry/Guardrail、
Dataset/Chart 未修改，原评测标准和 baseline 不变。

sidecar staging 已重建，隔离实测 Settings/Runtime 导入与默认模式；未重建 NSIS。基础
sidecar 不自动包含可选 MCP npm Server/Python SDK，缺依赖明确不可用；已安装旧版本
不会自动升级。仍为公开 fixture 根、Windows stdio、非 OS 沙箱，不扩目录或新增 Server。
说明：docs/Desktop-Provider-MCP-Settings.md；证据：
tests/results/desktop-settings-phase28-regression.json；README 含真实 Electron Settings 截图。

**Phase 2.3 真实 OpenAI 验收仍未完成，历史两次 HTTP 429。** 本轮未读取/使用真实 Key、
未加载 .env、未访问 OpenAI；凭据“可用”只检查环境，不能证明远端服务/模型兼容性。
原 provider-real-smoke.json 保留。Phase 2.8 完成后停止，等待用户后续指示。

## 历史阶段：Phase 2.7 Provider 与真实 MCP 可控联调

**Phase 2.7 Provider 与真实 MCP 可控联调已完成并通过全量回归，停止在 Phase 2.7。**
2026-09-28，新增 demo/provider_mcp_runtime.py 显式组装原 Provider Factory、AgentLoop、
Registry/Guardrail、MCPHost/Adapter/SDK stdio 与 Phase 2.6 的同一个官方 Filesystem Server。
默认仍 deterministic，不自动接入 Desktop worker/Settings；组装失败明确结束，不 fallback，
关闭后不复用。固定公开 fixture 根、get_file_info 单工具白名单不变，没有写操作或新依赖。

先完成 scripted Provider 的无 HTTP 联调，再用原 Factory/原 OpenAICompatibleProvider
连接本机 127.0.0.1 可控测试服务。使用独立合成凭据变量，不复制整个环境、不加载 .env、
不读取真实 Key、不请求 OpenAI。两通道均 schema 原样传入、1 次真实 MCP 调用、2 轮同一
Provider；Observation 与 tool_call_id 正确回填，final_answer 的 78 bytes 来自实际 MCP，
与本机 stat 一致。原 EvalRunner 的 Tool/Contract/Trace/Guardrail/Observability 全通过。

联调专项 18/18（scripted/组装 13、本机 compatible 5），覆盖完整闭环、安全隔离、timeout、
disconnect、非法工具、Guardrail、重复调用、max_iter、Trace/Eval 一致与关闭清理。错误
Observation 回 Provider 后可形成错误说明，但原 Harness 仍判工具失败；Guardrail block
不继续第二轮，重复调用继续由原 Trace/Eval 检出，原 max_iter 保留，不新增去重/自动重试。

最终全量 PASS：Provider 79/79、MCP 48/48（旧 Mock/SDK 24 不变）、联调 18/18、TypeScript、
Desktop 30/30、Electron smoke/E2E 9 步、Node 13/13、Python 382/382、P0 15/15、P1 20/20、
Robustness 25/25、Day19 60/60、Regression Gate 11/11；security violations=0、
contract failures=0，Day19 average/p95/max=0.243/0.653/0.859s。首轮 Electron E2E 窗口
800→1440px 切换超时，原 E2E 单独复跑与完整 npm test 复跑均通过，原桌面代码与断言未改。
AgentLoop、Workflow、Skill、Session、Memory、HITL、IPC/Event、Provider/MCP contract、
Factory/adapter、MCP Client/adapter、Registry/Guardrail、Eval 实现共 102 个受保护文件
阶段前后哈希一致，评测标准/baseline/旧案例未修改。

证据：tests/results/provider-mcp-joint-smoke.json、
tests/results/provider-mcp-phase27-regression.json；说明：docs/Provider-MCP-Joint-Validation.md。
**Phase 2.3 真实 OpenAI 验收仍未完成，历史两次 HTTP 429；本轮外部模型请求为 0。**
本机 HTTP 服务不是 OpenAI，没有真实模型推理；真实 final_answer/tool_call、模型/MCP
协作质量及服务兼容性仍未验证。原 provider-real-smoke.json 保留。本阶段未重建 NSIS，
未开放用户目录或扩展 Schema/Resources/Prompts/HTTP。停止，等待用户后续指示。

## 历史阶段：Phase 2.6 第一个真实 MCP 接入

**Phase 2.6 第一个真实 MCP 接入已完成并通过全量验收，停止在 Phase 2.6。**
2026-09-28，接入官方 `@modelcontextprotocol/server-filesystem@2026.8.31`，独立可选
package/lock 位于 integrations/mcp-filesystem，沿用现有 Python MCP SDK 2.2.0。
只通过 MCPHost 白名单注册 `mcp_filesystem__get_file_info`，action=mcp_read；访问根固定为
公开目录 tests/fixtures/mcp-readonly。服务本身提供其他工具，但读取正文、写入、编辑、移动
与 shell 均未授予 Agent。Node 由宿主显式选择，固定 entrypoint/根、env={}，不复制整个
环境、不继承 API Key/Provider 配置/NODE_OPTIONS，不加载 .env。默认 Desktop/Registry 不变。

实际调用为原 EvalRunner → 原 AgentLoop → ToolRegistry 参数校验/Guardrail → Adapter →
MCPStdioClient/SDK stdio → 官方 Filesystem stat → SDK/Adapter 结果校验 → 原 ToolResult、
截断和 Trace → AgentLoop。真实元数据与本机 stat 一致，公开文件大小 78 bytes。
独立 MCP-FILESYSTEM-01 案例使用原 Tool/Contract/Trace/Guardrail/Observability evaluator
全部通过；未改变 Day19 的旧案例、baseline、threshold、Regression Gate 或旧 Mock 测试。

Client 最小补充 SDK 校验异常到原 mcp_protocol_error 的安全映射及启动超时清理：不把
非法 response/structuredContent 误报为服务不可用，不输出 SDK 校验输入；其他断线仍按
mcp_server_unavailable 处理。启动超时取消初始化 task 并做有界清理，关闭后的迟到启动
不创建空闲子进程。AgentLoop、Workflow、Skill、Registry、Guardrail、Provider、Session、
Memory、HITL、Desktop IPC 和 Runtime Event contract 未修改。

新增真实专项 24/24，MCP 总计 48/48（旧 Mock/SDK 24/24 保留）。验证真实启动、list_tools、
schema/注册、call_tool、ToolResult、越界拒绝、写工具未注册、非法参数、Guardrail 阻断、
结果截断、环境隔离和生命周期。测试侧 relay 只代理同一个实际官方服务，注入非法 schema、
非法/缺字段响应、断线和延迟；timeout/显式取消均观察到真实 SDK cancellation notification，
等待终止且连接可复用。Filesystem stat 已经完成时，传输取消不证明能回滚该 stat。

最终回归：Provider 79/79、TypeScript build、Desktop 30/30、Electron smoke/E2E 9 步、
Node 13/13、Python 364/364、P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60、
Regression Gate 11/11 全 PASS；security violations=0、contract failures=0；Day19
average/p95/max latency=0.255/0.697/0.846s。测试默认 deterministic，无真实模型请求。
证据：tests/results/mcp-filesystem-smoke.json、tests/results/mcp-phase26-regression.json；
运行与安全说明：docs/MCP-Readonly-Filesystem.md。

**Phase 2.3 真实 OpenAI 验收仍未完成：此前两次调用均 HTTP 429，无成功模型响应。**
本轮不处理 429、不读取真实密钥、不改 Provider 架构，原 provider-real-smoke.json 未改；
真实 final_answer/tool_call 适配、AgentLoop 解析和服务/模型兼容性仍未验证。
当前只完成显式 Harness 接入，未接 Settings、未自动接入 Desktop worker、未重建 NSIS。
固定 fixture 根不是用户目录授权方案；协议白名单不是 OS 沙箱。仅验收 Windows stdio，
仍受原 JSON Schema 子集限制，未扩展 Resources/Prompts/HTTP。停止，不进入 Phase 2.7。

## 历史阶段：Phase 2.5 Provider 可靠性与观测

**Phase 2.5 Provider 可靠性与观测已完成并通过离线全量验收，停止在 Phase 2.5。**
2026-09-27，只修改 Provider 层：统一 auth_error、rate_limited、timeout、network_error、
invalid_response、provider_unavailable 六类服务错误，提供 classify_provider_error()。
429 与 5xx 使用专门异常子类，保留旧 HTTP 异常捕获兼容与 code/message envelope；
429/5xx 不自动重试。原本地配置/输入校验错误独立保留，不误报成远端响应错误。

ProviderConfig 新增 timeout_seconds，默认 30 秒、必须 >0 且 <=120；显式真实模式可由
DATA_AGENT_PROVIDER_TIMEOUT_SECONDS 配置。非法值明确失败，不钳制、不 fallback。
deterministic 实现/默认行为不变，不读取该环境项。该超时是 socket 传输配置，不是
DNS、所有读写及适配阶段的硬总时限。

新增独立 providers/observability.py：真实 Provider 的 complete 记录安全标量元数据
provider_id、model_name、latency_ms、可选 input_tokens/output_tokens/request_id 及安全错误分类。
使用单调时钟，只采纳合法服务 usage，不猜测；优先 x-request-id，不把 completion ID 当请求 ID。
默认 64 条、最大 256 条有锁内存记录，snapshot 不可变；记录故障不覆盖模型结果/错误。
不保存密钥、Authorization、endpoint、凭据引用、完整 prompt/response/错误正文；安全筛选
标识符。元数据不连接原 TraceCollector，不进入 Agent state、Session、Trace、IPC/Event 或 Renderer。
worker 退出记录消失，无持久化/exporter。deterministic 不新增网络观测逻辑。

最终验收：新增可靠性专项 22/22，Provider 合计 79/79；TypeScript build、Desktop 30/30、
Electron smoke、Electron E2E 9 步、Node 13/13、Python 340/340、P0 15/15、P1 20/20、
Robustness 25/25、Day19 60/60、Regression Gate 11/11 全 PASS，security violations=0、
contract failures=0。sidecar staging 重建，并在隔离目录实际导入可靠性/观测/Runtime/SSL。
仅更新原配置字段集合/环境读取集合断言以覆盖新增 timeout；原 deterministic/Mock 行为测试
与评测标准未改。AgentLoop、Workflow、Skill、Session、Memory、HITL、Desktop IPC/Event
contract、Registry/handlers、Dataset/Chart 均未改，未新增依赖或重建 NSIS。
证据：tests/results/provider-phase25-regression.json；说明：docs/Provider-Reliability.md。

**Phase 2.3 真实验收仍未完成。** 原两次 OpenAI endpoint/gpt-5.6-luna 请求均 HTTP 429，
无成功模型响应；真实 final_answer/tool_call、AgentLoop 解析、服务/模型兼容性仍未验证。
本轮只用合成凭据/Mock/本地 HTTP，未加载 .env、未读取真实 API Key、未请求真实模型服务；
原 provider-real-smoke.json 保留。新错误分类不能替代真实验收，也未重写历史错误码证据。
当前限制还有非流式/单工具调用、保守元数据剔除与变形凭据回显保护不足；旧安装版未升级。
完成后停止，不进入下一阶段。

## 历史阶段：Phase 2.4 Real / Deterministic 双模式切换

**Phase 2.4 Real / Deterministic 双模式切换已完成并通过离线全量验收，停止在 Phase 2.4。**
2026-09-27，仅在 Provider 配置层新增 `load_provider_config()`，普通 Runtime worker 在模型
组装点读取进程环境中的 `DATA_AGENT_PROVIDER_ID`、`DATA_AGENT_MODEL_NAME`、
`DATA_AGENT_PROVIDER_ENDPOINT`、`DATA_AGENT_API_KEY_ENV`。无 selector 默认 deterministic；
显式 deterministic 不读取其他配置或凭据。只有显式 openai-compatible 才创建真实适配器；
缺配置/空 selector/缺凭据/未知 Provider 均明确失败，禁止 fallback。无参数 factory 与
build_workflow 保持原 deterministic 语义，Skill 继续复用相同 Provider 实例。

不自动读取 .env，不接 Settings，不新增依赖；API Key 仍只由已有适配器从指定进程环境
变量取值。配置没有进入 IPC payload、Workflow/Agent 状态、Session、Trace 或 Renderer。
组装错误沿用原 run_failed envelope 的 error.code/message，使用安全结构化错误与固定文案。
审批 worker 不调用模型，保持原工具恢复流程。AgentLoop、Workflow、Skill、Session、Memory、
HITL、IPC/Event contract、Registry/handlers、Dataset/Chart 与原评测标准均未改。

最终验收：新增切换专项 15/15，Provider 合计 57/57；TypeScript build、Desktop 30/30、
Electron smoke、Electron E2E 9 步、Node 13/13、Python 318/318、P0 15/15、P1 20/20、
Robustness 25/25、Day19 60/60、Regression Gate 11/11 全 PASS，security violations=0、
contract failures=0。实际 worker 及独立子进程仅用合成凭据/Mock/本地 HTTP 执行原工具得到
sales.csv 总和 1580，并验证 Session/Trace/日志/事件无敏感配置、失败无 fallback。
sidecar staging 已更新，隔离目录实测 Provider 选择、Runtime、SSL 导入成功。
证据：tests/results/provider-phase24-regression.json；配置说明：docs/Provider-Mode-Selection.md。

**Phase 2.3 真实验收仍未完成：两次 OpenAI 请求 HTTP 429，无成功响应。** 本轮未读取真实
API Key、未加载 .env、未再次请求外部真实服务；不能确认真实 final_answer/tool_call 适配、
AgentLoop 真实响应解析或服务/模型兼容性。原 provider-real-smoke.json 证据保持不变。
切换需要重启继承了配置的应用；未重建 NSIS，既有 Phase 1.5 安装包不自动包含本阶段代码。
完成后停止，不进入下一阶段。

## 历史阶段：Phase 2.3（真实验收仍未通过）

**Phase 2.3 代码与离线回归已完成，两次真实验收均 HTTP 429，未完成最终验收。**
2026-09-27，新增显式 OpenAICompatibleProvider，采用标准库非流式 Chat Completions。
ProviderConfig 仅增加 API Key 环境变量名引用 `api_key_env`；默认仍 deterministic，
普通 Desktop worker 不变。内部 build_workflow(provider_config=...) 可注入真实 Provider，
不新增配置加载器或 Settings。未知项/缺配置/缺凭据明确失败，没有静默 fallback。

网络响应先转换为 final_answer / needs_user_input / 单个 tool_call；原厂响应、usage、
header 和配置不传入 AgentLoop。tools 仍由原 Registry 执行。30 秒 socket timeout、
认证/网络/HTTP/非法响应错误均使用固定文案；禁止 redirect，无自动重试。
凭据只在 Provider 内读取指定环境变量，不缓存到实例、不放 prompt/Session/Trace/Renderer；
完整密钥回显被拒绝。AgentLoop、Workflow、Skill、Memory、Session、HITL、IPC/Event contract、
ToolRegistry/handlers、Dataset/Chart 和 Node P0 均未改。

离线验收：Provider 42/42（新增 27 条）、TypeScript build、Desktop 30/30、Electron E2E
9 步、Node 13/13、Python 303/303、P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60、
Regression Gate 11/11；security violations=0、contract failures=0。原 Electron smoke 多次
取消轮询超时，诊断显示任务已 completed；以 --disable-background-timer-throttling
启动原 smoke 通过，已将参数加入 desktop/package.json 的 smoke 测试命令；原测试、
Mock 与超时不变。最终完整 Desktop npm test 退出码 0。一次原生 700px resize 超时，
原 E2E 不改复验通过，保留环境时序波动记录。
staged private Python 实测导入 Provider、Runtime 和 SSL 成功；未重建 installer。

**真实验收未通过。** 2026-09-27，用户指定 https://api.openai.com/v1/chat/completions、
gpt-5.6-luna、OPENAI_API_KEY。Process/User/Machine 未设置该变量；用户明确授权本次
从 .env 临时加载该指定变量到验收进程内存。只发送合成文本与单个合成 tools schema，
HTTP attempts=2、两次均 429/provider_http_error，没有重试。未获得成功模型响应，
final_answer、tool_call 和原 AgentLoop._normalize_decision 的真实响应解析均无法验证；
不能判断具体额度/限速原因，也不能据此认定模型/协议兼容或不兼容。
密钥未输出或持久化，临时加载脚本已移除；原架构与 Provider 协议未改。
安全证据：tests/results/provider-real-smoke.json。当时停止；后续 Phase 2.4 双模式验收
不替代 Phase 2.3 真实调用验收，该风险继续保留。

## 历史阶段：Phase 2.2 Provider 配置骨架

**Phase 2.2 Provider 配置骨架已完成，当前停在 Phase 2.2。** 2026-09-26，新增仅含
`provider_id`、可选 `model_name` 和 `endpoint` 的不可变内存配置。默认值继续为
deterministic；factory 只按 `provider_id` 显式选择，未知与预留 Provider 返回安全的
结构化异常（`unsupported_provider`），无静默 fallback。预留 openai、anthropic、gemini、
openai-compatible、local 名称，没有实现这些适配器，没有网络请求或 API Key 读写。

Desktop `build_workflow()` 通过内部 `provider_config` 参数接收配置，模型创建在业务组装前
完成。默认 worker 调用不变；配置没有传入 Workflow/Agent 数据或写入 Session、Trace、普通 UI。
保留旧 factory 的无参数、字符串及 `name=` 调用。Renderer Settings、Agent Loop、Workflow、
Skill、Session、Memory、HITL、Desktop IPC、Runtime Event contract 与业务事实源均未改。

最终验证：Provider 专项 15/15（新增配置测试 9 条）、TypeScript build、Desktop 30/30、
Electron smoke、Electron E2E 9 步、Node 13/13、Python 276/276、P0 15/15、P1 20/20、
Robustness 25/25、Day19 60/60、Regression Gate 11/11 全 PASS；security violations=0、
contract failures=0。真实分析与 Session 持久化验证默认/显式配置行为一致，配置字段和值不泄漏；
隔离 staged private Python 实际导入配置与 Runtime 并执行 Provider 成功。

当前限制：配置仅由内部组装传入，不提供文件/环境变量/Settings 加载；model_name 与 endpoint
仅作未来结构预留，当前 deterministic 不使用；真实适配器、凭据层和超时/重试仍未实现。
本轮未重建 NSIS installer，既有安装包仍为 Phase 1.5。等待明确指令，不进入 Phase 2.3。

## 历史阶段：Phase 2.1 Provider 抽象落地

**Phase 2.1 Provider 抽象已完成，当前停在 Phase 2.1。** 2026-09-26，将 Desktop Runtime
内嵌的 `BridgeModel` 迁移为独立 `DeterministicModelProvider`，新增统一的
`ModelProvider.complete(messages, tools)` 类型契约和只支持 `deterministic` 的显式 factory。
未知 Provider 会明确失败，不静默回退；没有网络调用、随机性、API Key 或真实 Provider 配置。

Desktop 只在 `build_workflow()` composition root 改为注入 `create_provider()`；打包 sidecar
同步包含 `providers/`。Agent Loop、Workflow、Skill Runtime、Session、Memory、HITL、Desktop
IPC、Runtime Event contract、Tool Registry/handlers、Dataset/Chart 事实源及 Node P0 流水线未改。
Skill 创建受限 Agent Loop 时继续复用主 Loop 的同一个 Provider 实例。

最终验证：Provider 6/6、TypeScript build、Desktop 30/30、Electron smoke、Electron E2E
9 步、Python 267/267、P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60、
Regression Gate 11/11 全 PASS；security violations=0、contract failures=0。staged private
Python 已实际导入并执行新 Provider。行为与迁移前保持一致。

当前风险：Provider 输入输出仍是宽松字典；只支持同步 completion；没有真实 Provider 的错误、
超时、重试、usage 或 capability 适配。本阶段不扩展这些能力，等待明确指令，不进入 Phase 2.2。

## 历史阶段：Phase 1.5 最终产品验收与 Phase 1 冻结

**Phase 1.5 最终产品验收已完成，Phase 1 已冻结。** 2026-09-26，未新增产品功能，
仅在 Electron E2E 中固化 1600/1200/900/700/520px 五档布局与普通 UI 工程字段
不可见的断言。Empty、Session、Dataset、Analysis、Chart、“分析过程”、Approval、
Error/Retry、左右区域拖拽与折叠均按 Phase 1.4 展示层和原有 Runtime 流程验收。
Python Runtime、IPC/Event contract、Session/HITL/Dataset/Chart 业务事实源未改。

最终回归：TypeScript build、Desktop 30/30、Electron smoke、开发态和打包资源态
E2E 各 9 步、Node 13/13、Python 261/261、P0 15/15、P1 20/20、Robustness
25/25、Day19 60/60、Regression Gate 11/11 全 PASS；security violations=0、
contract failures=0。新 unpacked 与独立安装目录中的真实 exe 双启动 smoke、
packaged sidecar 均通过。普通可见界面的整体文本断言不含 JSON、内部 ID、sequence
或 tool args；Session 标题和结构化结果保持人类可读。

最新 NSIS installer 为 `desktop/release/Data Analysis Agent Setup 0.1.0.exe`，
SHA256 `95DC64EAB21D721AA17296E95419523272CC0205E1FCCCD2B638CA0ABFC2454B`。
安装到独立目录 `desktop/release/phase1.5-installed-20260926`，安装退出码 0。
从该目录的 `resources/app.asar` 启动真实窗口并做可见操作验收：Empty 首页、
设置与集成、“分析过程”入口、系统 CSV/XLSX 文件对话框、测试 CSV 选择、
5 行/4 列数据概览和结果 1580 均实际显示，普通 UI 未出现工程字段。
这项可见验收由 Codex 操作并目视，未声称用户另行签收；Approval、Error/Retry、
Chart 和五档宽度另由真实 Electron E2E/Smoke 覆盖。

已知限制：installer 未签名；品牌图形仍为工作占位；Chart Spec v1 仍仅支持单系列
bar/line/scatter 和最多 100 点；没有 Runtime 结构化 Insight 来源；干净机器、
多显示器缩放及升级/卸载路径未验收。建议稳定标签名 `desktop-phase1.5-stable`，
本轮仅提出建议，未创建标签。下一阶段等待用户明确指令，不进入 Phase 2。

## 历史阶段：Phase 1.4 产品级桌面视觉重设计

**Phase 1.4 产品级桌面视觉重设计已实施并完成自动化回归。** 2026-09-24，
Renderer 已切换到分析画布中心布局：自然语言 Session 标题、CSV/XLSX 引导空首页、
确定性数据概览与结构化结果表、专业化 Chart Card、默认折叠的“分析过程”、可拖拽左右
宽度与窄窗口重排，以及只标记“规划中”的 Settings / Integrations。Windows 原生通用
标题文字和默认英文菜单已从可见窗口移除，使用简洁可拖动标题栏、系统窗口控制区和图标按钮。
当前品牌图形仅为统一资产入口的工作占位，不作为最终品牌确认稿。

本轮未修改 Python Runtime、IPC / Runtime Event contract、Session / HITL / Dataset /
Chart 业务事实源。普通 UI 不展示 thread / trace / run 等内部 ID、sequence、raw JSON、
tool args 或 API Key 值。数据行数、字段数量只取 DatasetSummary；当前 Runtime 投影没有
结构化业务 KPI / Insight 字段，因此不生成业务 Metric / Insight Card。

最终门禁：TypeScript build、Desktop 30/30、Electron smoke、开发态与打包资源态
E2E 各 9 步、Windows unpacked exe 双启动 smoke、packaged sidecar、Python 261/261、
Node 13/13、P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60、Regression Gate
11/11 全 PASS；security violations=0、contract failures=0。NSIS installer 已重新构建，
位于 `desktop/release/Data Analysis Agent Setup 0.1.0.exe`；本轮没有覆盖已安装的
Phase 1.3 目录，也没有对新 installer 做独立安装验收。

剩余限制：Chart Spec v1 仍只有单系列 bar / line / scatter，最多 100 点；无多系列
legend 或独立结构化 insight 来源。真实系统文件选择框在自动化中提供确定性返回路径，
新 installer 的人工视觉与安装流程尚未验收。下一阶段等待用户明确指定，不进入 Phase 2。

## 历史阶段：Phase 1.3 UI/UX Product Polish

Phase 1.3 UI/UX Product Polish 已完成。Renderer 的字体、间距、圆角、边框、卡片层级、
状态语义色、按钮反馈和溢出/滚动规则已统一；700px/520px 窗口重排通过真实 Electron
E2E 检查。仅展示层改变，原按钮 ID/事件绑定与 Python 业务事实源保持不变。

验收：TypeScript build、Desktop 27/27、Electron smoke、开发态/打包资源态 E2E
各 8/8、重建 unpacked 真实 exe 双启动 smoke、Python 261/261、Node 13/13、
P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60、Regression Gate 11/11 全 PASS。
本轮未生成新 NSIS installer，现有 installer 仍是 Phase 1 前 UI；真实原生文件对话框
人手操作及多显示缩放/干净机器人工视觉检查未覆盖。下一轮等待用户指定。

## 历史阶段：Phase 1.2 UI/UX Product Polish

Renderer 增加 Chart Card、按 sequence 的脱敏 Trace Timeline、仅显示安全字段的 HITL
Approval Card，以及 failed/partial/stale 的 Error/Retry 状态视觉区分；所有原按钮 ID、
事件绑定和 Python 业务事实源保持不变。当时验收为 TypeScript build、Desktop 27/27、
原 Electron smoke、开发态/打包资源态 E2E 各 7/7、重建 unpacked 真实 exe 双启动 smoke、
Python 261/261、Node 13/13、P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60、
Regression Gate 11/11 全 PASS。

## 历史阶段：Phase 1 第一轮最小布局

Phase 1 UI/UX Product Polish 第一轮最小布局已完成。Renderer 现在有顶部 Session/Dataset/
Run Status、左侧 Session/Dataset Sidebar、中间 Chat/Analysis/Chart、底部固定输入区；
右侧 Trace 和原有 Error/HITL/状态卡保留。所有原按钮 ID、事件绑定与 Python 业务边界不变。

验收：TypeScript build、Desktop 27/27、原 Electron smoke、开发态/打包资源态 E2E 各 7/7、
新 unpacked exe 双启动 smoke、Python 全量 261/261、Node 13/13、P0 15/15、P1 20/20、
Robustness 25/25、Day19 60/60、Regression Gate 11/11 全 PASS。仅重新构建了 unpacked，
现有 NSIS installer 仍为 Phase 1 之前的 UI；本轮没有进行新的安装包验收。

当时的下一轮 UI/UX 工作现已完成 Phase 1.2，见上文；不自动进入深度美化或业务能力扩展。

## 历史阶段：Desktop M6.5

Desktop M6.5：Release Gate + Release Report 已完成；全部 required gate PASS，Desktop M6 完成。
统一报告：`docs/Desktop-M6.5-Release-Report.md`。版本 0.1.0 的 NSIS installer 已实际安装到
`desktop/release/m6.5-installed`，安装后 exe 首次完成 CSV 真实分析，退出并重启后恢复旧 Session；
不是 unpacked/dev 启动。安装态 smoke 证据位于
`desktop/release/m6.5-installed-smoke-xR3Qia/{first,resume}.json`。

最终门禁：TypeScript build、Desktop 27/27、开发态与打包资源态 Electron E2E 各 7/7、
unpacked 与 installed 双启动 smoke、packaged sidecar、Python 261/261、Node 13/13、
P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60、Regression Gate 11/11 全 PASS；
security violations=0、contract failures=0。未修改 Python Runtime 业务语义或评测标准。

剩余非门禁风险：真实原生文件选择框交互未自动化、未在干净机器测试、安装包升级/卸载路径未验收，
installer/exe 未签名。下一阶段等待用户明确指定，不自动继续。

## 历史阶段：Desktop M6.4

Desktop M6.4：Packaged Smoke 已完成。从重新构建的 electron-builder 真实
`desktop/release/win-unpacked/Data Analysis Agent.exe` 先后启动两个独立进程，不用 dev 模式。
首次确认 Main/Preload/Renderer 与 packaged Python sidecar，经过文件按钮、Send 和真实 Python
数据分析得到 6 条 Runtime Events、`completed` 和销售额总和 1580。关闭进程后重启同一 exe，
从标准 userData 恢复原 thread、4 条消息和 6 条 Trace，没有重复执行旧 run。
NSIS installer 同时重新构建，但尚未执行独立安装；仅系统文件对话框的返回路径由测试提供，
核心 IPC、Runtime、SessionStore 没有 mock。验收结果位于
`desktop/release/m6.4-smoke-y1aRT9/first.json` 与 `resume.json`。

当时的下一阶段候选为 Desktop M6.5；现已完成，见上文。

M6.4 Desktop 单元 27/27、原 Electron smoke、M6.3 开发态与打包资源态 E2E 各 7 个场景、
packaged sidecar、真实 exe 双启动 smoke 均 PASS；Python 全量 261/261、Node 13/13、
P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60、11 项 Regression Gate 全 PASS。
未修改 Python Runtime 业务语义、评测标准或 P0/P1 逻辑。首次在受限测试沙箱中因标准
AppData 缓存目录权限不足失败；正常桌面权限重跑通过，未修改产品路径。

M6.3 新增真实 BrowserWindow UI 测试，在开发态和打包资源态各通过 7 个步骤，
覆盖启动、CSV/XLSX 选择、Send、Run State、Runtime Events、Stop/Cancel、
Session List/Resume、HITL Approve/Reject、真实文件错误/Retry 和 Trace Panel。

M6.3 未修改 Python Runtime 业务语义、P0/P1 逻辑或评测标准。首次整套复跑发现
E2E 测试将测试目录误作 Main 编译目录，已只修正测试入口路径并在两种模式重跑通过。
Desktop 单元 27/27、原 Electron smoke、新开发态 E2E 与打包资源 E2E 均 PASS；
Python 全量 261/261、Node 13/13、P0 15/15、P1 20/20、Robustness 25/25、
Day19 60/60、11 项 Regression Gate 全 PASS。

M6.2 的 Windows unpacked 与 NSIS installer 包含私有 Python 3.12、Python JSONL Bridge、
项目业务模块、Node 数据桥和私有 Node 可执行文件。packaged Electron 经 Main/Preload
成功启动真实 run，直接 packaged sidecar 完成 CSV 注册与分析 run；不依赖开发机绝对路径。

M6.2 构建使用 `DATA_AGENT_PYTHON` 作为构建机输入，产物中使用
`process.resourcesPath/python-runtime/python.exe`。Python stdout 只传协议 JSONL，
stderr 为日志；缺少可执行文件/Bridge 时返回结构化 IPC 错误而不使 Electron 崩溃。
未修改 Python Runtime 业务语义或评测标准。

M6.1 使用 electron-builder 26.15.3、Electron 38.8.6；Main/Preload/Renderer 进入 app.asar。
开发态使用仓库相对路径，打包态使用 process.resourcesPath，运行数据位于 Electron
标准 userData/runtime。打包产物不引用开发机绝对路径。BrowserWindow 继续保持
contextIsolation=true、nodeIntegration=false、sandbox=true。

M6.2 验证：Desktop 单元 27/27、Electron E2E PASS、Windows unpacked 真实 run 烟测
退出码 0；packaged CSV 分析返回销售额总和 1580，8 条 stdout 均为协议 JSONL。
Python 全量 261/261、Node 13/13、Day19 60/60、P0 15/15、P1 20/20、
Robustness 25/25、11 项 Regression Gate 全 PASS。安装包已构建，尚未做独立安装验证。

桌面层继续保持零侵入边界：Electron Main 负责原生文件选择、IPC 和进程宿主；Python Runtime 是
Workflow、Dataset、Agent、Tool、Chart 和安全决策的唯一业务事实源；Renderer 只投影事件和渲染
已有 Chart Spec。

## Desktop M4 已实现能力

- 新增 `sessions:list`、`sessions:get`、`sessions:resume` IPC；列表、消息、事件和恢复状态均来自
  Python `SQLiteSessionStore` 与 `SessionStateProjector`，Electron 不维护第二份 Session 数据。
- Session 列表展示 `thread_id`、`updated_at` 与最近用户/Agent 消息摘要；选择旧 Session 后恢复
  messages、持久化 events 和 pending approval，并继续沿用原 `thread_id`。
- 每次新执行和审批恢复均生成新的 `run_id` / `trace_id`；恢复只 hydrate，不重放历史已完成动作。
- 新增 `approvals:approve`、`approvals:reject` IPC。Renderer 只回传 Runtime 给出的 opaque ID/hash；
  Python `PersistentApprovalManager` / `SQLiteApprovalRepository` 继续唯一校验 thread、approval ID、
  action hash、TTL 和 consumed/replay 状态。
- `waiting_approval` 显示只包含 action type、risk summary、approval ID、expires_at 的审批卡片，
  不展示原始工具参数；Approve 只执行加密保存的单个原动作，Reject/expired/mismatch/replay 均不执行。
- Run State 新增 `resuming`、`rejected`、`expired`；所有状态仍由 Runtime Event 按 sequence 投影。
  Renderer 按当前 thread 过滤事件，Session A 的事件不会投影到 Session B。
- Desktop M1/M2/M3 的 Chat、File、Chart、取消、partial 和安全 BrowserWindow 边界保持不变。

## 验收结果

- Desktop TypeScript/IPC/Runtime/Session/HITL 专项：20/20 PASS。
- 真 Electron BrowserWindow E2E：PASS；覆盖 Session 列表/恢复、审批卡片、Reject 与 Approve 恢复。
- Python 全量：261/261 PASS。
- 原 Node 测试：13/13 PASS。
- P0：15/15 PASS。
- P1：20/20 PASS。
- Robustness：25/25 PASS。
- Day19 Eval Harness：60/60 PASS。
- 原 11 项 regression gate：全部 PASS。
- Day19 average / p95 / max latency：0.284s / 0.761s / 0.947s。
- Security violations：0；Contract failures：0。
- 未修改 baseline、threshold 或既有评测预期。

## Desktop M4 边界复验

- Runtime 宿主重启后 Session 列表、messages/events 与 pending approval 可从同一 SessionStore 恢复。
- Renderer reload 后 pending approval 卡片可重新 hydrate，Approve 保持原 thread ID 并生成新 trace ID。
- approval 重复点击由按钮 pending 状态阻止，Python consumed 状态继续阻止跨进程 replay；expired、
  reject 和 action hash mismatch 均不执行。
- Session A/B 除单元隔离外，Electron E2E 注入其他 thread 的迟到 event 后也未污染当前 UI。
- Session 切换不注册新的 Runtime listener；Renderer reload 会销毁旧 preload context/listener。
- hydrate 失败现在显示结构化错误和最小 Retry；Retry 成功后清除错误并恢复消息。
- 不存在的 thread ID 返回 `session_not_found`；重复 hydrate 已完成 Session 不新增
  `approval_resumed`，不重复执行历史动作。

## Desktop M5 已实现能力

- 新增纯 Renderer `Trace Panel` 投影，覆盖 route、skill、tool、MCP、sub-agent、guardrail、
  approval、error 和通用 Runtime 事件；run 内按 Runtime sequence 排序，Session hydrate 使用
  SessionStore 返回的规范顺序。面板和每条事件均可折叠。
- Trace 只显示 sequence、分类、受控名称、状态和 error code，不渲染 metadata、arguments、
  ToolResult、路径、错误正文或 action hash；thread/run 切换继续沿用 M4 隔离边界。
- 统一 `loading`、`empty`、`running`、`partial`、`stale`、`waiting_approval`、`completed`、
  `failed`、`cancelled` 九种产品状态。每种状态均说明当前发生的事情、是否可继续及下一步操作。
- Runtime/IPC/Session/File/Chart 错误统一显示 code、message、action；可恢复错误显示 Retry。
  Session hydrate Retry、run Retry 和 Session refresh 均不会绕过 Python Runtime。
- partial 状态保留已生成回答与图表，单独展示缺失内容；stale 状态提供 Session refresh 入口，
  Dataset 仍通过原文件选择入口重新选择。
- Retry 沿用当前 thread ID，并由 Runtime 创建新 run/trace。`waiting_approval` 不提供通用 Retry；
  approval 决策失败也不自动重放，已完成高风险动作继续由 Python consumed/replay 规则保护。
- 未修改 Python Runtime、Session、Guardrail、HITL、P0/P1 或评测业务语义。

## Desktop M5 验收

- Desktop TypeScript/IPC/Runtime/Trace/Product State 专项：23/23 PASS。
- Electron E2E：PASS；覆盖 Trace 顺序与脱敏、partial 保留、failed→Retry、stale、cancelled、
  waiting approval Retry 隔离、Session/run 隔离和 Renderer reload。
- Python 全量：261/261 PASS；Node：13/13 PASS。
- Day19 Eval Harness：60/60 PASS；原 11 项 regression gate 全部 PASS。
- Security violations：0；Contract failures：0。
- Day19 average / p95 / max latency：0.265s / 0.692s / 0.917s。

## 当前剩余风险

- BridgeModel 是最小 composition adapter，尚未接入真实模型客户端、凭证和模型级重试。
- 每个 run 独立 worker 仍有进程启动开销，supervisor 的长期 run/dataset 状态需要有界清理。
- 尚无 heartbeat、事件重放和断线后的 sequence gap 恢复。
- Main 仍向所有窗口广播事件；当前 Renderer 做 thread 隔离，未来多窗口仍需 Main 订阅隔离。
- 本地终止 worker 不能证明外部 MCP 写操作没有副作用；仍需远端幂等键、传输层取消和结果核对。
- Renderer 当前只渲染既有 Chart Spec v1 的 bar/line/scatter；不支持交互图表、多系列或大于 100 点。
- NSIS 独立安装后的完整 E2E、真实操作系统文件对话框自动化、代码签名、自动更新和
  干净机器部署仍属于后续阶段；M6.4 已从真实 unpacked exe 完成双启动恢复，未做安装后测试。

## 下一阶段

- 等待用户明确指定下一阶段；暂不加入 heartbeat、sequence gap 自动补洞、多窗口、Trace 导出/深度调试、
  UI 深度美化、真实 Provider 扩展或自动更新。
- 每次主要修改继续运行 Desktop 专项、Python 全量、Node、P0/P1/Robustness 和 Day19 regression gate。
