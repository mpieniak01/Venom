import { useEffect, useState } from "react";
import { VenomWebSocket } from "@/lib/ws-client";
import { createBrowserUuid } from "@/lib/optional-modules/transport";

type TelemetryEntry = {
  id: string;
  ts: number;
  payload: unknown;
};

export function useTelemetryFeed(maxEntries = 100, enabled = true) {
  const [connected, setConnected] = useState(false);
  const [entries, setEntries] = useState<TelemetryEntry[]>([]);

  useEffect(() => {
    if (!enabled) return;
    const socket = new VenomWebSocket("/ws/events", (data) => {
      setEntries((prev) => {
        const next = [
          {
            id: createBrowserUuid(),
            ts: Date.now(),
            payload: data,
          },
          ...prev,
        ];
        return next.slice(0, maxEntries);
      });
    }, setConnected);

    socket.connect();
    return () => socket.disconnect();
  }, [maxEntries, enabled]);

  return { connected: enabled && connected, entries };
}
