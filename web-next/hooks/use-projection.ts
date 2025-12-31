import { useState } from "react";
import { apiFetch } from "@/lib/api-client";

export function useProjectionTrigger() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ updated: number } | null>(null);

  const trigger = async (limit = 200) => {
    setPending(true);
    setError(null);
    setResult(null);
    try {
      const res = await apiFetch<{ status: string; updated: number }>(
        `/api/v1/memory/embedding-project?limit=${limit}`,
        { method: "POST" },
      );
      setResult({ updated: res.updated });
      return res;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Błąd projekcji embeddingów";
      setError(msg);
      throw err;
    } finally {
      setPending(false);
    }
  };

  return { pending, error, result, trigger };
}
