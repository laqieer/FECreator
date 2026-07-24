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
