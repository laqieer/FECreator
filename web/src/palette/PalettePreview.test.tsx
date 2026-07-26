import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { PalettePreview } from "./PalettePreview";
import type { IndexedFrame } from "./framePreview";

const frames: IndexedFrame[] = [
  {
    id: "eyes-open",
    label: "Eyes open",
    kind: "eyes",
    width: 2,
    height: 2,
    pixels: [
      [0, 1],
      [1, 0],
    ],
  },
  {
    id: "mouth-talk",
    label: "Mouth talk",
    kind: "mouth",
    width: 2,
    height: 2,
    pixels: [
      [1, 1],
      [0, 0],
    ],
  },
];

test("renders one swatch per palette entry and lets the user select eye/mouth frames", async () => {
  const onSelectFrame = vi.fn();
  render(
    <PalettePreview
      palette={[[0, 248, 0], [80, 96, 200]]}
      frames={frames}
      selectedFrameId="eyes-open"
      onSelectFrame={onSelectFrame}
      scale={2}
    />,
  );

  expect(screen.getAllByLabelText(/palette-entry/)).toHaveLength(2);
  expect(screen.getByRole("img", { name: "Eyes open preview" })).toHaveStyle({ imageRendering: "pixelated" });
  await userEvent.click(screen.getByRole("radio", { name: "Mouth talk" }));
  expect(onSelectFrame).toHaveBeenCalledWith("mouth-talk");
});

test("shows an explicit empty state when no palette or frames are loaded", () => {
  render(<PalettePreview palette={[]} frames={[]} scale={3} />);
  expect(screen.getByText("No palette entries loaded.")).toBeInTheDocument();
  expect(screen.getByText("No eye or mouth frames available.")).toBeInTheDocument();
});

test("uses candidate artifact URLs for native target and expression previews", () => {
  render(
    <PalettePreview
      artifacts={[
        { role: "portrait", path: "package/portrait.png", url: "blob:portrait" },
        { role: "eyes_open", path: "package/eyes.png", url: "blob:eyes" },
      ]}
    />,
  );

  expect(screen.getByRole("img", { name: "Candidate native-size preview" })).toHaveAttribute(
    "src",
    "blob:portrait",
  );
  expect(screen.getByLabelText("target-spec-overlay")).toBeInTheDocument();
  expect(screen.getByLabelText("mouth1 expression cell")).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "eyes_open package/eyes.png" })).toHaveAttribute(
    "src",
    "blob:eyes",
  );
});

test("prefers the backend sheet artifact and never renders palette artifacts as images", () => {
  render(
    <PalettePreview
      palette={[[8, 16, 24]]}
      artifacts={[
        { role: "portrait", path: "package/other.png", url: "blob:portrait" },
        { role: "sheet", path: "candidate/package/hero.png", url: "blob:sheet" },
      ]}
    />,
  );

  expect(screen.getByRole("img", { name: "Candidate native-size preview" })).toHaveAttribute(
    "src",
    "blob:sheet",
  );
  expect(screen.queryByRole("img", { name: /^Palette / })).not.toBeInTheDocument();
});

test("reports an empty palette when only image artifacts are available", () => {
  render(
    <PalettePreview
      palette={[]}
      artifacts={[{ role: "sheet", path: "candidate/package/hero.png", url: "blob:sheet" }]}
    />,
  );

  expect(screen.getByText("No palette entries loaded.")).toBeInTheDocument();
});
