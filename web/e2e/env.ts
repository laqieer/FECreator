import { spawnSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { pythonExecutable, pythonServeCommand } from "./shell";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export { webRoot };

export const repoRoot = resolve(webRoot, "..");

// Loopback-only ports, overridable when the defaults are already taken.
export const localPort = Number(process.env.FECREATOR_E2E_PORT ?? 8791);
export const demoPort = Number(process.env.FECREATOR_E2E_DEMO_PORT ?? 4791);
export const localBaseUrl = `http://127.0.0.1:${localPort}`;
export const demoBaseUrl = `http://127.0.0.1:${demoPort}`;
export const demoBasePath = "/FECreator/";

// Each run gets its own data root so it never reuses persisted jobs from an
// earlier run or from an operator's own `fecreator serve` session.  It is
// computed once in the Playwright main process and shared with test workers and
// the server through the environment, so every process agrees on one store.
export const dataRoot =
  process.env.FECREATOR_E2E_DATA_ROOT ??
  join(webRoot, ".e2e-data", `run-${Date.now()}-${process.pid}`);

process.env.FECREATOR_E2E_DATA_ROOT = dataRoot;

const pythonCommand = pythonExecutable(process.env.FECREATOR_PYTHON);

// Playwright starts `webServer.command` through a shell, so the interpreter is
// quoted here; `pythonCommand` stays bare for the argv based spawns below.
export const serveCommand = pythonServeCommand(process.env.FECREATOR_PYTHON);

export const serveEnv: Record<string, string> = {
  FECREATOR_DATA_ROOT: dataRoot,
  FECREATOR_HOST: "127.0.0.1",
  FECREATOR_PORT: String(localPort),
};

export function createDataRoot(): void {
  mkdirSync(dataRoot, { recursive: true });
}

export function removeDataRoot(): void {
  rmSync(dataRoot, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
}

// HTTP exposes POST /api/jobs/{job_id}/build. This helper still uses the CLI to
// prepare candidate state for e2e flows that do not exercise that HTTP mutation.
export function buildCandidate(jobId: string): void {
  const result = spawnSync(pythonCommand, ["-m", "fecreator", "build", "--job", jobId], {
    cwd: repoRoot,
    env: { ...process.env, FECREATOR_DATA_ROOT: dataRoot },
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(
      `fecreator build --job ${jobId} exited with ${result.status}\n` +
        `stdout: ${result.stdout}\nstderr: ${result.stderr}`,
    );
  }
}
