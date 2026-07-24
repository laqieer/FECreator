const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { ini } = require("playwright-core/lib/utilsBundle");

function configPathFrom(argv, env) {
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--config") {
      return argv[index + 1];
    }
    if (argument.startsWith("--config=")) {
      return argument.slice("--config=".length);
    }
  }
  return env.PLAYWRIGHT_MCP_CONFIG;
}

function configSelectsBrowser(configPath, extensionOverride) {
  let content;
  try {
    content = readFileSync(resolve(configPath), "utf8");
  } catch {
    return false;
  }
  let config;
  if (configPath.endsWith(".ini")) {
    config = ini.parse(content);
  } else {
    try {
      config = JSON.parse(
        content.charCodeAt(0) === 0xfeff ? content.slice(1) : content,
      );
    } catch {
      config = ini.parse(content);
    }
  }

  const hasOwn = (object, key) =>
    object !== null &&
    typeof object === "object" &&
    Object.prototype.hasOwnProperty.call(object, key);
  const configEnablesExtension =
    hasOwn(config, "extension") &&
    (config.extension === true ||
      String(config.extension).toLowerCase() === "true");
  const extensionIsEnabled = extensionOverride ?? configEnablesExtension;
  if (extensionIsEnabled) {
    return false;
  }

  if (
    hasOwn(config, "browser.browserName") ||
    hasOwn(config, "browser.cdpEndpoint") ||
    hasOwn(config, "browser.remoteEndpoint") ||
    hasOwn(config, "browser.launchOptions.channel") ||
    hasOwn(config, "browser.launchOptions.executablePath")
  ) {
    return true;
  }

  const browser = config.browser;
  return (
    hasOwn(browser, "browserName") ||
    hasOwn(browser, "cdpEndpoint") ||
    hasOwn(browser, "remoteEndpoint") ||
    hasOwn(browser?.launchOptions, "channel") ||
    hasOwn(browser?.launchOptions, "executablePath")
  );
}

function browserIsConfigured(argv, env) {
  const browserArguments = [
    "--browser",
    "--executable-path",
    "--cdp-endpoint",
    "--endpoint",
  ];
  const hasBrowserArgument = argv.some((argument) =>
    browserArguments.some(
      (name) => argument === name || argument.startsWith(`${name}=`),
    ),
  );
  if (
    hasBrowserArgument ||
    env.PLAYWRIGHT_MCP_BROWSER ||
    env.PLAYWRIGHT_MCP_EXECUTABLE_PATH ||
    env.PLAYWRIGHT_MCP_CDP_ENDPOINT ||
    env.PLAYWRIGHT_MCP_ENDPOINT
  ) {
    return true;
  }

  const configPath = configPathFrom(argv, env);
  const extensionFromEnv =
    env.PLAYWRIGHT_MCP_EXTENSION === "true" ||
    env.PLAYWRIGHT_MCP_EXTENSION === "1"
      ? true
      : env.PLAYWRIGHT_MCP_EXTENSION === "false" ||
          env.PLAYWRIGHT_MCP_EXTENSION === "0"
        ? false
        : undefined;
  const extensionOverride = argv.includes("--extension")
    ? true
    : extensionFromEnv;
  return configPath
    ? configSelectsBrowser(configPath, extensionOverride)
    : false;
}

module.exports = { browserIsConfigured };
