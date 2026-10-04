import type { DesktopApi } from "../shared/ipc";
import type { SettingsApi } from "../shared/settings";

declare global {
  interface Window {
    agent: DesktopApi;
    desktopSettings: SettingsApi;
  }
}

export {};

