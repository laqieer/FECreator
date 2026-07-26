import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, test, vi } from "vitest";
import { createStubApiClient } from "../test/util";
import { useLineage } from "./useLineage";

test("loads the selected lineage node with its ancestors and children", async () => {
  const selected = await createStubApiClient().getLineage("candidate");
  const ancestor = { ...selected, asset_id: "root", parents: [] };
  const child = { ...selected, asset_id: "export", parents: ["candidate"] };
  const getLineage = vi.fn(async () => selected);
  const getLineageAncestors = vi.fn(async () => [ancestor]);
  const getLineageChildren = vi.fn(async () => [child]);
  const client = createStubApiClient({ getLineage, getLineageAncestors, getLineageChildren });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  const { result } = renderHook(() => useLineage(client, "candidate"), { wrapper });

  await waitFor(() => expect(result.current.data?.children).toEqual([child]));
  expect(getLineage).toHaveBeenCalledWith("candidate");
  expect(getLineageAncestors).toHaveBeenCalledWith("candidate");
  expect(getLineageChildren).toHaveBeenCalledWith("candidate");
});
