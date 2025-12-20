"use client";

import { Badge } from "@/components/ui/badge";
import { MarkdownPreview } from "@/components/ui/markdown";
import { statusTone } from "@/lib/status";
import { Loader2 } from "lucide-react";
import type { KeyboardEvent, ReactNode } from "react";

type ConversationBubbleProps = {
  role: "user" | "assistant";
  timestamp: string;
  text: string;
  status?: string | null;
  requestId?: string;
  isSelected?: boolean;
  onSelect?: () => void;
  pending?: boolean;
  footerActions?: ReactNode;
  footerExtra?: ReactNode;
};

export function ConversationBubble({
  role,
  timestamp,
  text,
  status,
  requestId,
  isSelected,
  onSelect,
  pending,
  footerActions,
  footerExtra,
}: ConversationBubbleProps) {
  const isUser = role === "user";
  const disabled = pending || !onSelect;
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect?.();
    }
  };
  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      onClick={disabled ? undefined : onSelect}
      onKeyDown={handleKeyDown}
      aria-disabled={disabled}
      data-testid={isUser ? "conversation-bubble-user" : "conversation-bubble-assistant"}
      className={`w-full rounded-3xl border px-4 py-3 text-left text-sm shadow-lg transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500/50 ${
        isUser
          ? "ml-auto border-violet-500/40 bg-gradient-to-r from-violet-500/20 via-violet-500/10 to-transparent text-violet-50"
          : "border-white/10 bg-white/5 text-zinc-100"
      } ${isSelected ? "ring-2 ring-violet-400/60" : ""} ${pending ? "cursor-wait opacity-95" : ""}`}
    >
      <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.3em] text-zinc-500">
        <span>{isUser ? "Operacja" : "Venom"}</span>
        <span>{new Date(timestamp).toLocaleTimeString()}</span>
      </div>
      <div className="mt-3 text-[15px] leading-relaxed text-white">
        <MarkdownPreview content={text} emptyState="Brak treści." />
      </div>
      <div className="mt-4 border-t border-white/10 pt-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
          {footerActions && (
            <span className="flex items-center gap-2">{footerActions}</span>
          )}
          {pending && role === "assistant" && (
            <span className="flex items-center gap-1 text-amber-300">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              W toku
            </span>
          )}
          {status && <Badge tone={statusTone(status)}>{status}</Badge>}
          {requestId && <span>#{requestId.slice(0, 6)}…</span>}
          {!pending && (
            <span className="ml-auto text-[10px] uppercase tracking-[0.35em] text-zinc-500">
              Szczegóły ↗
            </span>
          )}
        </div>
        {footerExtra && <div className="mt-2">{footerExtra}</div>}
      </div>
    </div>
  );
}
