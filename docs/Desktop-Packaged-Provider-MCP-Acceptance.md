# Phase 2.9：Windows Provider / MCP / Settings 打包验收

2026-09-30。本阶段完成固定依赖打包、真实 NSIS 安装和安装 exe 的自动验收。
**Phase 2.3 真实 OpenAI 验收仍未完成：历史文本与 tools 请求均 HTTP 429。**
本阶段没有读取真实 Key、加载 .env 或发送外部模型请求。

## 安装产物与证据

- 安装包：`desktop/release/Data Analysis Agent Setup 0.1.0.exe`，147326044 bytes。
- SHA256：`B13822E0F59505593ECF48C292DF960259250F0B22834EAE87742AA9CB02F89A`。
- 实际 NSIS 安装目录：`desktop/release/phase29-installed-20260930/`。
- 启动的是上述目录中的 `Data Analysis Agent.exe`，不是开发 Electron 或 unpacked。
- [机器可读验收记录](../tests/results/packaged-integrations-phase29-regression.json)。

安装包仍为 0.1.0，未签名；本阶段没有发布到 GitHub Releases、自动更新旧安装或创建 tag。

## 固定资源与构建

资源含最新 providers、runtime_bridge/runtime_settings、Main/Preload/Renderer Settings、
私有 Windows x64 Python 3.12、私有 Node、cryptography 和 MCP SDK 2.2.0。
`desktop/requirements-packaged.txt` 固定 29 个 Python distribution（包含传递依赖）；
官方 Filesystem Server 2026.8.31 及 103 个 npm 包沿原 package-lock 固定。
只复制公开 `tests/fixtures/mcp-readonly/metadata.txt`，78 bytes，原根目录和 get_file_info
单工具白名单不变；不复制完整测试目录、用户数据、.env、配置文件或环境变量值。

Python staging 只读取固定依赖目录中的 wheel RECORD，校验版本、逐文件摘要与缺文件，
不复制开发机整个 site-packages；忽略外部 console wrapper、pycache/pyc。npm 依赖
按原 lock 校验安装版本，不使用 npx、shell 或运行时下载。安装环境的 Node 路径固定；
私有 Node 丢失时返回安全错误，禁止拾取全局 Node。

```powershell
cd .\desktop
npm.cmd ci
$env:DATA_AGENT_PYTHON = "C:\path\to\windows-python-3.12\python.exe"
& $env:DATA_AGENT_PYTHON -I -m pip install --only-binary=:all: --target .packaging-deps -r requirements-packaged.txt
npm.cmd ci --prefix ..\integrations\mcp-filesystem
npm.cmd run pack:win
node scripts/audit-packaged-resources.cjs
npm.cmd run verify:packaged-integrations
npm.cmd run test:smoke:packaged
```

`.packaging-deps` 是专用干净目录；版本不一致明确阻止构建，不自动下载或 fallback。
安装后资源可独立验收：

```powershell
node scripts/audit-packaged-resources.cjs "C:\path\to\installed\resources"
node scripts/verify-packaged-integrations.cjs --resources "C:\path\to\installed\resources"
node scripts/verify-packaged-smoke.cjs --executable "C:\path\to\installed\Data Analysis Agent.exe" --label phase2.9-installed
```

## 实际安装 exe 验收

NSIS `/S /CURRENTUSER /D=...` 实际安装成功，exit 0，包含 uninstaller。
打包和安装两套资源审核均 PASS：最新 Provider/Runtime/Settings 文件与源码或编译产物
一致，6549 个资源文件无 .env、用户 Settings 或 .git，公开 fixture 内容一致。

实际安装 exe 启动两次，独立 userData profile，不继承开发 PATH、Python 路径或 Key。
默认 deterministic / MCP disabled；外部模式页只有 model、endpoint、api_key_env，没有
真实 Key 输入。缺凭据明确失败且原模式保留。保存 deterministic + MCP enabled，真实
list_tools 注册元数据工具，CSV 分析完成（1580）；原 HITL 暂停/拒绝正确，拒绝后可继续
普通分析。关闭进程重新启动，非敏感配置和 MCP ready 恢复，随后停用 MCP，Session
11 条 messages / 20 个过程事件恢复，原 trace 保留，恢复不会发起新分析。

安装私有 Python 的独立检查还验证原 Factory 构造两种 Provider（外部模式仅使用进程内
合成凭据，不调用模型）、schema、Registry → MCP → ToolResult（实际 size=78）、目录
越界拒绝，以及缺 Server、私有 Node 或 Python SDK 的结构化错误；不修改业务协议。

Windows computer-use 补充复核确认首页、Settings 默认模式、外部字段、只读范围摘要及
原生 CSV/XLSX 对话框正确显示。后续原生 CSV 选择未完成：工具先报 element 不在缓存，
随后窗口消失、无法重绑定（window id was not found），原因未确认。不能把这项补充
步骤记为人工分析 PASS；安装 exe 的 CSV 选择/分析自动 smoke 使用确定性 chooser 答案，
其余 UI / Preload / Main / Python 全为真实链路。

## 回归与边界

最终 PASS：TypeScript、Desktop 38/38、Electron smoke、开发和 packaged E2E 各 10 步、
packaged/installed 双启动 smoke、Provider 79/79、MCP 48/48、联调 18/18、Settings 14/14、
新增打包安全 4/4、Node 13/13、Python 400/400、P0 15/15、P1 20/20、Robustness 25/25、
Day19 60/60、Regression Gate 11/11；security violations=0、contract failures=0。
打包 E2E 首轮 Windows viewport 1600 被量化为 1601px，独立原样复跑通过，未放宽断言。
64 个核心 Python 文件阶段前后 SHA256 不变；Provider/MCP contract/实现、AgentLoop、
Workflow、Skill、Session、Memory、HITL、Registry/Guardrail、Dataset/Chart、原分析 IPC/
Runtime Event 和评测标准均未改。Runtime 仅收紧安装场景的 Node 路径选择。

仍限 Windows x64、公开 fixture 根和单个只读元数据工具，协议权限白名单不是 OS 沙箱。
凭据可用性不代表远端模型兼容性。Phase 2.9 完成打包与自动验收后停止。
