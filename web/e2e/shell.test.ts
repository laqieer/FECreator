import { describe, expect, test } from "vitest";
import { pythonExecutable, pythonServeCommand, shellQuote, unquote } from "./shell";

describe("python interpreter resolution", () => {
  test("falls back to the plain interpreter name", () => {
    expect(pythonExecutable(undefined)).toBe("python");
    expect(pythonExecutable("")).toBe("python");
    expect(pythonExecutable("   ")).toBe("python");
  });

  test("keeps a configured path unquoted for argv based spawns", () => {
    expect(pythonExecutable("/usr/bin/python3")).toBe("/usr/bin/python3");
    expect(pythonExecutable('"C:\\Program Files\\Python312\\python.exe"')).toBe(
      "C:\\Program Files\\Python312\\python.exe",
    );
  });
});

describe("shell quoting", () => {
  test("quotes a path containing spaces exactly once", () => {
    expect(shellQuote("C:\\Program Files\\Python312\\python.exe")).toBe(
      '"C:\\Program Files\\Python312\\python.exe"',
    );
    expect(shellQuote('"C:\\Program Files\\Python312\\python.exe"')).toBe(
      '"C:\\Program Files\\Python312\\python.exe"',
    );
  });

  test("quotes a plain command name too, so the shape never varies", () => {
    expect(shellQuote("python")).toBe('"python"');
  });

  test("refuses values a shell could not carry safely", () => {
    expect(() => shellQuote("")).toThrow(/blank/);
    expect(() => shellQuote('py"thon')).toThrow(/double quote/);
  });

  test("unquote is idempotent", () => {
    expect(unquote(unquote('"  python  "'))).toBe("python");
  });
});

describe("serve command", () => {
  test("builds a quoted, shell safe local server command", () => {
    expect(pythonServeCommand(undefined)).toBe('"python" -m fecreator serve');
    expect(pythonServeCommand("/opt/py runtimes/bin/python")).toBe(
      '"/opt/py runtimes/bin/python" -m fecreator serve',
    );
    expect(pythonServeCommand('"/opt/py runtimes/bin/python"')).toBe(
      '"/opt/py runtimes/bin/python" -m fecreator serve',
    );
  });
});
