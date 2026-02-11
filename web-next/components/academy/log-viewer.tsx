"use client";

import { useEffect, useRef, useState } from "react";
import { Terminal, X, Pause, Play } from "lucide-react";
import { Button } from "@/components/ui/button";

interface LogViewerProps {
  jobId: string;
  onClose?: () => void;
}

interface LogEntry {
  line: number;
  message: string;
  timestamp?: string;
}

export function LogViewer({ jobId, onClose }: LogViewerProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("connecting");
  const logContainerRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const shouldAutoScrollRef = useRef(true);

  useEffect(() => {
    if (isPaused) return;

    // Połącz z SSE endpoint
    const eventSource = new EventSource(
      `/api/v1/academy/train/${jobId}/logs/stream`
    );
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
      setStatus("connected");
      setError(null);
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case "connected":
            setStatus("streaming");
            break;

          case "log":
            setLogs((prev) => [
              ...prev,
              {
                line: data.line,
                message: data.message,
                timestamp: data.timestamp,
              },
            ]);
            break;

          case "status":
            setStatus(data.status);
            if (data.status === "completed" || data.status === "failed") {
              eventSource.close();
              setIsConnected(false);
            }
            break;

          case "error":
            setError(data.message);
            setStatus("error");
            break;
        }
      } catch (err) {
        console.error("Failed to parse SSE event:", err);
      }
    };

    eventSource.onerror = () => {
      setIsConnected(false);
      setStatus("disconnected");
      setError("Connection lost");
      eventSource.close();
    };

    return () => {
      if (eventSource.readyState !== EventSource.CLOSED) {
        eventSource.close();
      }
    };
  }, [jobId, isPaused]);

  // Auto-scroll do dołu gdy pojawiają się nowe logi
  useEffect(() => {
    if (shouldAutoScrollRef.current && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  const handleScroll = () => {
    if (!logContainerRef.current) return;

    const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    shouldAutoScrollRef.current = isAtBottom;
  };

  const togglePause = () => {
    setIsPaused(!isPaused);
    if (isPaused && eventSourceRef.current) {
      eventSourceRef.current.close();
    }
  };

  const getStatusColor = () => {
    switch (status) {
      case "connected":
      case "streaming":
        return "text-emerald-400";
      case "completed":
        return "text-blue-400";
      case "failed":
      case "error":
        return "text-red-400";
      default:
        return "text-zinc-400";
    }
  };

  return (
    <div className="rounded-xl border border-white/10 bg-zinc-900/50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 bg-zinc-900 px-4 py-3">
        <div className="flex items-center gap-3">
          <Terminal className="h-5 w-5 text-emerald-400" />
          <div>
            <h3 className="text-sm font-semibold text-white">
              Training Logs - {jobId}
            </h3>
            <p className={`text-xs ${getStatusColor()}`}>
              {isConnected ? (
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                  {status}
                </span>
              ) : (
                status
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            onClick={togglePause}
            variant="ghost"
            size="sm"
            className="gap-2"
          >
            {isPaused ? (
              <>
                <Play className="h-4 w-4" />
                Resume
              </>
            ) : (
              <>
                <Pause className="h-4 w-4" />
                Pause
              </>
            )}
          </Button>
          {onClose && (
            <Button onClick={onClose} variant="ghost" size="sm">
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {/* Logs */}
      <div
        ref={logContainerRef}
        onScroll={handleScroll}
        className="h-96 overflow-y-auto bg-black/50 p-4 font-mono text-xs"
      >
        {error && (
          <div className="mb-2 rounded border border-red-500/20 bg-red-500/10 p-2 text-red-300">
            Error: {error}
          </div>
        )}

        {logs.length === 0 && !error && (
          <div className="flex h-full items-center justify-center text-zinc-500">
            {status === "connecting" ? "Connecting..." : "No logs yet"}
          </div>
        )}

        {logs.map((log) => (
          <div
            key={log.line}
            className="group flex gap-2 hover:bg-white/5 px-1 -mx-1"
          >
            <span className="text-zinc-600 select-none w-12 text-right shrink-0">
              {log.line}
            </span>
            {log.timestamp && (
              <span className="text-zinc-600 select-none shrink-0">
                {log.timestamp.split("T")[1]?.split("Z")[0] || log.timestamp}
              </span>
            )}
            <span className="text-zinc-300 break-all">{log.message}</span>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="border-t border-white/10 bg-zinc-900 px-4 py-2">
        <p className="text-xs text-zinc-400">
          {logs.length} lines • {isPaused ? "Paused" : "Live"}
          {!shouldAutoScrollRef.current && " • Auto-scroll disabled (scroll to bottom to enable)"}
        </p>
      </div>
    </div>
  );
}
