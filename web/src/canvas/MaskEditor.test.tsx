import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

vi.mock("react-konva", () => ({
  Stage: ({ children }: { children: React.ReactNode }) => <div data-testid="stage">{children}</div>,
  Layer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Rect: (props: { name?: string }) => <div data-testid="rect" aria-label={props.name} />,
}));

import { MaskEditor } from "./MaskEditor";

test("renders one rect per protected region", () => {
  render(
    <MaskEditor
      width={96}
      height={80}
      protectedRegions={[
        { x: 0, y: 0, w: 10, h: 10, label: "face" },
        { x: 20, y: 20, w: 10, h: 10, label: "hair" },
      ]}
    />,
  );
  expect(screen.getByTestId("stage")).toBeInTheDocument();
  expect(screen.getAllByTestId("rect")).toHaveLength(2);
});
