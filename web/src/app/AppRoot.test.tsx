import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { AppRoot } from "./AppRoot";
import { createComposition } from "./composition";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("demo composition shows the banner, runs an in-memory timeline, and makes no network calls", async () => {
  const fetchSpy = vi.fn();
  const webSocketSpy = vi.fn();
  vi.stubGlobal("fetch", fetchSpy);
  vi.stubGlobal("WebSocket", webSocketSpy);
  const user = userEvent.setup();

  render(<AppRoot composition={createComposition("demo")} />);

  expect(screen.getByRole("note", { name: "Demo mode notice" })).toBeInTheDocument();
  expect(await screen.findByText("1 asset type available")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Create job" }));
  await user.click(screen.getByRole("tab", { name: "Timeline" }));

  expect(await screen.findByText("Sample job completed. No real assets were produced.")).toBeInTheDocument();
  expect(await screen.findByText("Timeline snapshot complete.")).toBeInTheDocument();

  expect(fetchSpy).not.toHaveBeenCalled();
  expect(webSocketSpy).not.toHaveBeenCalled();
});

test("demo composition loads the seeded candidate review image without network errors", async () => {
  const fetchSpy = vi.fn();
  const webSocketSpy = vi.fn();
  const createObjectURL = vi.fn(() => "blob:demo-review-image");
  class ReviewUrl extends URL {
    static createObjectURL = createObjectURL;
    static revokeObjectURL = vi.fn();
  }

  vi.stubGlobal("fetch", fetchSpy);
  vi.stubGlobal("WebSocket", webSocketSpy);
  vi.stubGlobal("URL", ReviewUrl);

  render(<AppRoot composition={createComposition("demo")} />);

  expect(await screen.findByAltText("Candidate candidate/package/portrait.png")).toHaveAttribute(
    "src",
    "blob:demo-review-image",
  );
  expect(createObjectURL).toHaveBeenCalledWith(expect.objectContaining({ type: "image/png" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(fetchSpy).not.toHaveBeenCalled();
  expect(webSocketSpy).not.toHaveBeenCalled();
});

test("local composition omits the banner and uses the real HTTP client", async () => {
  const fetchSpy = vi.fn(async (input: string) => {
    const payload =
      input === "/api/assets"
        ? ["portrait"]
        : input === "/api/specs"
          ? ["fe-gba-portrait-standard"]
          : input === "/api/providers"
            ? ["fake"]
            : [];
    return { ok: true, json: async () => payload };
  });
  vi.stubGlobal("fetch", fetchSpy);

  render(<AppRoot composition={createComposition("local")} />);

  expect(screen.queryByRole("note", { name: "Demo mode notice" })).not.toBeInTheDocument();
  expect(await screen.findByText("1 asset type available")).toBeInTheDocument();
  expect(fetchSpy).toHaveBeenCalledWith("/api/assets", undefined);
});
