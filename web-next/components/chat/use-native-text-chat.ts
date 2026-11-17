"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchNativeTextCatalog, fetchNativeTextState, rollbackNativeText, selectNativeText, type NativeTextAdapter, type NativeTextState } from "@/lib/native-text-chat";

export function useNativeTextChat() {
  const [state, setState] = useState<NativeTextState>({selection: null, previous: null, persistent: false});
  const [adapters, setAdapters] = useState<NativeTextAdapter[]>([]);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const locked = useRef(false);
  const revision = useRef(0);
  const refresh = useCallback(async () => {
    const current = ++revision.current;
    try {
      const fresh = await fetchNativeTextState();
      if (current !== revision.current) return;
      setState(fresh); setReady(true);
      try {
        const catalog = await fetchNativeTextCatalog();
        if (current === revision.current) setAdapters(catalog);
      } catch { if (current === revision.current) setAdapters([]); }
    } catch {
      if (current === revision.current) { setReady(false); setError("chat2.nativeText.failed"); }
    }
  }, []);
  const invalidate = useCallback(() => { revision.current++; }, []);
  useEffect(() => {
    void refresh();
    const onFocus = () => { if (!locked.current) void refresh(); };
    window.addEventListener("focus", onFocus);
    return () => { invalidate(); window.removeEventListener("focus", onFocus); };
  }, [refresh, invalidate]);
  const change = useCallback(async (adapter?: string) => {
    if (locked.current) return false;
    locked.current = true; setBusy(true); setError(null); revision.current++;
    try {
      const fresh = adapter ? await selectNativeText(adapter, state.selection)
        : state.selection ? await rollbackNativeText(state.selection) : state;
      setState(fresh); setReady(true); return true;
    } catch {
      setError("chat2.nativeText.changed"); await refresh(); return false;
    } finally { locked.current = false; setBusy(false); }
  }, [state, refresh]);
  return {state, adapters, ready, busy, error, refresh, change};
}
export type NativeTextChat = ReturnType<typeof useNativeTextChat>;
