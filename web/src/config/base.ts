import { DEMO_BASE_PATH, DEMO_MODE, LOCAL_BASE_PATH } from "./constants";

export function resolveBase(env: Record<string, string | undefined>): string {
  return env.VITE_FE_CREATOR_MODE === DEMO_MODE ? DEMO_BASE_PATH : LOCAL_BASE_PATH;
}
