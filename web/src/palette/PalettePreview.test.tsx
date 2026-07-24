import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { PalettePreview } from "./PalettePreview";

test("renders one swatch per palette entry and native size", () => {
  render(<PalettePreview palette={[[0, 248, 0], [80, 96, 200]]} scale={2} />);
  expect(screen.getAllByLabelText(/palette-entry/)).toHaveLength(2);
  expect(screen.getByText(/128×112/)).toBeInTheDocument();
});

test("includes explicit eye and mouth review guidance", () => {
  render(<PalettePreview palette={[]} scale={3} />);
  expect(screen.getByText("No palette entries loaded.")).toBeInTheDocument();
  expect(screen.getByText(/Eyes aligned/)).toBeInTheDocument();
  expect(screen.getByText(/Mouth centered/)).toBeInTheDocument();
});
