import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorText } from "./api";
import type { GraphData } from "./types";

/** Keep the visible graph current without moving an unchanged layout. */
export function useHomeGraph(active: boolean, enabled: boolean) {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const mounted = useRef(false);
  const generation = useRef(0);
  const snapshot = useRef("");
  const pending = useRef<{
    controller: AbortController;
    quiet: boolean;
  } | null>(null);

  const load = useCallback(async (quiet = false) => {
    if (!mounted.current || (quiet && (pending.current || document.hidden)))
      return;
    pending.current?.controller.abort();
    const request = { controller: new AbortController(), quiet };
    pending.current = request;
    const version = ++generation.current;
    if (!quiet) {
      setLoading(true);
      setError("");
    }
    try {
      const next = await api<GraphData>("/graph", {
        signal: request.controller.signal,
      });
      if (
        !mounted.current ||
        request.controller.signal.aborted ||
        version !== generation.current
      )
        return;
      const serialized = JSON.stringify(next);
      if (serialized !== snapshot.current) {
        snapshot.current = serialized;
        setData(next);
      }
      setError("");
    } catch (cause) {
      if (
        mounted.current &&
        !request.controller.signal.aborted &&
        version === generation.current
      )
        setError(errorText(cause));
    } finally {
      if (pending.current === request) {
        pending.current = null;
        if (mounted.current) setLoading(false);
      }
    }
  }, []);

  const cancelQuiet = useCallback(() => {
    if (!pending.current?.quiet) return;
    generation.current++;
    pending.current.controller.abort();
    pending.current = null;
  }, []);

  useEffect(() => {
    if (!enabled) return;
    mounted.current = true;
    void load();
    return () => {
      mounted.current = false;
      generation.current++;
      pending.current?.controller.abort();
      pending.current = null;
    };
  }, [enabled, load]);

  useEffect(() => {
    if (!active) return;
    const refresh = () => {
      if (document.hidden) cancelQuiet();
      else void load(true);
    };
    refresh();
    const timer = window.setInterval(refresh, 8000);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
      cancelQuiet();
    };
  }, [active, cancelQuiet, load]);

  return { data, loading, error, refresh: load };
}
