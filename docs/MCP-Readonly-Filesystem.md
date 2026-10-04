# Phase 2.6：真实只读 Filesystem MCP

## 选择与范围

接入官方 `@modelcontextprotocol/server-filesystem`，固定版本 **2026.8.31**。
独立可选依赖位于 `integrations/mcp-filesystem`，package-lock 固定传递依赖和 integrity；
不修改根 Node P0 或 Desktop 依赖。沿用 `requirements-mcp.txt` 的 Python SDK `mcp==2.2.0`。

参考：[官方 Filesystem Server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)。
`get_file_info` 只调用文件 stat，返回大小、时间、类型和权限，不读取正文。
上游 Server 本身也提供写工具；本轮的 Host 权限只有 `get_file_info`，模型只能看见
`mcp_filesystem__get_file_info`，不能取得上游的读取正文、写入、编辑、移动或 shell 工具。
权限由 Host 白名单决定，不把 `readOnlyHint` 当成安全保证。

访问根固定为仓库内的 `tests/fixtures/mcp-readonly`，其中只有公开验收文件。
不提供 root 配置项，不开放仓库根、用户目录、驱动器或 `.env`。相对路径由 Server
在该根内解析；Server 会验证规范化路径和 realpath。客户端不提供 Roots 回调，不扩展 CLI 根。

## 当前实际链路

```text
可选验收入口：tests/mcp_filesystem_smoke.py
  → 原 EvalRunner / EvalCase（独立 phase26-real-mcp 案例）
  → attach_readonly_filesystem(MCPHost, host-owned Node)
  → 原 MCPStdioClient / 官方 Python SDK
  → 固定 Node entrypoint / 官方 Filesystem Server / 固定 fixture 根
  → initialize + list_tools
  → 原 MCPToolAdapter → 原 ToolRegistry（schema、mcp_read、4 KiB 结果上限）
  → 原 AgentLoop（验收用 ScriptedModel 只指定工具，不编造文件事实）
  → Registry 参数校验 / Guardrail
  → Adapter → Client → stdio tools/call → get_file_info / stat
  → SDK 校验 → Adapter 内容与 outputSchema 校验
  → 原 ToolResult / 原结果截断 / 原安全 Trace
  → AgentLoop Observation → final_answer
  → 原 Tool / Contract / Trace / Guardrail / Observability evaluators
```

不修改 EvalRunner、Day19 的 60 个旧案例、baseline、threshold 或 Regression Gate。
验收报告只保存工具名、状态、过程评估摘要和公开文件大小，不保存原始请求/响应、路径参数
或 Trace ID。实际 ToolResult/Trace 在内部交给原 Evaluator，证明的是实际调用。

## 显式运行

使用现有项目 Python 环境；可选 MCP SDK 安装方式保持不变：

```powershell
python -m pip install -r requirements-mcp.txt
npm.cmd ci --prefix integrations/mcp-filesystem --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org
$env:PYTHONPATH = (Get-Location).Path
$env:DATA_AGENT_PROVIDER_ID = 'deterministic'
python -B tests/mcp_filesystem_smoke.py --node 'D:/NodeJS/node.exe' --output tests/results/mcp-filesystem-smoke.json
python -B -m unittest tests.test_mcp_filesystem tests.test_mcp_adapter tests.test_mcp_integration tests.test_mcp_stdio_sdk
```

`--node` 是宿主选择的绝对 Node 路径，示例路径应替换为本机真实路径。运行时直接启动
固定 Node 文件与固定 Server JS，不运行 npx、安装命令或 shell，不发送网络请求。
默认 Registry/Runtime/Desktop 不自动启用 MCP；缺可选依赖或启动失败明确返回错误，调用方
必须检查 `MCPRegistrationReport.ok`，不把原 Registry 仍可用误认为 MCP 成功。

`MCPHost.close()` 负责关闭 Client 和 SDK 所有的子进程。关闭后应丢弃本次 Registry，
不继续复用已经绑定到关闭 Client 的 handler。

## 安全与故障处理

- Client 的 `env={}` 仅允许 SDK 自带的操作系统变量白名单；不复制整个 `os.environ`，
  不继承 API Key、Provider 配置或 `NODE_OPTIONS`，不加载 `.env`。
- 保持 Registry 的参数校验、Guardrail、ToolResult 结构、错误安全适配和截断不变。
  MCP Trace 仅包含工具名、状态、耗时、受控 server_id/错误码，不保存参数或完整返回正文。
- 启动默认 10 秒、工具调用默认 5 秒。Adapter 原超时继续取消 SDK pending request；
  `mcp_timeout`、`mcp_server_unavailable`、`mcp_protocol_error` 等原错误码保持不变。
- Client 仅补 SDK 校验异常到协议错误的映射：Pydantic wire 校验失败、带 schema 校验
  cause 的 RuntimeError、SDK 2.2 缺 structured content 的固定异常。固定安全错误文案，
  不将校验输入或原响应放进错误。其他断线/连接异常仍属于服务不可用。
- 启动超时取消初始化 task 并等待有界 SDK 清理，防止初始化结束后遗留空闲子进程。
  SDK 自带 transport 负责关闭 stdin、等待、必要时结束自己的进程树。
- 不自动重试、不自动重连，不修改 AgentLoop、Workflow、Skill、Session、Memory、HITL、
  Provider、IPC 或 Runtime Event contract。

## 专项验证方法

`tests/test_mcp_filesystem.py` 启动真实官方 Server，覆盖发现/schema/单工具注册、文件和目录
元数据、真实 AgentLoop、Trace、越界/父目录/前缀相邻路径拒绝、写工具未注册、非法参数、
Guardrail 阻断、原截断、默认 Registry 不变，以及环境隔离和明确启动失败。

测试专用 `mcp_filesystem_fault_relay.cjs` 只代理同一个官方 Server 的 stdio：在真实响应
之后注入延迟、非法 schema、非法 wire/structured output、缺字段和断线。取消验证观察
实际 SDK cancellation notification，确认请求等待终止且连接可继续使用；旧 SDK slow_echo
测试继续验证 Server 的执行 task 收到取消。relay 只记录临时标记，不记录请求/响应，
不在产品路径注册，不提供第二个产品 MCP 或额外目录。

Filesystem 的 stat 本身很快；延迟注入验证的是传输取消，不证明能够回滚已经完成的 stat。
本轮不存在 MCP 写操作，所以不引入远端写动作取消或幂等语义。

## 2026-09-28 验收结果

真实 Filesystem 专项 24/24，包含原 Mock/SDK 的 MCP 合计 48/48；Provider 79/79，
TypeScript build、Desktop 30/30、Electron smoke/E2E、Node 13/13、Python 364/364、
P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60、Regression Gate 11/11 全通过。
Day19 security violations=0、contract failures=0；没有修改评测目标或标准。
真实案例在原 EvalRunner 的五个过程 evaluator 中全部通过。

证据：[真实 MCP Harness 摘要](../tests/results/mcp-filesystem-smoke.json)、
[Phase 2.6 全量回归](../tests/results/mcp-phase26-regression.json)、
[原 Day19 与 Regression Gate](../tests/results/day19-unified-report.json)。

## 限制与阶段边界

这是显式 Harness 集成，当前验证平台为 Windows / Python 3.12 / Node 24。
没有接 Renderer Settings，没有自动加入 Desktop Worker，没有重建 NSIS；安装版不会自动
获得该可选服务。固定公开目录适用于本阶段验收，尚不是面向用户任意目录的产品授权方案。
上游进程按当前用户身份运行；协议路径白名单不等于操作系统沙箱。支持范围仍受原
ToolRegistry JSON Schema 子集限制；Resources、Prompts、HTTP transport 不在本阶段范围。

**Phase 2.3 真实 OpenAI 验收仍未完成：此前两次请求均 HTTP 429。** 本轮不读取真实
密钥、不处理 429、不再调用 OpenAI，不改变 Provider 架构，也不以 MCP 验收替代真实模型验收。
完成后停止，不进入 Phase 2.7。
