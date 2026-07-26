import { useQuery } from "@tanstack/react-query";
import type { ApiClient } from "../api/client";

export function useLineage(api: ApiClient, assetId: string | null, refreshKey = 0) {
  return useQuery({
    queryKey: ["lineage", assetId, refreshKey],
    enabled: assetId !== null,
    queryFn: async () => {
      const selectedId = assetId!;
      const [selected, ancestors, descendants] = await Promise.all([
        api.getLineage(selectedId),
        api.getLineageAncestors(selectedId),
        api.getLineageChildren(selectedId),
      ]);
      return { selected, ancestors, descendants };
    },
  });
}
