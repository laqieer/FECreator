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
  await user.selectOptions(screen.getByLabelText("Reference pack for new job"), "hero-pack");
  await user.selectOptions(screen.getByLabelText("Reference revision for new job"), "2");
  await user.type(screen.getByLabelText("Approved base asset id"), "hero-candidate");
  await user.type(screen.getByLabelText("Mask path for new job"), "masks/face.png");
  await user.click(screen.getByRole("button", { name: "Create job" }));

  expect(onSubmit).toHaveBeenCalledWith<Parameters<(value: Manifest) => void>>(
    expect.objectContaining({
      version: "1.0",
      asset_type: "portrait",
      target_spec: "fe-gba-portrait-standard",
      workflow: "masked_variant",
      character_ref_pack: "hero-pack",
      character_ref_pack_rev: 2,
      parent_asset_id: "hero-candidate",
      edit: { mask_path: "masks/face.png", protected_regions: [] },
    }),
  );
});

test("requires an approved base asset id for workflows that consume one", async () => {
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

  await user.selectOptions(screen.getByLabelText("Workflow"), "expression_refine");
  await user.type(screen.getByLabelText("Approved base asset id"), "   ");
  await user.click(screen.getByRole("button", { name: "Create job" }));

  expect(onSubmit).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent(
    "An approved base asset id is required for this workflow.",
  );
});

test("omits the approved base asset id for originating workflows", async () => {
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

  expect(screen.queryByLabelText("Approved base asset id")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Create job" }));

  expect(onSubmit).toHaveBeenCalledWith<Parameters<(value: Manifest) => void>>(
    expect.objectContaining({ workflow: "text_to_portrait", parent_asset_id: null }),
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

test("rejects protected regions with extra keys before emitting a manifest", async () => {
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

  await user.selectOptions(screen.getByLabelText("Workflow"), "masked_variant");
  fireEvent.change(screen.getByLabelText("Protected regions JSON"), {
    target: {
      value: JSON.stringify([
        { x: 0, y: 0, w: 10, h: 10, label: "face", color: "red" },
      ]),
    },
  });
  await user.type(screen.getByLabelText("Mask path for new job"), "masks/face.png");
  await user.click(screen.getByRole("button", { name: "Create job" }));

  expect(screen.getByRole("alert")).toHaveTextContent("Protected regions must be a JSON array of valid regions.");
  expect(onSubmit).not.toHaveBeenCalled();
});

test("rejects protected regions with missing, wrong, or empty fields before emitting a manifest", async () => {
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

  await user.selectOptions(screen.getByLabelText("Workflow"), "masked_variant");
  fireEvent.change(screen.getByLabelText("Protected regions JSON"), {
    target: {
      value: JSON.stringify([
        { x: 0, y: 0, w: 10, h: 10 },
        { x: 0, y: 0, w: 10, h: 10, label: "" },
        { x: 0, y: 0, w: 10.5, h: 10, label: "hair" },
      ]),
    },
  });
  await user.type(screen.getByLabelText("Mask path for new job"), "masks/face.png");
  await user.click(screen.getByRole("button", { name: "Create job" }));

  expect(screen.getByRole("alert")).toHaveTextContent("Protected regions must be a JSON array of valid regions.");
  expect(onSubmit).not.toHaveBeenCalled();
});

test("uses a selected reference board revision in the manifest controls", async () => {
  const onSelectionChange = vi.fn();
  render(
    <ManifestControls
      assets={["portrait"]}
      specs={["fe-gba-portrait-standard"]}
      providers={["fake"]}
      references={references}
      selectedReference={{ id: "hero-pack", revision: 2 }}
      onSelectedReferenceChange={onSelectionChange}
      submitting={false}
      onSubmit={vi.fn()}
    />,
  );

  expect(screen.getByLabelText("Reference pack for new job")).toHaveValue("hero-pack");
  expect(screen.getByLabelText("Reference revision for new job")).toHaveValue("2");
});
