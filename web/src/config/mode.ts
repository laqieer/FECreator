import { DEMO_MODE, LOCAL_MODE, type AppMode } from "./constants";

export function appMode(): AppMode {
  return import.meta.env.VITE_FE_CREATOR_MODE === DEMO_MODE ? DEMO_MODE : LOCAL_MODE;
}

export function isDemo(): boolean {
  return appMode() === DEMO_MODE;
}