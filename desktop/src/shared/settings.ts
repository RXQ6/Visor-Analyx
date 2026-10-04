import type { IpcError, IpcResult } from "./ipc";

export const SETTINGS_CHANNELS = { get: "settings:get", apply: "settings:apply" } as const;
export interface DesktopSettings {
  provider: { provider_id: "deterministic" | "openai-compatible"; model_name: string | null; endpoint: string | null; api_key_env: string | null };
  mcp: { enabled: boolean };
}
export interface SettingsSnapshot {
  config: DesktopSettings;
  ready: boolean;
  issue: IpcError | null;
  credentials: "not_required" | "available" | "missing" | "unknown";
  mcp: { enabled: boolean; read_only: true; root_summary: string; registered_tools: string[]; status: "disabled" | "ready" | "unavailable" };
}
export interface SettingsApi {
  getSettings(): Promise<IpcResult<SettingsSnapshot>>;
  applySettings(input: DesktopSettings): Promise<IpcResult<SettingsSnapshot>>;
}
export class SettingsFault extends Error {
  constructor(readonly code: string, message: string) { super(message); }
}
export function defaultSettings(): DesktopSettings {
  return { provider: { provider_id: "deterministic", model_name: null, endpoint: null, api_key_env: null }, mcp: { enabled: false } };
}
function exact(value: unknown, keys: string[]): asserts value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).sort().join() !== [...keys].sort().join()) {
    throw new SettingsFault("settings_invalid", "配置包含不支持的字段。");
  }
}
export function validateSettings(input: unknown): DesktopSettings {
  exact(input, ["provider", "mcp"]);
  exact(input.provider, ["provider_id", "model_name", "endpoint", "api_key_env"]);
  exact(input.mcp, ["enabled"]);
  const provider = input.provider;
  if (!["deterministic", "openai-compatible"].includes(String(provider.provider_id)) || typeof input.mcp.enabled !== "boolean") {
    throw new SettingsFault("settings_invalid", "请选择支持的模式和只读 MCP 开关。");
  }
  const result = defaultSettings();
  if (provider.provider_id === "deterministic" && [provider.model_name, provider.endpoint, provider.api_key_env].some((value) => value !== null)) {
    throw new SettingsFault("settings_invalid", "本地模式不接受外部模型或凭据配置。");
  }
  result.provider.provider_id = provider.provider_id as DesktopSettings["provider"]["provider_id"];
  result.mcp.enabled = input.mcp.enabled;
  for (const [field, limit] of [["model_name", 128], ["endpoint", 1024], ["api_key_env", 128]] as const) {
    const value = provider[field];
    if (value !== null && (typeof value !== "string" || value.length > limit || value.trim() !== value)) {
      throw new SettingsFault("settings_invalid", "模型配置格式无效。");
    }
    if (typeof value === "string" && /^(sk-|AIza|Bearer\s)/i.test(value)) {
      throw new SettingsFault("settings_invalid", "此页面只接受凭据引用，不接受密钥。");
    }
    result.provider[field] = (value || null) as string | null;
  }
  if (result.provider.model_name && !/^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/.test(result.provider.model_name)) {
    throw new SettingsFault("settings_invalid", "模型名称格式无效。");
  }
  if (result.provider.api_key_env && !/^[A-Za-z_][A-Za-z0-9_]{0,127}$/.test(result.provider.api_key_env)) {
    throw new SettingsFault("settings_invalid", "请输入环境变量名，不是 API Key。");
  }
  if (result.provider.endpoint) {
    let valid = false;
    try {
      const url = new URL(result.provider.endpoint);
      valid = Boolean(url.hostname) && (url.protocol === "https:" ||
        (url.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname))) &&
        !url.username && !url.password && !url.search && !url.hash && !/\s/.test(result.provider.endpoint);
    } catch { /* fixed error below */ }
    if (!valid) throw new SettingsFault("settings_invalid", "地址须为 HTTPS 或本机 HTTP，且不含凭据、查询参数或片段。");
  }
  if (result.provider.provider_id === "openai-compatible" &&
    [result.provider.model_name, result.provider.endpoint, result.provider.api_key_env].some((value) => !value)) {
    throw new SettingsFault("settings_missing_fields", "请填写模型名称、服务地址和 API Key 环境变量名。");
  }
  return result;
}
