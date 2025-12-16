import { useEffect, useRef, useState } from "react";
import { VenomWebSocket } from "@/lib/ws-client";

type TelemetryEntry = {
  id: string;
  ts: number;
  payload: unknown;
};

export function useTelemetryFeed(maxEntries = 100) {
  const [connected, setConnected] = useState(false);
  const [entries, setEntries] = useState<TelemetryEntry[]>([]);
  const wsRef = useRef<VenomWebSocket | null>(null);

  useEffect(() => {
    const socket = new VenomWebSocket("/ws/events", (data) => {
      setEntries((prev) => {
        const next = [
          {
            id: crypto.randomUUID(),
            ts: Date.now(),
            payload: data,
          },
          ...prev,
        ];
        return next.slice(0, maxEntries);
      });
    }, setConnected);

    wsRef.current = socket;
    socket.connect();
    return () => socket.disconnect();
  }, [maxEntries]);

  return { connected, entries };
}
