import { existsSync, mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { defaultSettings, SettingsFault, validateSettings, type DesktopSettings } from "../shared/settings";

export class SettingsStore {
  readonly path: string;
  constructor(private readonly directory: string) { this.path = join(directory, "runtime-settings.json"); }
  load(): DesktopSettings {
    if (!existsSync(this.path)) return defaultSettings();
    try { return validateSettings(JSON.parse(readFileSync(this.path, "utf8"))); }
    catch { throw new SettingsFault("settings_storage_invalid", "保存的配置无法读取。请在设置中重新保存有效配置。"); }
  }
  save(input: DesktopSettings): void {
    const config = validateSettings(input);
    const temporary = this.path + ".tmp";
    try {
      mkdirSync(this.directory, { recursive: true });
      writeFileSync(temporary, JSON.stringify(config, null, 2) + "\n", { encoding: "utf8", mode: 0o600 });
      renameSync(temporary, this.path);
    } catch {
      if (existsSync(temporary)) { try { unlinkSync(temporary); } catch { /* fixed error */ } }
      throw new SettingsFault("settings_storage_failed", "无法保存配置，请检查应用数据目录权限。");
    }
  }
}
