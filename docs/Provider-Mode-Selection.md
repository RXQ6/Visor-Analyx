# Phase 2.4：Runtime Provider 双模式切换

Runtime 在每次普通分析 worker 的模型组装处读取进程环境配置；不新增 IPC 字段，
不通过 Renderer、Session、Trace 或运行命令 payload 传递 Provider 配置。
Desktop Main → Python supervisor → worker 沿用已有的环境继承方式。

## 配置入口

| 环境变量 | 对应 ProviderConfig | 默认与要求 |
| --- | --- | --- |
| `DATA_AGENT_PROVIDER_ID` | `provider_id` | 未设置时为 `deterministic`；显式空值报错 |
| `DATA_AGENT_MODEL_NAME` | `model_name` | `openai-compatible` 必填 |
| `DATA_AGENT_PROVIDER_ENDPOINT` | `endpoint` | `openai-compatible` 必填 |
| `DATA_AGENT_API_KEY_ENV` | `api_key_env` | `openai-compatible` 必填，只填写密钥环境变量名称 |
| `DATA_AGENT_PROVIDER_TIMEOUT_SECONDS` | `timeout_seconds` | Phase 2.5 新增；可选，默认 30 秒，必须 >0 且 <=120 |

默认或显式 deterministic 都不读取其他配置项或密钥，不访问网络。单独设置 model、
endpoint 或密钥引用不会启用真实模式；必须显式设置 Provider ID。
无参数 `create_provider()` 和 `build_workflow()` 仍为 deterministic，不自动读取全局配置，
保持原有 Mock / deterministic 单元测试的组装语义。

显式 deterministic：

```powershell
$env:DATA_AGENT_PROVIDER_ID = 'deterministic'
```

显式真实模式的非敏感配置示例：

```powershell
$env:DATA_AGENT_PROVIDER_ID = 'openai-compatible'
$env:DATA_AGENT_MODEL_NAME = 'YOUR_MODEL_NAME'
$env:DATA_AGENT_PROVIDER_ENDPOINT = 'https://YOUR_PROVIDER_HOST/v1'
$env:DATA_AGENT_API_KEY_ENV = 'OPENAI_API_KEY'
```

被引用的密钥变量必须由外部安全配置或启动环境提供。这里不提供密钥输入、保存或加载命令。
Runtime 不读取 `.env`，不加载 User/Machine 的凭据存储；仅使用启动进程继承的环境。
已经运行的 Desktop / supervisor 不会接收外部终端后来修改的环境；切换后需重新启动应用。
现有 Settings / Integrations 仍为规划中入口，本轮没有连接真实配置。

## 实际调用链

```text
Desktop Main → Python supervisor → worker（继承启动环境）
  → load_provider_config()（只读选择元数据）
  → build_workflow(provider_config=...)
  → create_provider(config)
      ├─ deterministic → DeterministicModelProvider
      └─ openai-compatible → OpenAICompatibleProvider（只读指定密钥环境变量）
  → 原 Workflow / AgentLoop / Skill 复用同一实例
  → Provider.complete(messages, tools)
  → 已有 final_answer / needs_user_input / tool_call
  → 原 AgentLoop / Tool Registry / 确定性工具
```

只有原 Workflow 路由到分析节点时才调用模型。chat/calc 等原路由行为不改变。
审批 worker 原来直接恢复已批准工具操作，不调用模型；该流程保持不变。

## 失败与安全边界

- 配置缺失、空 Provider ID、非法 endpoint/引用：`invalid_provider_config`。
- 未知或未实现的 Provider：`unsupported_provider`；预留项不自动映射到兼容模式。
- 被引用变量缺失或凭据格式无效：`missing_api_key`。
- 以上组装错误在业务 Workflow/Dataset 组装前失败，沿用既有 `run_failed` 的
  `error.code/message` 结构。只输出安全固定文案或字段名，不回显配置值。
- 网络、认证、非法响应沿用 Phase 2.3 错误处理；不重新选择 Provider、不重试、不 fallback。
- 配置与密钥不会写入 Agent messages、ToolResult、Session、Trace、Renderer 或错误日志。
  完整密钥回显仍由原适配器拦截；不承诺识别任意变形或分段的凭据回显。
- 测试运行环境显式使用 deterministic；真实模式专项仅使用合成凭据和 Mock/本地 HTTP。
  本轮不读取真实 API Key，不发送外部真实服务请求。

## 验收证据与保留风险

新增 `tests/test_provider_selection.py`：配置选择、显式失败、无 fallback、原 Desktop
结果一致、Skill 同实例、Runtime Event envelope 不变，以及子进程继承环境后通过本地 HTTP
执行原真实统计工具（sales.csv 总和 1580）。Session/Trace/日志/对外事件检查无敏感配置。
最终回归记录见 [Phase 2.4 回归](../tests/results/provider-phase24-regression.json)。

**Phase 2.3 真实验收仍未完成。** 用户指定的 OpenAI endpoint 与 gpt-5.6-luna 两次请求
均返回 HTTP 429；没有成功模型响应，真实 final_answer、tool_call、AgentLoop 解析及模型/
服务兼容性未验证。本阶段双模式离线通过不替代该验收，未再次请求真实服务。
原证据见 [Phase 2.3 真实验收](../tests/results/provider-real-smoke.json)。
Phase 2.5 的超时、错误分类与内部元数据见 [Provider 可靠性](Provider-Reliability.md)；
同样不替代真实调用验收。

本轮不改 AgentLoop、Workflow、Skill、Session、Memory、HITL、Desktop IPC、Runtime Event
contract、Registry/handlers、Dataset/Chart 或评测标准；不新增依赖，不重建 NSIS installer。
源码与 sidecar staging 的变更不会自动更新已经安装的旧版本。
