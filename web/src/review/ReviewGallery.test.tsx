import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ReviewGallery } from "./ReviewGallery";

test("approve fires with candidate id", async () => {
  const onApprove = vi.fn();
  render(
    <ReviewGallery
      candidates={[{ id: "c1", src: "a.png" }]}
      onApprove={onApprove}
      onReject={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("crop-overlay-c1")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Approve c1" }));
  expect(onApprove).toHaveBeenCalledWith("c1");
});

test("shows an explicit empty state when no candidates are available", () => {
  render(<ReviewGallery candidates={[]} onApprove={vi.fn()} onReject={vi.fn()} />);
  expect(screen.getByText("No review candidates available.")).toBeInTheDocument();
});
