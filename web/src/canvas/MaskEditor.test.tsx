import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

test("supports keyboard painting and emits protected regions in the mask draft", async () => {
  const onChange = vi.fn();
  const onDraftChange = vi.fn();
  const user = userEvent.setup();

  render(
    <MaskEditor
      width={4}
      height={4}
      mask={emptyMask(4, 4)}
      maskPath="masks/hero.png"
      protectedRegions={[{ x: 1, y: 1, w: 2, h: 2, label: "face" }]}
      onChange={onChange}
      onDraftChange={onDraftChange}
      onClear={vi.fn()}
    />,
  );

  const surface = screen.getByRole("application", { name: "mask-paint-surface" });
  surface.focus();
  await user.keyboard("{ArrowRight}{ArrowDown}{Space}");

  expect(onChange).toHaveBeenCalledWith(expect.any(Array));
  expect(onDraftChange).toHaveBeenLastCalledWith({
    mask_path: "masks/hero.png",
    protected_regions: [{ x: 1, y: 1, w: 2, h: 2, label: "face" }],
  });

  await user.type(screen.getByLabelText("x"), "0");
  await user.type(screen.getByLabelText("y"), "2");
  await user.type(screen.getByLabelText("w"), "1");
  await user.type(screen.getByLabelText("h"), "1");
  await user.type(screen.getByLabelText("label"), "hair");
  await user.click(screen.getByRole("button", { name: "Add protected region" }));

  expect(onDraftChange).toHaveBeenLastCalledWith({
    mask_path: "masks/hero.png",
    protected_regions: [
      { x: 1, y: 1, w: 2, h: 2, label: "face" },
      { x: 0, y: 2, w: 1, h: 1, label: "hair" },
    ],
  });
});

test("rejects a protected region with blank coordinates", async () => {
  const onDraftChange = vi.fn();
  const user = userEvent.setup();
  render(
    <MaskEditor
      width={4}
      height={4}
      mask={emptyMask(4, 4)}
      maskPath="masks/hero.png"
      protectedRegions={[]}
      onChange={vi.fn()}
      onDraftChange={onDraftChange}
      onClear={vi.fn()}
    />,
  );

  await user.type(screen.getByLabelText("w"), "1");
  await user.type(screen.getByLabelText("h"), "1");
  await user.type(screen.getByLabelText("label"), "hair");
  await user.click(screen.getByRole("button", { name: "Add protected region" }));

  expect(screen.getByRole("alert")).toHaveTextContent("Enter a label and non-negative integer region bounds.");
  expect(onDraftChange).not.toHaveBeenCalled();
});

test("clamps the keyboard cursor to the mask grid and announces its position", async () => {
  const onChange = vi.fn();
  const user = userEvent.setup();

  render(
    <MaskEditor
      width={40}
      height={40}
      mask={emptyMask(2, 2)}
      protectedRegions={[]}
      onChange={onChange}
      onClear={vi.fn()}
    />,
  );

  const surface = screen.getByRole("application", { name: "mask-paint-surface" });
  surface.focus();
  expect(screen.getByRole("status")).toHaveTextContent("Mask cursor at column 0, row 0.");

  await user.keyboard("{ArrowRight}{ArrowRight}{ArrowRight}{ArrowDown}{ArrowDown}{ArrowDown}");
  expect(screen.getByRole("status")).toHaveTextContent("Mask cursor at column 1, row 1.");

  await user.keyboard("{Enter}");
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(onChange.mock.calls[0][0][1][1]).toBe(true);
});

test("labels each protected region with its bounds", () => {
  render(
    <MaskEditor
      width={96}
      height={80}
      mask={emptyMask(96, 80)}
      protectedRegions={[{ x: 4, y: 6, w: 10, h: 12, label: "face" }]}
      onChange={vi.fn()}
      onClear={vi.fn()}
    />,
  );

  expect(
    screen.getByLabelText("Protected region face at x 4, y 6, width 10, height 12"),
  ).toBeInTheDocument();
});
