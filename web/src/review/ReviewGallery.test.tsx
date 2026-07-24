import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ReviewGallery } from "./ReviewGallery";

test("renders clipped crop and spec overlays from numeric rect props", async () => {
  const onApprove = vi.fn();
  render(
    <ReviewGallery
      candidates={[
        {
          id: "c1",
          src: "a.png",
          imageWidth: 80,
          imageHeight: 48,
          cropRect: { x: -10, y: 8, w: 50, h: 24 },
          specRect: { x: 20, y: 4, w: 24, h: 24 },
        },
      ]}
      onApprove={onApprove}
      onReject={vi.fn()}
    />,
  );

  expect(screen.getByLabelText("crop-overlay-c1")).toHaveStyle({
    left: "0%",
    top: "16.666666666666664%",
    width: "50%",
    height: "50%",
  });
  expect(screen.getByLabelText("spec-overlay-c1")).toHaveStyle({
    left: "25%",
    top: "8.333333333333332%",
    width: "30%",
    height: "50%",
  });
  await userEvent.click(screen.getByRole("button", { name: "Approve c1" }));
  expect(onApprove).toHaveBeenCalledWith("c1");
});

test("shows an explicit empty state when no candidates are available", () => {
  render(<ReviewGallery candidates={[]} onApprove={vi.fn()} onReject={vi.fn()} />);
  expect(screen.getByText("No review candidates available.")).toBeInTheDocument();
});
