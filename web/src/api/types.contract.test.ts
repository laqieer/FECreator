import { expectTypeOf, test } from "vitest";
import type { LineageNode, Manifest, ReferencePack } from "./types";

test("LineageNode keeps required canonical lineage fields", () => {
  type RequiredLineageFields = Pick<LineageNode, "asset_id" | "operation" | "created_at">;
  expectTypeOf<RequiredLineageFields>().toEqualTypeOf<{
    asset_id: string;
    operation: "import_concept" | "create_neutral" | "refine_expression" | "variant_masked_edit" | "export_spec";
    created_at: string;
  }>();
});

test("ReferencePack mirrors the canonical reference contract", () => {
  expectTypeOf<ReferencePack>().toEqualTypeOf<{
    id: string;
    revision: number;
    source?: string;
    concept_art?: {
      role: string;
      path: string;
      sha256: string;
      media_type: string;
    }[];
    traits?: Record<string, string>;
    swatches?: string[];
    forbidden_changes?: string[];
    provenance?: string;
    rights?: string;
  }>();
});

test("Manifest mirrors the canonical manifest contract", () => {
  type CharacterRefPackRev = Manifest["character_ref_pack_rev"];
  expectTypeOf<CharacterRefPackRev>().toEqualTypeOf<number | null | undefined>();

  expectTypeOf<Manifest>().toEqualTypeOf<{
    version: "1.0";
    asset_type: "portrait";
    target_spec: "fe-gba-portrait-standard";
    workflow:
      | "text_to_portrait"
      | "concept_to_portrait"
      | "expression_refine"
      | "masked_variant";
    provider: string;
    character_ref_pack?: string | null;
    character_ref_pack_rev?: number | null;
    sources?: {
      kind: "text" | "concept_art" | "approved_portrait";
      ref: string;
    }[];
    edit?: {
      mask_path: string;
      protected_regions?: {
        x: number;
        y: number;
        w: number;
        h: number;
        label: string;
      }[];
    } | null;
    params?: Record<string, string | number | boolean>;
  }>();
});
