"use client";

import { Badge } from "@/components/ui/badge";
import { MarkdownPreview } from "@/components/ui/markdown";
import { statusTone } from "@/lib/status";

type ConversationBubbleProps = {
  role: "user" | "assistant";
  timestamp: string;
  text: string;
  status?: string | null;
  requestId?: string;
  isSelected?: boolean;
  onSelect?: () => void;
};

export function ConversationBubble({
  role,
  timestamp,
  text,
  status,
  requestId,
  isSelected,
  onSelect,
}: ConversationBubbleProps) {
  const isUser = role === "user";
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full max-w-2xl rounded-3xl border px-4 py-3 text-left text-sm shadow-lg transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500/50 ${
        isUser
          ? "ml-auto border-violet-500/40 bg-gradient-to-r from-violet-500/20 via-violet-500/10 to-transparent text-violet-50"
          : "border-white/10 bg-white/5 text-zinc-100"
      } ${isSelected ? "ring-2 ring-violet-400/60" : ""}`}
    >
      <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.3em] text-zinc-500">
        <span>{isUser ? "Operacja" : "Venom"}</span>
        <span>{new Date(timestamp).toLocaleTimeString()}</span>
      </div>
      <div className="mt-3 text-[15px] leading-relaxed text-white">
        <MarkdownPreview content={text} emptyState="Brak treści." />
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-zinc-400">
        {status && <Badge tone={statusTone(status)}>{status}</Badge>}
        {requestId && <span>#{requestId.slice(0, 6)}…</span>}
        <span className="ml-auto text-[10px] uppercase tracking-[0.35em] text-zinc-500">
          Szczegóły ↗
        </span>
      </div>
    </button>
  );
}
