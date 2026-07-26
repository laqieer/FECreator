import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ReferenceBoard } from "./ReferenceBoard";
import type { ReferencePack } from "../api/types";

const references: ReferencePack[] = [
  {
    id: "hero",
    revision: 1,
    source: "local",
    concept_art: [],
    traits: {},
    swatches: ["#aa2222"],
    forbidden_changes: [],
    provenance: "approved",
    rights: "original",
  },
  {
    id: "hero",
    revision: 2,
    source: "local",
    concept_art: [],
    traits: {},
    swatches: ["#2222aa"],
    forbidden_changes: [],
    provenance: "approved",
    rights: "original",
  },
];

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

test("selects a persisted reference revision for the manifest", async () => {
  const onSelect = vi.fn();
  render(
    <ReferenceBoard
      references={references}
      selectedReference={{ id: "hero", revision: 1 }}
      onSelectReference={onSelect}
      manifestText="{}"
      onManifestChange={vi.fn()}
    />,
  );

  await userEvent.selectOptions(screen.getByLabelText("Reference revision"), "2");
  expect(onSelect).toHaveBeenCalledWith({ id: "hero", revision: 2 });
  expect(screen.getByLabelText("swatch #aa2222")).toBeInTheDocument();
});

test("clears a locally selected revision when the manifest clears its reference", async () => {
  const { rerender } = render(
    <ReferenceBoard
      references={references}
      selectedReference={undefined}
      manifestText="{}"
      onManifestChange={vi.fn()}
    />,
  );

  await userEvent.selectOptions(screen.getByLabelText("Reference pack"), "hero");
  rerender(
    <ReferenceBoard
      references={references}
      selectedReference={null}
      manifestText="{}"
      onManifestChange={vi.fn()}
    />,
  );

  expect(screen.getByLabelText("Reference pack")).toHaveValue("");
  expect(screen.getByText("No reference swatches loaded.")).toBeInTheDocument();
});
