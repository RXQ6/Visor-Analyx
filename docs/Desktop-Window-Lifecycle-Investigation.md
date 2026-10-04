# Phase 2.9.1：CSV 选择与窗口生命周期专项排查

2026-10-02。**dev、真实 unpacked exe、真实 installed exe 专项复验通过；历史第一次
窗口消失的准确触发原因仍未证实，Phase 2.9 不因此标记为最终完全通过。**

## 代码审查与结论边界

- `files:select` 使用 `BrowserWindow.fromWebContents(event.sender)` 获取请求窗口，传给
  `dialog.showOpenDialog(parent, options)`；三种形态均断言实际 parent 为同一个主窗口。
- CSV 注册成功、取消及失败均通过原 IPC 返回；Renderer 只更新 DOM、显示错误和恢复按钮。
  选择路径不调用 hide/close/minimize/destroy，也不触发 reload 或清理 IPC listener。
- Main handler 全局注册一次，preload 的 unsubscribe 只移除对应事件订阅。专项证明选择、
  失败重试及显式 Renderer reload 后仍可调用 Session IPC、接收真实 run_completed。
- 当前主窗口在启动回调中使用局部变量。这本身不足以证明 BrowserWindow 引用丢失；
  本轮没有基于这一猜测添加全局引用或改变窗口生命周期。
- dev 与两种成品共用生产 Main/Preload/Renderer；区别主要为资源和解释器路径。

## 本轮实际观察

1. 原生对话框打开后，computer-use 返回文件名元素，但使用该索引报
   `element ... is not available in cached app state`。刷新截图还曾显示与目标窗口不同的
   前台内容。这是验收工具绑定/缓存问题的直接证据，不能证明应用已经退出。
2. 第一组诊断中窗口出现 minimize/blur，BrowserWindow 仍存活；没有 close/closed、
   webContents destroyed 或 render-process-gone。隐藏启动的自动专项也记录到最小化；
   诊断 runner 改为正常可见启动后，三种形态通过。该差异不能单独证明历史问题的来源。
3. 用户确认本轮曾手动操作原生对话框；部分选项为 top_products.csv、dirty_numeric.csv、
   anomaly.csv，最初固定 sales.csv 的新专项因此失败。最初 runner 在断言失败后终止测试
   进程，可能造成本轮测试窗口消失；这属于诊断清理行为，不是 CSV 业务路径主动关窗。
   后续 native 失败保留进程供检查，原生选择核对实际文件与 DatasetSummary，另用固定
   sales.csv 保持 1580 数值断言。既有评测目标/断言/超时均未修改。
4. 最终三轮真实原生选择，由用户完成文件选择，测试程序记录对话框结果与后续真实链路。
   同一 PID、BrowserWindow id、webContents id 保持，窗口可见且未最小化；正常分析得到
   1580，注册失败后可重试，显式 reload 后仍可选择与分析。没有产品关窗复现。

**不能把上述多个本轮现象合并宣称为历史首次故障的已确定根因。** 历史记录没有当时的
窗口事件、进程退出信息和启动环境快照。目前没有证据支持修改业务窗口逻辑。

## 专项入口与覆盖

新增两个测试文件，不进入应用成品或 Python Runtime：

- `desktop/scripts/verify-window-lifecycle.cjs`：启动真正的生产 Main 或指定成品 exe，
  使用独立 userData、固定最小环境、仅本机 Main inspector；无 .env 或真实 Key。
- `desktop/tests/window-lifecycle-probe.cjs`：记录窗口/Renderer 事件、OS system command、
  JS hide/close/minimize/destroy 调用；校验 parent、存活、可见性、窗口 ID 与 IPC。

```powershell
cd desktop
node scripts/verify-window-lifecycle.cjs --mode dev
node scripts/verify-window-lifecycle.cjs --mode packaged
node scripts/verify-window-lifecycle.cjs --mode installed --executable "release/phase29-installed-20260930/Data Analysis Agent.exe"
# 各命令加 --native：首个真实 Windows 对话框由用户操作
```

`--native` 首次使用真实 Windows 对话框（测试侧预填 sales.csv），其余取消、空 CSV
失败、恢复和 reload 选择使用确定性 chooser 返回值；所有注册和计算始终由真实 Runtime
完成。原生与自动证据明确区分，不声称原生取消/错误输入已由人工覆盖。
等待使用事件、MutationObserver、Promise 和明确失败超时，没有固定 sleep 或放宽旧门禁。

最终 native 三种形态各 9 项，共 27/27；自动专项各 8 项，共 24/24。原生最终证据目录：

- `desktop/release/phase291-dev-native-yPfBbP/result.json`
- `desktop/release/phase291-packaged-native-Thz0Lb/result.json`
- `desktop/release/phase291-installed-native-edVUCU/result.json`

## 全量回归与交付状态

TypeScript build、Desktop 38/38、Electron smoke、dev/packaged E2E 各 10 步、unpacked/
installed 双启动 smoke、sidecar、资源审核及两套 Provider/MCP 私有运行时检查均 PASS。
Node 13/13、Python 400/400、P0 15/15、P1 20/20、Robustness 25/25、Day19 60/60、
Regression Gate 11/11 均 PASS；security violations=0、contract failures=0。

Desktop 首次沙箱执行因 GPU 子进程 DLL 加载错误失败，正常桌面权限原样重跑通过。
dev 诊断首次最小 PATH 缺 Node 导致 bridge_unavailable，仅修正测试环境；未改 Runtime。
65 个受保护 Python 文件阶段前后 SHA256 一致；未修改 Python Runtime、Provider/MCP
contract、AgentLoop/Workflow/Session/HITL 或既有 IPC/Event/评测。安装包未重建或发布。

报告：`tests/results/window-lifecycle-phase291-regression.json`。原 Phase 2.3 两次 HTTP 429
仍未最终验收；本轮未加载 .env、未使用真实 Key、未发送外部模型请求。

本轮没有产品修复。Phase 2.9.1 已完成本次排查与专项复验，历史故障根因仍保留为未确认；
不自动进入后续阶段，不用 finally show/restore/focus 掩盖未定位问题。
