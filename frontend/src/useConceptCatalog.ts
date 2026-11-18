import { useCallback, useEffect, useState } from "react";
import { api, errorText } from "./api";
import type { Concept, Page } from "./types";

export async function loadConcepts(signal: AbortSignal): Promise<Concept[]> {
  const items = new Map<string, Concept>();
  let cursor: string | null = null;
  const seen = new Set<string>();
  do {
    const params = new URLSearchParams({ limit: "100" });
    if (cursor) params.set("cursor", cursor);
    const page = await api<Page<Concept>>("/concepts?" + params, { signal });
    for (const item of page.items) items.set(item.id, item);
    cursor = page.next_cursor;
    if (cursor && seen.has(cursor))
      throw new Error(
        "주제 목록을 끝까지 불러오지 못했습니다. 다시 시도해 주세요.",
      );
    if (cursor) seen.add(cursor);
  } while (cursor && !signal.aborted);
  return [...items.values()];
}

export function useConceptCatalog(enabled: boolean) {
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [generation, setGeneration] = useState(0);
  const refresh = useCallback(() => setGeneration((value) => value + 1), []);
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    loadConcepts(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setConcepts(items);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(errorText(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [enabled, generation]);
  useEffect(() => {
    if (!enabled) return;
    // Records created from Codex can add concepts while this tab is inactive.
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [enabled, refresh]);
  return { concepts, loading, error, refresh };
}
