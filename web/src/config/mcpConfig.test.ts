import { spawnSync } from "node:child_process";
import {
  existsSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { expect, test } from "vitest";

function findRepoRoot(start: string): string {
  let current = resolve(start);
  while (!existsSync(resolve(current, ".github", "mcp.json"))) {
    const parent = dirname(current);
    if (parent === current) {
      throw new Error(`repository root not found from ${start}`);
    }
    current = parent;
  }
  return current;
}

const repoRoot = findRepoRoot(process.cwd());
const requireFromRepo = createRequire(resolve(repoRoot, "package.json"));
const { browserIsConfigured } = requireFromRepo(
  "./.github/mcp/playwrightArgs.cjs",
) as {
  browserIsConfigured: (argv: string[], env: Record<string, string>) => boolean;
};

test("Playwright MCP uses the repository-local launcher", () => {
  const config = JSON.parse(
    readFileSync(resolve(repoRoot, ".github", "mcp.json"), "utf8"),
  ) as unknown;

  expect(config).toEqual({
    mcpServers: {
      playwright: {
        type: "stdio",
        command: "node",
        args: [".github/mcp/playwright.cjs"],
        tools: ["*"],
      },
    },
  });
});

test("Playwright MCP launcher exposes the CLI", () => {
  const result = spawnSync(
    process.execPath,
    [".github/mcp/playwright.cjs", "--help"],
    {
      cwd: repoRoot,
      encoding: "utf8",
    },
  );

  expect(result.status, result.stderr).toBe(0);
  expect(result.stdout).toContain("Usage: Playwright MCP");
});

test("Playwright MCP defers config read errors to the upstream CLI", () => {
  const result = spawnSync(
    process.execPath,
    [".github/mcp/playwright.cjs", "--config", "missing-playwright-mcp.json"],
    {
      cwd: repoRoot,
      encoding: "utf8",
    },
  );

  expect(result.status).toBe(1);
  expect(result.stderr).toContain("ENOENT");
  expect(result.stderr).not.toContain("playwrightArgs.cjs");
});

test("Playwright MCP output does not dirty the worktree", () => {
  const gitignore = readFileSync(resolve(repoRoot, ".gitignore"), "utf8");

  expect(gitignore.split(/\r?\n/)).toContain(".playwright-mcp/");
});

test("Playwright MCP recognizes every explicit browser argument form", () => {
  expect(
    browserIsConfigured(["node", "launcher", "--browser=firefox"], {}),
  ).toBe(true);
  expect(
    browserIsConfigured(
      ["node", "launcher", "--executable-path=C:/browser.exe"],
      {},
    ),
  ).toBe(true);
  expect(
    browserIsConfigured(["node", "launcher", "--browser", "firefox"], {}),
  ).toBe(true);
  expect(
    browserIsConfigured(
      ["node", "launcher", "--cdp-endpoint=ws://browser"],
      {},
    ),
  ).toBe(true);
  expect(
    browserIsConfigured(["node", "launcher"], {
      PLAYWRIGHT_MCP_ENDPOINT: "http://browser",
    }),
  ).toBe(true);
  expect(
    browserIsConfigured(["node", "launcher"], {
      PLAYWRIGHT_MCP_BROWSER: "webkit",
    }),
  ).toBe(true);
  expect(browserIsConfigured(["node", "launcher"], {})).toBe(false);
});

test("Playwright MCP config suppresses Edge only when it selects a browser", () => {
  const tempRoot = mkdtempSync(join(tmpdir(), "fecreator-mcp-"));
  const unrelated = join(tempRoot, "unrelated.json");
  const browserName = join(tempRoot, "browser-name.json");
  const channel = join(tempRoot, "channel.json");
  const executable = join(tempRoot, "executable.json");
  const extension = join(tempRoot, "extension.json");
  const remote = join(tempRoot, "remote.json");
  const ini = join(tempRoot, "browser.ini");

  try {
    writeFileSync(unrelated, JSON.stringify({ outputDir: "artifacts" }));
    writeFileSync(
      browserName,
      JSON.stringify({ browser: { browserName: "firefox" } }),
    );
    writeFileSync(
      channel,
      JSON.stringify({ browser: { launchOptions: { channel: "msedge" } } }),
    );
    writeFileSync(
      executable,
      JSON.stringify({
        browser: { launchOptions: { executablePath: "C:/browser.exe" } },
      }),
    );
    writeFileSync(
      extension,
      JSON.stringify({
        extension: true,
        browser: { launchOptions: { channel: "msedge" } },
      }),
    );
    writeFileSync(
      remote,
      JSON.stringify({ browser: { remoteEndpoint: "http://browser" } }),
    );
    writeFileSync(ini, "browser.launchOptions.channel=msedge\n");

    expect(
      browserIsConfigured(["node", "launcher", "--config", unrelated], {}),
    ).toBe(false);
    expect(
      browserIsConfigured(["node", "launcher", `--config=${browserName}`], {}),
    ).toBe(true);
    expect(
      browserIsConfigured(["node", "launcher", "--config", channel], {}),
    ).toBe(true);
    expect(
      browserIsConfigured(["node", "launcher"], {
        PLAYWRIGHT_MCP_CONFIG: executable,
      }),
    ).toBe(true);
    expect(
      browserIsConfigured(["node", "launcher", "--config", extension], {}),
    ).toBe(false);
    expect(
      browserIsConfigured(["node", "launcher", "--config", extension], {
        PLAYWRIGHT_MCP_EXTENSION: "false",
      }),
    ).toBe(true);
    expect(
      browserIsConfigured(
        ["node", "launcher", "--extension", "--config", channel],
        {},
      ),
    ).toBe(false);
    expect(
      browserIsConfigured(["node", "launcher", "--config", channel], {
        PLAYWRIGHT_MCP_EXTENSION: "true",
      }),
    ).toBe(false);
    expect(
      browserIsConfigured(["node", "launcher", "--config", remote], {}),
    ).toBe(true);
    expect(browserIsConfigured(["node", "launcher", "--config", ini], {})).toBe(
      true,
    );
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});
