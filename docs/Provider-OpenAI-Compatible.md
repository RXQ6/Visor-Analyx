# Phase 2.3：最小 OpenAI-compatible Provider

当前状态（2026-09-27）：适配器与离线回归通过；用户指定 OpenAI Chat Completions endpoint
和 gpt-5.6-luna，明确授权本次将 .env 中 OPENAI_API_KEY 临时加载到进程环境。
两次真实请求均 HTTP 429，未获得模型响应，无自动重试，Phase 2.3 未完成最终验收。
真实 final_answer/tool_call 及 AgentLoop 解析未能验证，模型/协议兼容性不能判定。
安全证据见 [真实验收记录](../tests/results/provider-real-smoke.json)。
结果记录见 [离线回归记录](../tests/results/provider-phase23-regression.json)。
Phase 2.4 已新增 Runtime 环境选择入口，参见 [双模式切换](Provider-Mode-Selection.md)；
该切换不代表本页所述 Phase 2.3 真实验收通过。
Phase 2.5 增加有上限的超时配置、429/5xx 分类与独立内存元数据，参见
[Provider 可靠性](Provider-Reliability.md)；不重新请求真实服务，也不改变上述验收状态。

## 选择与配置

默认 `create_provider()` 仍为 deterministic，不访问网络或凭据。
只有显式传入以下内存配置才启用真实 Provider：

```python
from providers import ProviderConfig, create_provider

config = ProviderConfig(
    provider_id="openai-compatible",
    model_name="YOUR_MODEL_NAME",
    endpoint="https://YOUR_PROVIDER_HOST/v1",
    api_key_env="DATA_AGENT_COMPATIBLE_API_KEY",
)
provider = create_provider(config)
decision = provider.complete(
    messages=[{"role": "user", "content": "Reply with exactly OK."}],
    tools=[],
)
```

`api_key_env` 是环境变量名，不能填写密钥值。密钥须由调用进程继承的环境变量提供；
Phase 2.3 不实现安全配置存储、文件配置、环境配置自动选择或 Renderer Settings。
Desktop 内部组装可传入 `build_workflow(..., provider_config=config)`；Phase 2.4 的普通
worker 读取显式环境选择，缺省仍为 deterministic。缺少字段、凭据或未知 Provider
都明确失败，不回退；无参数 factory 本身保持 deterministic。

endpoint 可为兼容服务的 API base URL，或完整的 `/chat/completions` URL；前者追加
`/chat/completions`，完整 URL 不重复追加。要求 HTTPS，只有 loopback 允许 HTTP；
不接受 URL 中的用户名、密码、query 或 fragment。环境变量应在启动调用进程前设置。

## 调用与响应边界

```text
内部 composition / Desktop build_workflow(provider_config=...)
  → create_provider(ProviderConfig)
  → OpenAICompatibleProvider
  → AgentLoop.complete(messages, tools) / Skill 复用同一 Provider
  → POST {endpoint}/chat/completions
  → Provider 校验并转换
  → final_answer / needs_user_input / tool_call
  → 原 AgentLoop → 原 ToolRegistry → 确定性工具
```

采用非流式 Chat Completions，按官方协议传递 `messages`、`tools` 和 function call
历史；工具结果仍由 ToolRegistry 执行，Provider 不执行工具。协议参考：
[Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。
兼容服务需支持相同字段；不支持的响应明确报错，不尝试其他 API 或静默降级。

Runtime 的 `dataset_context` / `schema` 作为用户消息中的数据上下文转换；不原样发送
内部消息扩展字段。已有系统与 Skill 指令保持原文。普通文本输出为 final_answer；
明确的 `{"type":"needs_user_input","content":"..."}` 输出为补充信息请求，
不从自然语言猜测。Skill 的其他 JSON 输出保留为 final_answer 内容供原 validator 检查。

仅支持一个完整 function call，发送 `parallel_tool_calls=false`；多调用、不完整、
非法 JSON、未知工具、拒绝响应和截断响应都失败，不丢弃或自动修复部分输出。
Provider 响应 envelope、usage 和其他厂商字段不返回 AgentLoop。

## 凭据与错误

- 构造时验证指定环境变量，每次调用重新取值；实例/配置不保存密钥值。
- 密钥仅放在 HTTP Authorization header，不拼进 URL、prompt 或 tool schema。
- 拒绝所有 HTTP redirect，避免转发 Authorization；保留系统 TLS 校验。
- 不打印或记录原始请求/响应、header、URL、厂商错误正文和底层异常；返回固定结构化错误。
- 拒绝输入与输出决策中的完整密钥值，包括解析后的 JSON 字符串；不会让完整回显进入 Session/Trace。
- 此措施不承诺清除 Python 内存中的字符串，或识别任意变形、分段、编码后的凭据；
  应继续避免调试器 locals 转储及第三方 HTTP 调试日志。

默认 socket timeout 为 30 秒，构造器可用 `timeout=...` 显式调整；只发一次，不重试。
Phase 2.5 加入 `ProviderConfig.timeout_seconds` / `DATA_AGENT_PROVIDER_TIMEOUT_SECONDS`，
必须 >0 且 <=120 秒；旧构造器参数也受该上限校验。
它是传输读写超时，不是跨全部读写的硬总时限，也不新增 AgentLoop 取消机制。
响应读取上限 1 MiB，超限报错；401/403 归为认证错误，其他 HTTP 错误、timeout、
network、invalid response 各有固定错误 code。

## 离线验收环境

Provider 42/42、Python 303/303、Desktop 30/30、Electron E2E 9 步、Node 13/13、
P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60 与 Regression Gate 11/11 通过。
原 Electron smoke 在后台取消轮询中超时（诊断显示任务已完成），以下测试启动方式通过，
保留了所有原断言和 timeout，未修改产品或 Mock 实现：

```powershell
cd desktop
.\node_modules\.bin\electron.cmd --disable-background-timer-throttling .\dist\tests\electron-smoke.js
```

此测试依然需要原 DATA_AGENT_PYTHON 环境变量。已将该 launch 参数加入
desktop/package.json 的 smoke 启动命令，最终完整 Desktop npm test 退出码 0；
未改测试文件、Mock、断言或 timeout。一次 E2E 原生 700px resize 等待超时，
原测试不改复验通过；Windows 窗口时序仍可能波动。

## 两次真实验证（显式选择，离线回归不会运行）

先在本机设置指定的密钥环境变量，再用项目可用 Python 运行：

```powershell
python -B tests/provider_real_smoke.py --endpoint https://YOUR_PROVIDER_HOST/v1 --model YOUR_MODEL_NAME --api-key-env DATA_AGENT_COMPATIBLE_API_KEY --report tests/results/provider-real-smoke.json
```

脚本只发两次请求：合成文本 `OK` 与合成 `emit_probe_status` tools 请求。
不读取/发送 CSV、Session、Memory，不执行该合成工具；使用原 AgentLoop 的解析函数
校验已适配决策。报告仅包含时间、用户指定的非密钥 endpoint/model、HTTP status/attempts、
决策类型、解析/通过状态与固定错误，不记录密钥、header、请求正文或原始响应。
运行真实验证需要用户指定目标与模型；临时 .env 加载仅用于本次明确授权，未接入 Runtime。

## Phase 2.3 原始阶段边界

不改 AgentLoop、Workflow、Skill、Session、Memory、HITL、IPC/Event contract、
Tool Registry/handlers、Dataset/Chart 事实源和 Node P0；不新增依赖、不接 UI、MCP、
其他 Provider、流式输出、自动重试或 usage 统计。现有 installer 不因本阶段自动升级。
