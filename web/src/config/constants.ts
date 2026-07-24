export const LOCAL_MODE = "local" as const;
export const DEMO_MODE = "demo" as const;
export const LOCAL_BASE_PATH = "/";
export const DEMO_BASE_PATH = "/FECreator/";

export type AppMode = typeof LOCAL_MODE | typeof DEMO_MODE;