const { existsSync } = require("node:fs");
const { join } = require("node:path");
const { tools } = require("playwright-core/lib/coreBundle");
const { program } = require("playwright-core/lib/utilsBundle");
const { version } = require("playwright-core/package.json");
const { browserIsConfigured } = require("./playwrightArgs.cjs");

if (
  process.platform === "win32" &&
  !browserIsConfigured(process.argv, process.env)
) {
  const edgeRoots = [
    process.env["ProgramFiles(x86)"],
    process.env.ProgramFiles,
    process.env.LOCALAPPDATA,
  ].filter(Boolean);
  const edgeIsInstalled = edgeRoots.some((root) =>
    existsSync(join(root, "Microsoft", "Edge", "Application", "msedge.exe")),
  );

  if (edgeIsInstalled) {
    process.argv.push("--browser", "msedge");
  }
}

const command = program.version(`Version ${version}`).name("Playwright MCP");
tools.decorateMCPCommand(command, version);
void command.parseAsync(process.argv);
