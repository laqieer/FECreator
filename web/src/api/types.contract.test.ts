import { expectTypeOf, test } from "vitest";
import type { LineageNode, ReferencePack } from "./types";

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
