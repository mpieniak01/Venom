"use client";
import { memo, useState } from "react";
import { Copy, Check } from "lucide-react";
import { ConversationBubble } from "@/components/cockpit/conversation-bubble";
import { OpenRouterCost } from "@/components/cockpit/openrouter-cost";
import { useLanguage } from "@/lib/i18n";
import type { ChatMessage } from "@/components/cockpit/cockpit-chat-thread";
import type { HistoryRequestDetail } from "@/lib/types";
const Message = memo(function StudioMessage({ message, detail, onError }: Readonly<{
  message: ChatMessage; detail?: HistoryRequestDetail; onError: (message: string) => void;
}>) {
  const { t } = useLanguage(); const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      if (!navigator.clipboard?.writeText) { throw new Error("clipboard_unavailable"); }
      await navigator.clipboard.writeText(message.text);
      setCopied(true);
    }
    catch { onError(t("chat2.copyFailed")); }
  };
  return <article className={"studio-message studio-message-" + message.role} data-testid={"chat2-message-" + message.role}>
    <ConversationBubble {...message} requestId={message.requestId ?? undefined} text={message.text}
      footerActions={<button type="button" className="studio-copy" onClick={() => { void copy(); }}>{copied ? <Check size={14} /> : <Copy size={14} />}{t(copied ? "chat2.copied" : "chat2.copy")}</button>} />
    {!!message.materialIds?.length && <p className="studio-muted">{t("chat2.materials")}: {message.materialIds.length}</p>}
    {message.role === "assistant" && detail?.openrouter_cost && <details className="studio-turn-cost"><summary>{t("chat2.costs")}</summary><OpenRouterCost cost={detail.openrouter_cost} t={t} /></details>}
  </article>;
}, (previous, next) => previous.onError === next.onError && previous.detail === next.detail &&
  previous.message.text === next.message.text && previous.message.status === next.message.status && previous.message.pending === next.message.pending &&
  previous.message.timestamp === next.message.timestamp && previous.message.requestId === next.message.requestId && previous.message.role === next.message.role &&
  previous.message.contextUsed === next.message.contextUsed && previous.message.policyBlocked === next.message.policyBlocked &&
  previous.message.reasonCode === next.message.reasonCode && previous.message.userMessage === next.message.userMessage &&
  previous.message.materialIds?.join("|") === next.message.materialIds?.join("|"));
export function StudioThread({ messages, details, scrollRef, onScroll, loading, onError }: Readonly<{
  messages: ChatMessage[]; details: Record<string, HistoryRequestDetail>; scrollRef: React.RefObject<HTMLDivElement>; onScroll: () => void; loading: boolean; onError: (message: string) => void;
}>) {
  const { t } = useLanguage(); const [visibleCount, setVisibleCount] = useState(60);
  const visible = messages.slice(-visibleCount);
  return <section className="studio-thread" ref={scrollRef} onScroll={onScroll} aria-label={t("chat2.session")} data-testid="chat2-thread">
    {loading && !messages.length && <output>{t("chat2.loading")}</output>}
    {!loading && !messages.length && <div className="studio-welcome"><span className="studio-welcome-mark">V</span><h2>{t("chat2.emptyTitle")}</h2><p>{t("chat2.emptyHint")}</p></div>}
    {messages.length > visibleCount && <button type="button" className="studio-button" onClick={() => setVisibleCount(value => value + 60)}>{t("chat2.earlier")}</button>}
    {visible.map(message => <Message key={message.bubbleId} message={message} detail={message.requestId ? details[message.requestId] : undefined} onError={onError} />)}
  </section>;
}
