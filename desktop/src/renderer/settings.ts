import type { DesktopSettings, SettingsSnapshot } from "../shared/settings";

const explanations: Record<string, string> = {
  settings_invalid: "配置格式无效。请检查模型名称、服务地址和凭据变量名；不要填写真实 API Key。",
  settings_missing_fields: "请填写模型名称、服务地址和 API Key 环境变量名。",
  settings_missing_credentials: "所选环境变量中没有可用凭据。请在系统环境中设置后重启应用。",
  settings_mcp_unavailable: "只读文件服务不可用，请检查本机 MCP 依赖。原配置没有被替换。",
  settings_busy: "请等待当前分析结束后再应用配置。",
  settings_storage_invalid: "保存的配置无法读取。请重新填写并保存有效配置；当前分析被阻止。",
  settings_storage_failed: "无法保存配置，请检查应用数据目录权限。",
};

export function installSettings(): { refresh: () => Promise<void> } {
  const form = document.querySelector<HTMLFormElement>("#runtime-settings-form")!;
  const provider = document.querySelector<HTMLSelectElement>("#settings-provider")!;
  const model = document.querySelector<HTMLInputElement>("#settings-model")!;
  const endpoint = document.querySelector<HTMLInputElement>("#settings-endpoint")!;
  const keyEnv = document.querySelector<HTMLInputElement>("#settings-key-env")!;
  const mcp = document.querySelector<HTMLInputElement>("#settings-mcp-enabled")!;
  const fields = document.querySelector<HTMLElement>("#settings-external-fields")!;
  const save = document.querySelector<HTMLButtonElement>("#settings-save")!;
  const reload = document.querySelector<HTMLButtonElement>("#settings-reload")!;
  const error = document.querySelector<HTMLElement>("#settings-error")!;
  const feedback = document.querySelector<HTMLElement>("#settings-feedback")!;
  const mode = document.querySelector<HTMLElement>("#settings-current-mode")!;
  let busy = false;
  const updateFields = (): void => {
    fields.hidden = provider.value !== "openai-compatible";
    [model, endpoint, keyEnv].forEach((field) => { field.disabled = fields.hidden; });
  };
  const showError = (code: string): void => {
    error.textContent = explanations[code] ?? "配置暂时不可用，请重试。";
    error.dataset.code = code;
    error.hidden = false;
  };
  const render = (snapshot: SettingsSnapshot): void => {
    const config = snapshot.config;
    provider.value = config.provider.provider_id;
    model.value = config.provider.model_name ?? "";
    endpoint.value = config.provider.endpoint ?? "";
    keyEnv.value = config.provider.api_key_env ?? "";
    mcp.checked = config.mcp.enabled;
    mode.textContent = config.provider.provider_id === "deterministic" ? "当前模式：本地 / 测试（deterministic）" : "当前模式：外部模型（OpenAI-compatible）";
    mode.dataset.ready = String(snapshot.ready);
    document.querySelector("#settings-credentials")!.textContent = {
      not_required: "本地模式不需要 API 凭据。", available: "凭据可用（仅检查环境变量，未验证远端服务）。",
      missing: "缺少可用凭据。", unknown: "凭据状态尚不可确认。",
    }[snapshot.credentials];
    document.querySelector("#settings-mcp-status")!.textContent = { disabled: "已停用", ready: "已启用 · 只读", unavailable: "不可用 · 分析被阻止" }[snapshot.mcp.status];
    document.querySelector("#settings-mcp-root")!.textContent = snapshot.mcp.root_summary;
    document.querySelector("#settings-mcp-tools")!.textContent = snapshot.mcp.registered_tools.length ? "文件 / 目录元数据（get_file_info）" : "未注册工具";
    updateFields();
    if (snapshot.issue) showError(snapshot.issue.code);
  };
  const operation = async (apply: boolean): Promise<void> => {
    if (busy) return;
    busy = true; save.disabled = reload.disabled = true;
    error.hidden = true; feedback.textContent = apply ? "正在校验并保存…" : "正在读取配置…";
    try {
      const external = provider.value === "openai-compatible";
      const config: DesktopSettings = { provider: { provider_id: external ? "openai-compatible" : "deterministic",
        model_name: external ? model.value.trim() || null : null,
        endpoint: external ? endpoint.value.trim() || null : null,
        api_key_env: external ? keyEnv.value.trim() || null : null }, mcp: { enabled: mcp.checked } };
      const result = apply ? await window.desktopSettings.applySettings(config) : await window.desktopSettings.getSettings();
      if (!result.ok) {
        showError(result.error.code);
        if (!apply) { mode.textContent = "当前配置不可用"; mode.dataset.ready = "false"; }
        feedback.textContent = apply ? "未应用新配置。" : "未加载配置。";
      } else {
        render(result.data);
        feedback.textContent = apply ? "已保存，用于后续新分析。" : "已读取当前配置。";
      }
    } catch {
      showError("settings_unavailable"); feedback.textContent = "未应用新配置。";
    } finally { busy = false; save.disabled = reload.disabled = false; }
  };
  provider.addEventListener("change", updateFields);
  form.addEventListener("submit", (event) => { event.preventDefault(); void operation(true); });
  reload.addEventListener("click", () => { void operation(false); });
  updateFields();
  return { refresh: () => operation(false) };
}
