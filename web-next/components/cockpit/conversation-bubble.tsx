"use client";

import { Badge } from "@/components/ui/badge";
import { MarkdownPreview } from "@/components/ui/markdown";
import { isComputationContent } from "@/lib/markdown-format";
import { statusTone } from "@/lib/status";
import { TYPING_EFFECT } from "@/lib/ui-config";
import { useEffect, useRef, useState } from "react";
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
  modeLabel?: string | null;
  contextUsed?: {
    lessons?: string[];
    memory_entries?: string[];
  } | null;
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
  modeLabel,
  contextUsed,
}: ConversationBubbleProps) {
  const isUser = role === "user";
  const terminalStatuses = ["COMPLETED", "FAILED", "LOST"];
  const isTerminal =
    typeof status === "string" && terminalStatuses.includes(status);
  const showTyping = !isUser && (pending || (status && !isTerminal));
  const showComputationLabel =
    !isUser && !showTyping && isComputationContent(text);
  const disabled = pending || !onSelect;
  const typingText = text.trim().length > 0 ? text : "Generuję odpowiedź";
  const [visibleText, setVisibleText] = useState(text);
  const typingTimerRef = useRef<number | null>(null);
  useEffect(() => {
    if (isUser) {
      setVisibleText(text);
      return;
    }
    if (!showTyping) {
      setVisibleText(text);
      return;
    }
    setVisibleText((prev) => {
      if (typingText.startsWith(prev)) return prev;
      return "";
    });
  }, [isUser, showTyping, text, typingText]);
  useEffect(() => {
    if (isUser || !showTyping) return undefined;
    if (visibleText.length >= typingText.length) return undefined;
    if (typingTimerRef.current) {
      window.clearTimeout(typingTimerRef.current);
    }
    const remaining = typingText.length - visibleText.length;
    const step = Math.max(1, Math.min(Math.ceil(typingText.length / TYPING_EFFECT.MAX_STEPS), remaining));
    typingTimerRef.current = window.setTimeout(() => {
      window.requestAnimationFrame(() => {
        setVisibleText(typingText.slice(0, Math.min(visibleText.length + step, typingText.length)));
      });
    }, TYPING_EFFECT.INTERVAL_MS);
    return () => {
      if (typingTimerRef.current) {
        window.clearTimeout(typingTimerRef.current);
      }
    };
  }, [isUser, showTyping, typingText, visibleText]);
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect?.();
    }
  };
  const footerClickable = !disabled && !pending && !isUser;
  return (
    <div
      data-testid={isUser ? "conversation-bubble-user" : "conversation-bubble-assistant"}
      className={`w-full rounded-3xl border px-4 py-3 text-left text-sm shadow-lg transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500/50 ${isUser
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
            {visibleText}
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
        <div
          role={footerClickable ? "button" : undefined}
          tabIndex={footerClickable ? 0 : undefined}
          aria-disabled={footerClickable ? false : undefined}
          onClick={footerClickable ? onSelect : undefined}
          onKeyDown={footerClickable ? handleKeyDown : undefined}
          className={`mt-4 border-t border-white/10 pt-3 ${footerClickable ? "cursor-pointer hover:text-white" : ""
            }`}
        >
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
            {footerActions && (
              <span className="flex items-center gap-2">{footerActions}</span>
            )}
            {forcedLabel && <Badge tone="neutral">{forcedLabel}</Badge>}
            {pending && role === "assistant" && (
              <span className="text-amber-300">W toku</span>
            )}
            {!isUser && status && <Badge tone={statusTone(status)}>{status}</Badge>}
            {!isUser && status && modeLabel && (
              <Badge tone="neutral">{modeLabel}</Badge>
            )}
            {contextUsed?.lessons && contextUsed.lessons.length > 0 && (
              <Badge tone="neutral" title="Użyto lekcji">
                🎓 {contextUsed.lessons.length}
              </Badge>
            )}
            {contextUsed?.memory_entries && contextUsed.memory_entries.length > 0 && (
              <Badge tone="neutral" title="Użyto pamięci długoterminowej">
                🧠 {contextUsed.memory_entries.length}
              </Badge>
            )}
            {requestId && <span>#{requestId.slice(0, 6)}…</span>}
            {!pending && !isUser && footerClickable && (
              <span className="ml-auto text-caption">
                <button
                  type="button"
                  className="text-xs uppercase tracking-wide text-zinc-300 transition hover:text-white"
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelect?.();
                  }}
                >
                  Szczegóły ↗
                </button>
              </span>
            )}
          </div>
          {footerExtra && <div className="mt-2">{footerExtra}</div>}
        </div>
      )}
    </div>
  );
}
