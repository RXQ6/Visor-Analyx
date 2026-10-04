# Phase 2.5：Provider 可靠性与安全观测

本阶段只改变 Provider 层。`complete(messages, tools)` 仍只返回原模型决策；
deterministic 实现不变，仍是默认模式。没有改 AgentLoop、Workflow、Skill、Session、
Memory、HITL、Desktop IPC、Runtime Event contract、Tool Registry 或 Dataset/Chart。

## 统一服务错误分类

通过 `classify_provider_error(error)` 或异常的 `category` 读取六类服务错误。
原错误 envelope 仍只有 `code/message`，已有错误码保持兼容；429 和 5xx 增加专门子类。

| 场景 | 统一 category | 异常 / code |
| --- | --- | --- |
| 401 / 403 | `auth_error` | ProviderAuthenticationError / provider_auth_error |
| 429 | `rate_limited` | ProviderRateLimitedError / provider_rate_limited |
| socket timeout / wrapped timeout | `timeout` | ProviderTimeoutError / provider_timeout |
| 连接、DNS、其他传输异常 | `network_error` | ProviderNetworkError / provider_network_error |
| malformed / 截断 / 非法决策 / 其他非成功 HTTP | `invalid_response` | ProviderInvalidResponseError / provider_invalid_response，或原 ProviderHTTPError / provider_http_error |
| 5xx | `provider_unavailable` | ProviderUnavailableError / provider_unavailable |

本地配置校验仍保留 `invalid_provider_config`、`unsupported_provider`、`missing_api_key`。
调用期间丢失凭据的观测分类为 auth_error；本地输入拒绝保留 provider_invalid_request，
category 为空，不误报成远端响应错误。组装失败尚未发生 complete，不生成虚假的调用记录。
429/5xx 都只尝试一次；不读取错误正文，不自动重试，不切换 Provider。

## 可配置超时

`ProviderConfig.timeout_seconds` 默认 30 秒，允许 **0 < timeout_seconds <= 120**。
Runtime 显式真实模式可使用 `DATA_AGENT_PROVIDER_TIMEOUT_SECONDS`，例如 `2.5`。
空值、非数字、NaN/Infinity、非正数、超过上限都明确失败，不钳制或静默回退。
直接构造 OpenAICompatibleProvider 时仍兼容 `timeout=...`，同样受上限校验。
deterministic 不读取该环境项，不受真实模式配置影响。

这是标准库 urllib 的 socket 传输超时配置，不是 DNS、全部读写和适配过程的硬总时限。
没有增加后台重试线程、全局取消或 AgentLoop 时限；不能据此承诺所有调用在 120 秒内结束。

## 调用元数据

OpenAICompatibleProvider 每次 complete（成功或已识别失败）生成一条独立元数据：

| 字段 | 来源与规则 |
| --- | --- |
| provider_id | 固定 openai-compatible |
| model_name | 配置中的模型标识，安全校验后保留 |
| latency_ms | perf_counter 单调时钟，覆盖 complete 的输入校验、传输与适配 |
| input_tokens | usage.prompt_tokens，仅非负整数 |
| output_tokens | usage.completion_tokens，仅非负整数 |
| request_id | 优先 x-request-id header；缺省时使用显式 body.request_id |
| error_category / error_code | 仅已有固定安全分类/错误码；成功为空 |

usage 缺失或非法时为 None，不估算、不从文本推断、不把缺失写成 0。
completion 的 `id` 不冒充 request_id。适配成功后才采纳 usage；非法响应或错误正文不采纳用量。
服务错误仍可保留安全的 header request_id。参考官方
[Chat Completions usage](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
和 [x-request-id](https://developers.openai.com/api/reference/overview#debugging-requests)。

## 观测与安全边界

`providers/observability.py` 提供独立的 ProviderObservations。有锁的内存环形记录默认
64 条，容量最多 256 条；snapshot 是不可变元数据元组，to_dict 生成独立副本。
通过 `provider.observations.snapshot()` 可在内部检查，不提供 Renderer/IPC 导出。
可在内部组装传入另一个 ProviderObservations 实例；记录异常被隔离，不覆盖模型结果或错误。

- 只复制 allowlist 标量，不保存原配置对象、prompt、response、HTTP request、header 或错误正文。
- 不记录 endpoint、API Key 环境变量名或密钥，不保存 Authorization header。
- 标识符限定字符、长度最多 128；不安全格式、完整密钥/配置/文本回显被丢弃。
- 没有 logger、文件写入、外部 exporter，也不连接原 TraceCollector/Session。
- 元数据不加入模型决策、Agent state、工具结果、Runtime Event 或普通 Session 文本。
- deterministic 不增加网络观测逻辑；所有原离线测试默认 deterministic。

元数据当前只在 Provider 实例内保留，worker 退出后消失；无持久化或跨进程观测汇总。
观测记录故障可导致元数据丢失，模型调用语义保持不变。字符筛选和完整回显保护不保证
识别任意编码、分段或变形的凭据，也不能证明服务返回的任意标识没有其他业务敏感含义。

## 验收与保留风险

新增 `tests/test_provider_reliability.py` 覆盖超时上限与环境解析、401/403、429、5xx、
network、malformed、usage、latency、request ID、元数据安全、记录故障隔离、有界/不可变记录，
以及真实 Runtime 工具分析后的 Session/Trace/事件/日志隔离。
只使用合成凭据和 Mock/本地 HTTP，未加载 .env、未读取真实 API Key、未调用真实模型服务。
最终结果见 [Phase 2.5 回归汇总](../tests/results/provider-phase25-regression.json)。

**Phase 2.3 真实验收仍未完成。** 此前用户指定 OpenAI endpoint / gpt-5.6-luna 的两次请求
都返回 HTTP 429，无成功 final_answer/tool_call；真实适配和模型/服务兼容性未验证。
新 429 分类不重写历史证据，不代表真实验收通过。本阶段未重新请求真实服务。
原证据：[两次真实请求](../tests/results/provider-real-smoke.json)。

本阶段不新增依赖，不连接 Settings，不重建 NSIS installer；完成后停止，不进入下一阶段。
