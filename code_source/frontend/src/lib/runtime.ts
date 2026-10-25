/** Browser runtime configuration (/runtime-config.js, loaded before the app). */
export const runtime: AljRuntime = window.ALJ_RUNTIME ?? { env: "prod" };

/** Dev mode: Firebase Auth emulator of the fake "demo-alj" project, fake data. */
export const isEmulator = runtime.env === "dev";
