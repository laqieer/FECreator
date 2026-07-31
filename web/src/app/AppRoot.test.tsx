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
  expect(
    screen.getByText("Local-first portrait and dialogue background review workbench."),
  ).toBeInTheDocument();
  expect(await screen.findByText("2 asset types available")).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "dialogue_background" })).toBeInTheDocument();

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

test("demo composition creates a native-size dialogue background offline", async () => {
  const fetchSpy = vi.fn();
  const webSocketSpy = vi.fn();
  class ReviewUrl extends URL {
    static createObjectURL = vi.fn(() => "blob:demo-dialogue-background");
    static revokeObjectURL = vi.fn();
  }

  vi.stubGlobal("fetch", fetchSpy);
  vi.stubGlobal("WebSocket", webSocketSpy);
  vi.stubGlobal("URL", ReviewUrl);
  const user = userEvent.setup();

  render(<AppRoot composition={createComposition("demo")} />);

  await screen.findByText("2 asset types available");
  await user.selectOptions(screen.getByLabelText("Asset type"), "dialogue_background");
  await user.type(screen.getByLabelText("Text source"), "a moonlit armory");
  await user.type(screen.getByLabelText("Asset name"), "armory");
  await user.type(screen.getByLabelText("Purpose"), "dialogue scene");
  await user.type(screen.getByLabelText("Source kind"), "text");
  await user.type(screen.getByLabelText("Source id"), "brief");
  await user.type(screen.getByLabelText("Source revision"), "1");
  await user.type(screen.getByLabelText("License note"), "original");
  await user.type(screen.getByLabelText("Source note"), "demo fixture");
  await user.click(screen.getByRole("button", { name: "Create job" }));
  await user.click(await screen.findByRole("button", { name: "Plan sources" }));
  await user.upload(
    screen.getByLabelText("Source files"),
    new File(["demo-source"], "armory.png", { type: "image/png" }),
  );
  await user.click(screen.getByRole("button", { name: "Submit sources" }));

  expect(
    await screen.findByAltText("Candidate candidate/package/armory.png"),
  ).toHaveAttribute("width", "240");
  expect(screen.getByAltText("Candidate candidate/package/armory.png")).toHaveAttribute(
    "height",
    "160",
  );
  await user.click(screen.getByRole("tab", { name: "Palette" }));
  expect(
    screen.getByText("Palette preview is only available for portrait jobs."),
  ).toBeInTheDocument();
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
