/**
 * Shell-safe construction of the Playwright `webServer` command.
 *
 * Playwright starts `webServer.command` through a shell, so an interpreter path
 * containing spaces (`C:\Program Files\Python312\python.exe`,
 * `/opt/py runtimes/bin/python`) must be quoted or the server never starts.
 * `FECREATOR_PYTHON` may already arrive quoted — CI sets it that way — so
 * quoting is idempotent, and the unquoted value stays available for the
 * argv-based `spawnSync` calls that must not see quote characters.
 */

const DOUBLE_QUOTE = '"';

export function unquote(value: string): string {
  const trimmed = value.trim();
  if (
    trimmed.length >= 2 &&
    trimmed.startsWith(DOUBLE_QUOTE) &&
    trimmed.endsWith(DOUBLE_QUOTE)
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

export function shellQuote(value: string): string {
  const bare = unquote(value);
  if (bare.length === 0) {
    throw new Error("FECREATOR_PYTHON must not be blank");
  }
  if (bare.includes(DOUBLE_QUOTE)) {
    throw new Error("FECREATOR_PYTHON must not contain a double quote character");
  }
  return `${DOUBLE_QUOTE}${bare}${DOUBLE_QUOTE}`;
}

export function pythonExecutable(configured: string | undefined): string {
  const bare = unquote(configured ?? "");
  return bare.length > 0 ? bare : "python";
}

export function pythonServeCommand(configured: string | undefined): string {
  return `${shellQuote(pythonExecutable(configured))} -m fecreator serve`;
}
