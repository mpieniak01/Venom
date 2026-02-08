"use client";

import { Badge } from "@/components/ui/badge";
import { MarkdownPreview } from "@/components/ui/markdown";
import { isComputationContent } from "@/lib/markdown-format";
import { statusTone } from "@/lib/status";
import { TYPING_EFFECT } from "@/lib/ui-config";
import { useTranslation } from "@/lib/i18n";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

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
  sourceLabel?: string | null;
  contextUsed?: {
    lessons?: string[];
    memory_entries?: string[];
  } | null;
};

function resolveStatusLabel(
  status: string | null | undefined,
  t: ReturnType<typeof useTranslation>,
) {
  if (!status) return null;
  const normalized = status.toUpperCase();
  switch (normalized) {
    case "COMPLETED":
      return t("cockpit.chatStatus.completed");
    case "FAILED":
      return t("cockpit.chatStatus.failed");
    case "LOST":
      return t("cockpit.chatStatus.lost");
    case "PENDING":
      return t("cockpit.chatStatus.pending");
    case "PROCESSING":
      return t("cockpit.chatStatus.processing");
    default:
      break;
  }
  const localizedMap: Record<string, string> = {
    "W TOKU": t("cockpit.chatStatus.inProgress"),
    "WYSŁANO": t("cockpit.chatStatus.sent"),
    "WYSYŁANO": t("cockpit.chatStatus.sent"),
    "W KOLEJCE": t("cockpit.chatStatus.queued"),
    "BŁĄD STRUMIENIA": t("cockpit.chatStatus.streamError"),
  };
  return localizedMap[normalized] ?? status;
}

function resolveModeLabelText(
  modeLabel: string | null | undefined,
  t: ReturnType<typeof useTranslation>,
) {
  if (!modeLabel) return null;
  const normalized = modeLabel.toLowerCase();
  if (normalized === "direct") return t("cockpit.chatMode.direct");
  if (normalized === "normal") return t("cockpit.chatMode.normal");
  if (normalized === "complex") return t("cockpit.chatMode.complex");
  return modeLabel;
}

function resolveTimeLabel(timestamp: string) {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date);
}

function renderMessageBody(input: {
  showTyping: boolean;
  visibleText: string;
  text: string;
  isUser: boolean;
  t: ReturnType<typeof useTranslation>;
}): ReactNode {
  const { showTyping, visibleText, text, isUser, t } = input;
  if (showTyping) {
    return (
      <p className="whitespace-pre-wrap text-sm text-white/90">
        {visibleText}
        <span className="typing-dots" aria-hidden="true">
          <span className="typing-dot" />
          <span className="typing-dot" />
          <span className="typing-dot" />
        </span>
      </p>
    );
  }
  if (text.trim().length > 0) {
    return (
      <MarkdownPreview content={text} emptyState={t("cockpit.chatLabels.emptyContent")} mode="final" />
    );
  }
  return (
    <p className="text-sm text-zinc-400">{isUser ? "…" : t("cockpit.chatLabels.generating")}</p>
  );
}

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
  sourceLabel,
  contextUsed,
}: ConversationBubbleProps) {
  const t = useTranslation();
  const isUser = role === "user";
  const terminalStatuses = ["COMPLETED", "FAILED", "LOST"];
  const isTerminal =
    typeof status === "string" && terminalStatuses.includes(status);
  const showTyping = !isUser && (pending || (status && !isTerminal));
  const showComputationLabel =
    !isUser && !showTyping && isComputationContent(text);
  const disabled = pending || !onSelect;
  const typingText =
    text.trim().length > 0 ? text : t("cockpit.chatLabels.generating");
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
    typingTimerRef.current = globalThis.setInterval(() => {
      setVisibleText((prev) => {
        if (prev.length >= typingText.length) return prev;
        const remaining = typingText.length - prev.length;
        const step = Math.max(
          1,
          Math.min(Math.ceil(typingText.length / TYPING_EFFECT.MAX_STEPS), remaining),
        );
        const next = typingText.slice(0, Math.min(prev.length + step, typingText.length));
        return next === prev ? prev : next;
      });
    }, TYPING_EFFECT.INTERVAL_MS);
    return () => {
      if (typingTimerRef.current) {
        globalThis.clearInterval(typingTimerRef.current);
        typingTimerRef.current = null;
      }
    };
  }, [isUser, showTyping, typingText]);
  const statusLabel = resolveStatusLabel(status, t);
  const modeLabelText = resolveModeLabelText(modeLabel, t);
  const footerClickable = !disabled && !pending && !isUser;
  const timeLabel = resolveTimeLabel(timestamp);
  const messageBody = renderMessageBody({
    showTyping,
    visibleText,
    text,
    isUser,
    t,
  });

  return (
    <div
      data-testid={isUser ? "conversation-bubble-user" : "conversation-bubble-assistant"}
      className={`w-full rounded-3xl border px-4 py-3 text-left text-sm shadow-lg transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500/50 ${isUser
        ? "ml-auto border-violet-500/40 bg-gradient-to-r from-violet-500/20 via-violet-500/10 to-transparent text-violet-50"
        : "border-white/10 bg-white/5 text-zinc-100"
        } ${isSelected ? "ring-2 ring-violet-400/60" : ""} ${pending ? "cursor-wait opacity-95" : ""}`}
    >
      <div className="flex items-center justify-between text-caption">
        <span>{isUser ? t("cockpit.chatLabels.user") : "Venom"}</span>
        <span>{timeLabel}</span>
      </div>
      <div className="mt-3 text-[15px] leading-relaxed text-white">
        {showComputationLabel && (
          <p className="mb-2 text-xs uppercase tracking-[0.35em] text-emerald-200/80">
            {t("cockpit.chatLabels.computationResult")}
          </p>
        )}
        {messageBody}
      </div>
      {(footerActions || footerExtra || forcedLabel || (!isUser && (pending || status || requestId))) && (
        <div
          className="mt-4 border-t border-white/10 pt-3"
        >
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
            {footerActions && (
              <span className="flex items-center gap-2">{footerActions}</span>
            )}
            {forcedLabel && <Badge tone="neutral">{forcedLabel}</Badge>}
            {sourceLabel && <Badge tone="neutral">{sourceLabel}</Badge>}
            {pending && role === "assistant" && (
              <span className="text-amber-300">{t("cockpit.chatStatus.inProgress")}</span>
            )}
            {!isUser && status && (
              <Badge tone={statusTone(status)}>{statusLabel ?? status}</Badge>
            )}
            {!isUser && status && modeLabelText && (
              <Badge tone="neutral">{modeLabelText}</Badge>
            )}
            {contextUsed?.lessons && contextUsed.lessons.length > 0 && (
              <Badge tone="neutral" title={t("cockpit.chatLabels.lessonsUsed")}>
                🎓 {contextUsed.lessons.length}
              </Badge>
            )}
            {contextUsed?.memory_entries && contextUsed.memory_entries.length > 0 && (
              <Badge tone="neutral" title={t("cockpit.chatLabels.memoryUsed")}>
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
                  {t("cockpit.chatLabels.detailsLink")}
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
