"use client";

import { Badge } from "@/components/ui/badge";
import { MarkdownPreview } from "@/components/ui/markdown";
import { isComputationContent } from "@/lib/markdown-format";
import { statusTone } from "@/lib/status";
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
  forcedLabel?: string | null;
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
  forcedLabel,
}: ConversationBubbleProps) {
  const isUser = role === "user";
  const terminalStatuses = ["COMPLETED", "FAILED", "LOST"];
  const isTerminal =
    typeof status === "string" && terminalStatuses.includes(status);
  const showTyping = !isUser && (pending || (status && !isTerminal));
  const showComputationLabel =
    !isUser && !showTyping && isComputationContent(text);
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
      <div className="flex items-center justify-between text-caption">
        <span>{isUser ? "Operacja" : "Venom"}</span>
        <span>{new Date(timestamp).toLocaleTimeString()}</span>
      </div>
      <div className="mt-3 text-[15px] leading-relaxed text-white">
        {showComputationLabel && (
          <p className="mb-2 text-xs uppercase tracking-[0.35em] text-emerald-200/80">
            Wynik obliczeń
          </p>
        )}
        {showTyping ? (
          <p className="whitespace-pre-wrap text-sm text-white/90">
            {text}
            <span className="typing-dots" aria-hidden="true">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </span>
          </p>
        ) : (
          <MarkdownPreview content={text} emptyState="Brak treści." mode="final" />
        )}
      </div>
      {(footerActions || footerExtra || forcedLabel || (!isUser && (pending || status || requestId))) && (
        <div className="mt-4 border-t border-white/10 pt-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
          {footerActions && (
            <span className="flex items-center gap-2">{footerActions}</span>
          )}
          {forcedLabel && <Badge tone="neutral">{forcedLabel}</Badge>}
          {pending && role === "assistant" && (
            <span className="text-amber-300">W toku</span>
          )}
          {!isUser && status && <Badge tone={statusTone(status)}>{status}</Badge>}
          {requestId && <span>#{requestId.slice(0, 6)}…</span>}
          {!pending && !isUser && (
            <span className="ml-auto text-caption">
              Szczegóły ↗
            </span>
          )}
        </div>
          {footerExtra && <div className="mt-2">{footerExtra}</div>}
        </div>
      )}
    </div>
  );
}
