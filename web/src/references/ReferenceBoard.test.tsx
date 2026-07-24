import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ReferenceBoard } from "./ReferenceBoard";

test("shows swatches and edits manifest", async () => {
  const onChange = vi.fn();
  render(
    <ReferenceBoard
      swatches={["#aa2222", "#2222aa"]}
      manifestText="{}"
      onManifestChange={onChange}
    />,
  );
  expect(screen.getAllByLabelText(/swatch/)).toHaveLength(2);
  await userEvent.type(screen.getByRole("textbox", { name: "Manifest JSON" }), "x");
  expect(onChange).toHaveBeenCalled();
});

test("shows an explicit empty state when no swatches are present", () => {
  render(<ReferenceBoard swatches={[]} manifestText="{}" onManifestChange={vi.fn()} />);
  expect(screen.getByText("No reference swatches loaded.")).toBeInTheDocument();
});
