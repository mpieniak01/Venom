import { useCallback, useEffect, useRef, useState } from "react";

export type OpenRouterPurpose = "chat" | "tasks" | "programming";
export interface OpenRouterModel {
  id: string; name: string; description: string; context_length: number | null;
  input_price_per_million: string | null; output_price_per_million: string | null;
  supports_tools: boolean; connected: boolean; available?: boolean; reason?: string | null;
}
export interface OpenRouterSearchResult {
  models: OpenRouterModel[]; total: number; count: number; offset: number; limit: number;
  next_offset: number | null; fetched_at: string; source: string;
}
const base = "/api/v1/openrouter/models";
async function responseJson(response: Response) {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export function useOpenRouterModels(onChanged?: () => Promise<unknown>) {
  const [query, updateQuery] = useState("");
  const [purpose, updatePurpose] = useState<OpenRouterPurpose>("chat");
  const [category, updateCategory] = useState("");
  const [results, setResults] = useState<OpenRouterSearchResult | null>(null);
  const [connected, setConnected] = useState<OpenRouterModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [connectedLoading, setConnectedLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const searchSequence = useRef(0);
  const connectedSequence = useRef(0);
  const operations = useRef(new Set<string>());
  const mounted = useRef(true);
  const changed = useRef(onChanged); changed.current = onChanged;

  const loadConnected = useCallback(async () => {
    const sequence = ++connectedSequence.current;
    setConnectedLoading(true);
    try {
      const data = await responseJson(await fetch(`${base}/connected`));
      if (mounted.current && sequence === connectedSequence.current) setConnected(data.models || []);
    } catch (e) {
      if (mounted.current && sequence === connectedSequence.current) setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      if (mounted.current && sequence === connectedSequence.current) setConnectedLoading(false);
    }
  }, []);
  const cancelPending = useCallback(() => { ++searchSequence.current; ++connectedSequence.current; }, []);
  useEffect(() => {
    mounted.current = true;
    void loadConnected();
    return () => { mounted.current = false; cancelPending(); };
  }, [loadConnected, cancelPending]);

  const invalidate = () => { ++searchSequence.current; setLoading(false); setResults(null); };
  const setQuery = (value: string) => { invalidate(); updateQuery(value); };
  const setPurpose = (value: OpenRouterPurpose) => { invalidate(); updatePurpose(value); };
  const setCategory = (value: string) => { invalidate(); updateCategory(value); };
  const search = async (offset = 0) => {
    const sequence = ++searchSequence.current;
    setLoading(true); setError(null);
    const params = new URLSearchParams({ q: query.trim(), purpose, offset: String(offset), limit: "25" });
    if (category) params.set("category", category);
    try {
      const data = await responseJson(await fetch(`${base}/search?${params}`));
      if (mounted.current && sequence === searchSequence.current) setResults(data);
    } catch (e) {
      if (mounted.current && sequence === searchSequence.current) setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      if (mounted.current && sequence === searchSequence.current) setLoading(false);
    }
  };
  const manage = async (id: string, connect: boolean) => {
    if (operations.current.has(id)) return;
    operations.current.add(id); setPending(current => ({ ...current, [id]: true })); setError(null);
    try {
      await responseJson(await fetch(`${base}/${connect ? "connect" : "disconnect"}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model_id: id }),
      }));
      if (!mounted.current) return;
      await loadConnected();
      await changed.current?.();
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      operations.current.delete(id);
      if (mounted.current) setPending(current => ({ ...current, [id]: false }));
    }
  };
  return { query, setQuery, purpose, setPurpose, category, setCategory, results, connected, loading, connectedLoading, error, pending, search, manage, loadConnected };
}
