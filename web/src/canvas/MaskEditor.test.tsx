import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { emptyMask } from "./maskModel";

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
      mask={emptyMask(96, 80)}
      protectedRegions={[
        { x: 0, y: 0, w: 10, h: 10, label: "face" },
        { x: 20, y: 20, w: 10, h: 10, label: "hair" },
      ]}
      onChange={vi.fn()}
      onClear={vi.fn()}
      onUndo={vi.fn()}
      canUndo
    />,
  );
  expect(screen.getByTestId("stage")).toBeInTheDocument();
  expect(screen.getAllByTestId("rect")).toHaveLength(2);
});

test("paints through pointer input and exposes clear/undo controls", () => {
  const onChange = vi.fn();
  const onClear = vi.fn();
  const onUndo = vi.fn();

  render(
    <MaskEditor
      width={4}
      height={4}
      mask={emptyMask(4, 4)}
      protectedRegions={[]}
      onChange={onChange}
      onClear={onClear}
      onUndo={onUndo}
      canUndo
    />,
  );

  const surface = screen.getByLabelText("mask-paint-surface");
  Object.defineProperty(surface, "getBoundingClientRect", {
    value: () => ({ left: 0, top: 0, width: 40, height: 40, right: 40, bottom: 40 }),
  });

  fireEvent.pointerDown(surface, { clientX: 15, clientY: 15, buttons: 1 });

  expect(onChange).toHaveBeenCalledWith(expect.any(Array));
  expect(onChange.mock.calls[0][0][1][1]).toBe(true);

  fireEvent.click(screen.getByRole("button", { name: "Clear mask" }));
  fireEvent.click(screen.getByRole("button", { name: "Undo mask stroke" }));
  expect(onClear).toHaveBeenCalled();
  expect(onUndo).toHaveBeenCalled();
});
