import { RuntimeClient } from "../bridge/runtimeClient";
import { SettingsStore } from "./settings-store";
import { SettingsFault, validateSettings, type SettingsSnapshot } from "../shared/settings";

export class SettingsController {
  private initialized = false;
  private queue: Promise<unknown> = Promise.resolve();
  constructor(private readonly runtime: RuntimeClient, private readonly store: SettingsStore) {
    runtime.processManager.on("exit", () => { this.initialized = false; });
  }
  private serial<T>(action: () => Promise<T>): Promise<T> {
    const next = this.queue.then(action, action);
    this.queue = next.catch(() => undefined);
    return next;
  }
  private async initialize(): Promise<void> {
    if (!this.initialized) {
      await this.runtime.applySettings(this.store.load(), true);
      this.initialized = true;
    }
  }
  get(): Promise<SettingsSnapshot> {
    return this.serial(async () => { await this.initialize(); return this.runtime.getSettings(); });
  }
  async ensureReady(): Promise<void> {
    const snapshot = await this.get();
    if (!snapshot.ready) throw new SettingsFault(snapshot.issue?.code ?? "settings_invalid", snapshot.issue?.message ?? "配置尚不可用。");
  }
  apply(input: unknown): Promise<SettingsSnapshot> {
    return this.serial(async () => {
      const config = validateSettings(input);
      // A valid explicit save can repair a corrupt file. Never run with an implicit default.
      const previous = await this.runtime.getSettings();
      const snapshot = await this.runtime.applySettings(config);
      try { this.store.save(config); }
      catch (error) {
        await this.runtime.applySettings(previous.config, true);
        throw error;
      }
      this.initialized = true;
      return snapshot;
    });
  }
}
