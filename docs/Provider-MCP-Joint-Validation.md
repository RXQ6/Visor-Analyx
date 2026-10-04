# Phase 2.7：Provider 与真实只读 MCP 联调

## 验收范围

这是显式应用组装与可控联调，不是外部真实模型验收。复用 Phase 2.6 的官方
`@modelcontextprotocol/server-filesystem@2026.8.31` 与固定目录
`tests/fixtures/mcp-readonly`，仍只授权 `get_file_info`。没有增加工具、写权限、目录
或依赖，没有自动接入 Desktop worker 或 Settings。

新增 `demo/provider_mcp_runtime.py` 管理一次 Provider、Registry、AgentLoop 和 MCPHost
的生命周期。默认调用原 `create_provider(None)`，仍为 deterministic；显式
ProviderConfig 交给原 Factory。Provider 组装失败在启动 MCP 前抛出，MCP 失败明确结束
组装，不退回无 MCP 的运行。关闭后禁止复用本次 Runtime/Registry。

## 实际调用链

```text
原 EvalRunner / 独立 Phase 2.7 EvalCase
  → ProviderMCPRuntime
  → Provider Factory → 同一个 ModelProvider 实例
  → MCPHost / attach_readonly_filesystem → 原 SDK stdio Client
  → 官方 Filesystem initialize + list_tools
  → 原 MCP Adapter → 原 ToolRegistry（单工具白名单与原 schema）
  → 原 AgentLoop.complete(messages, tools)
  → Provider tool_call
  → 原 Registry 参数校验 / Guardrail
  → Adapter → Client → stdio tools/call → 真实 get_file_info / stat
  → 原 SDK / Adapter 校验、截断、ToolResult 与安全 Trace
  → 原 AgentLoop 的 tool Observation
  → 同一个 Provider 第二轮 complete(messages, tools)
  → final_answer → 原 AgentLoop 结束
  → 原 Tool / Contract / Trace / Guardrail / Observability evaluators
```

先做无 HTTP 的 scripted Provider，再做本机 HTTP：

| 验证通道 | Provider | 结果来源 | 证明范围 |
| --- | --- | --- | --- |
| scripted | 宿主显式注入测试 factory；不新增 Provider ID | 真实 Filesystem MCP | 原模型 contract、AgentLoop 与 MCP 的两轮闭环 |
| loopback HTTP | 原 Factory 创建原 OpenAICompatibleProvider，连接 127.0.0.1 临时端口 | 测试服务脚本选择工具，真实 MCP 提供文件事实 | 原网络请求构造、schema、tool call ID、Observation 回填与响应适配 |

loopback 服务不是 OpenAI，也没有真实模型推理。两通道最终回答中的文件大小都从实际
MCP ToolResult 解析，再与本机 stat 对比，不硬编码文件事实。

## 安全边界

- 不加载 `.env`，不读取真实 API Key，不调用 OpenAI 或任何外部模型。loopback 服务仅
  临时设置独立测试环境变量，使用明确的合成凭据，不复制整个进程环境。
- Provider 配置与内部 usage/latency 不进入 Agent messages、Trace、Session、IPC 或
  Renderer。测试 HTTP 服务关闭访问日志，不记录请求头、完整 prompt/response 或异常正文。
  验收报告只保存计数、断言、原 Eval 摘要和公开 fixture 大小。
- MCP 继续使用固定 Node entrypoint、固定 fixture 根、env={}、单工具白名单、原参数
  校验、Guardrail、ToolResult 和截断。生产调用没有绕过 Registry；本机 stat 只用于
  对照测试结果。
- 没有改 AgentLoop、Workflow、Skill、Session、Memory、HITL、Desktop IPC/Event、
  Provider/MCP contract、Provider Factory/adapter、MCP Client/adapter 或原评测标准。

## 失败与过程判定

专项用例直接启动同一真实官方 MCP，测试侧沿用 Phase 2.6 stdio relay 注入延迟与断线。
原 `mcp_timeout` / `mcp_server_unavailable` ToolResult 回到 Provider 第二轮，产生明确
错误回答；没有自动重试或重新连接。原 Harness 仍判工具执行失败，不以错误说明文本
冒充成功分析。

未注册工具不会进入 MCP：scripted 通道由原 Registry 返回 `TOOL_NOT_FOUND`，原 Eval
判非法工具；compatible 通道由原 Provider adapter 拒绝非法 tool response，原 Loop
记录模型错误并抛出。Guardrail block 仍在远端 I/O 前结束 Loop，不追加模型轮次。

相同只读工具重复调用保持原行为，不新增去重逻辑：原 Trace/Eval 检测重复签名并判失败；
一直重复则由原 max_iter 上限终止。Trace 的 Guardrail → MCP → tool_completed 顺序、
工具次数和迭代次数与实际执行一致，负向用例的 Harness 失败是预期结果。

## 显式运行

前提沿用 Phase 2.6 的可选 MCP SDK 和固定 npm Server，见
[只读 MCP 说明](MCP-Readonly-Filesystem.md)。脚本不安装依赖，也不接受外部模型 endpoint
或 API Key 参数。

```powershell
$env:PYTHONPATH = (Get-Location).Path
$env:DATA_AGENT_PROVIDER_ID = 'deterministic'
python -B tests/provider_mcp_smoke.py --node 'D:/NodeJS/node.exe' --output tests/results/provider-mcp-joint-smoke.json
python -B -m unittest tests.test_provider_mcp_joint
```

`--node` 应替换为宿主真实的绝对 Node 路径。直接调用新的组装类时，显式配置仍受原
Factory/Provider 校验约束；本阶段验收入口只运行 scripted 与 loopback 测试通道。

## 2026-09-28 验收结果

Provider 79/79、MCP 48/48（原 Mock/SDK 24 保留）、联调 18/18；TypeScript build、
Desktop 30/30、Electron smoke/E2E 9 步、Node 13/13、Python 382/382、P0 15/15、
P1 20/20、Robustness 25/25、Day19 60/60、Regression Gate 11/11 全 PASS。
Day19 security violations=0、contract failures=0；原评测预期与 baseline 未改。
102 个受保护实现文件的阶段前后 SHA256 一致。

首轮 Desktop E2E 在 800→1440px 原生窗口切换时超时；原 E2E 单独复跑及完整 Desktop
npm test 复跑均通过。未放宽断言或改桌面代码，Windows 窗口时序波动作为风险保留。

证据：[两通道真实 MCP Harness 摘要](../tests/results/provider-mcp-joint-smoke.json)、
[Phase 2.7 全量回归与边界记录](../tests/results/provider-mcp-phase27-regression.json)、
[原 Day19 与 Regression Gate](../tests/results/day19-unified-report.json)。

## 尚未完成的真实验收

**Phase 2.3 仍未完成。** 历史两次 OpenAI 请求均返回 HTTP 429，没有成功模型响应。
本机可控服务不能证明真实 OpenAI 的 final_answer/tool_call、模型工具选择质量或
服务/模型兼容性。原真实调用证据保留，Phase 2.7 不处理 429、不重试 OpenAI。

本轮仍为固定公开目录的 Windows stdio 验收，不是用户目录授权或操作系统沙箱；依赖
已安装的可选 SDK/Server。真实模型自动重复/恢复行为未验收。原 JSON Schema 子集、
Resources/Prompts/HTTP transport 边界不变，安装包未重建。完成后停止。
