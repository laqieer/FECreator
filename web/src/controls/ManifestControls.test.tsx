import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ManifestControls } from "./ManifestControls";
import type { Manifest, ReferencePack } from "../api/types";

const references: ReferencePack[] = [
  {
    id: "hero-pack",
    revision: 2,
    source: "local",
    concept_art: [],
    traits: {},
    swatches: [],
    forbidden_changes: [],
    provenance: "",
    rights: "",
  },
];

test("submits the selected workflow and pinned reference revision", async () => {
  const onSubmit = vi.fn();
  const user = userEvent.setup();
  render(
    <ManifestControls
      assets={["portrait"]}
      specs={["fe-gba-portrait-standard"]}
      providers={["fake"]}
      references={references}
      submitting={false}
      onSubmit={onSubmit}
    />,
  );

  await user.selectOptions(screen.getByLabelText("Workflow"), "masked_variant");
  await user.selectOptions(screen.getByLabelText("Reference pack"), "hero-pack");
  await user.selectOptions(screen.getByLabelText("Reference revision"), "2");
  await user.type(screen.getByLabelText("Mask path"), "masks/face.png");
  await user.click(screen.getByRole("button", { name: "Create job" }));

  expect(onSubmit).toHaveBeenCalledWith<Parameters<(value: Manifest) => void>>(
    expect.objectContaining({
      version: "1.0",
      asset_type: "portrait",
      target_spec: "fe-gba-portrait-standard",
      workflow: "masked_variant",
      character_ref_pack: "hero-pack",
      character_ref_pack_rev: 2,
      edit: { mask_path: "masks/face.png", protected_regions: [] },
    }),
  );
});

test("rejects invalid parameters before emitting a manifest", async () => {
  const onSubmit = vi.fn();
  const user = userEvent.setup();
  render(
    <ManifestControls
      assets={["portrait"]}
      specs={["fe-gba-portrait-standard"]}
      providers={["fake"]}
      references={[]}
      submitting={false}
      onSubmit={onSubmit}
    />,
  );

  fireEvent.change(screen.getByLabelText("Parameters JSON"), {
    target: { value: '{"nested": {}}' },
  });
  await user.click(screen.getByRole("button", { name: "Create job" }));

  expect(screen.getByRole("alert")).toHaveTextContent("Parameters must be a JSON object");
  expect(onSubmit).not.toHaveBeenCalled();
});
