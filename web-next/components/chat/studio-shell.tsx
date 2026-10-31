"use client";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { ArrowLeft, Headphones, History, Mic, Moon, Paperclip, Plus, Send, Square, X } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import { useSession } from "@/lib/session";
import { apiFetch } from "@/lib/api-client";
import { cancelSimpleChatStream } from "@/hooks/use-api";
import { readChatSessions } from "@/lib/chat-sessions";
import { materialBlocked } from "@/lib/chat-materials";
import { useCockpitInteractiveState } from "@/components/cockpit/hooks/use-cockpit-interactive-state";
import { useCockpitLayout } from "@/components/cockpit/hooks/use-cockpit-layout";
import { useConversationController } from "./use-conversation-controller";
import { useConversationData } from "./use-conversation-data";
import { useSessionDraft } from "./use-session-draft";
import { useChatMaterials } from "./use-chat-materials";
import { StudioModelPicker } from "./studio-model-picker";
import { StudioMaterials } from "./studio-materials";
import { StudioThread } from "./studio-thread";
import "./studio.css";
const StudioVoice = dynamic(() => import("./studio-voice").then(module => module.StudioVoice), { ssr: false });
function materialSelection(value: string): string[] {
  try { const parsed: unknown = JSON.parse(value); return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string" && id.length < 128).slice(0, 4) : []; }
  catch { return []; }
}
const compactQuery = "(max-width: 800px)";
function subscribeCompact(onChange: () => void) {
  const query = window.matchMedia(compactQuery);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
function desktopSnapshot() { return !window.matchMedia(compactQuery).matches; }
function serverDesktopSnapshot() { return false; }
/** Preserve cancellation order and start the first operation synchronously. */
export function cancelStudioTasksInOrder(taskIds: readonly string[], cancelTask: (id: string) => Promise<void>): Promise<void> {
  const cancelNext = (index: number): Promise<void> => {
    if (index >= taskIds.length) return Promise.resolve();
    return cancelTask(taskIds[index]).then(() => cancelNext(index + 1));
  };
  return cancelNext(0);
}

export function StudioShell({ showLegacyLink = true }: Readonly<{ showLegacyLink?: boolean }>) {
  const { sessionId } = useSession();
  return <StudioConversation key={sessionId} showLegacyLink={showLegacyLink} />;
}
function StudioConversation({ showLegacyLink }: Readonly<{ showLegacyLink: boolean }>) {
  const { t, language, setLanguage } = useLanguage();
  const { theme, setTheme } = useTheme();
  const { sessionId, setSessionId } = useSession();
  const source = useConversationData();
  const interaction = useCockpitInteractiveState("direct");
  const layout = useCockpitLayout();
  const shellRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null!);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const materialButton = useRef<HTMLButtonElement>(null);
  const historyButton = useRef<HTMLButtonElement>(null);
  const [draft, setDraft] = useSessionDraft(sessionId);
  const [selectedJson, setSelectedJson] = useSessionDraft(sessionId ? "materials:" + sessionId : "");
  const selected = useMemo(() => materialSelection(selectedJson), [selectedJson]);
  const desktop = useSyncExternalStore(subscribeCompact, desktopSnapshot, serverDesktopSnapshot);
  const [materialsOverride, setMaterialsOverride] = useState<boolean | null>(null);
  const materialsOpen = materialsOverride ?? desktop;
  const materialsLayer = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (desktop || !materialsOpen) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    materialsLayer.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => { if (opener?.isConnected) opener.focus(); };
  }, [desktop, materialsOpen]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [stopRevision, setStopRevision] = useState(0);
  const [voice, setVoice] = useState<"dictation" | "conversation" | null>(null);
  const conversation = useConversationController({ data: source.data, interactive: interaction, layout, chatScrollRef: scrollRef, materialIds: selected });
  const { state, setters } = interaction;
  const materials = useChatMaterials(sessionId, state.selectedLlmModel, state.selectedLlmServer,
    source.data.activeServerInfo?.active_server ?? "", source.data.activeServerInfo?.config_hash ?? "", materialsOpen || selected.length > 0);
  const attached = materials.items.filter(item => selected.includes(item.id));
  const missing = selected.length > attached.length;
  const blocked = missing || materialBlocked(attached, materials.capabilities, state.chatMode === "direct");
  const active = state.sending || conversation.historyMessages.some(message => message.pending || ["PENDING", "PROCESSING"].includes(message.status ?? ""));
  const sendLock = useRef(false);
  const pendingStop = useRef(false);
  const stoppedTasks = useRef(new Set<string>());
  const activeTaskIds = conversation.historyMessages.filter(message => message.role === "assistant" && (message.pending || ["PENDING", "PROCESSING"].includes(message.status ?? "")))
    .map(message => message.requestId).filter((id): id is string => !!id && !id.startsWith("opt-"));
  const taskKey = JSON.stringify(activeTaskIds.filter(id => conversation.normalRequestIds.includes(id)));
  const cancelKnownTasks = useCallback(() => cancelStudioTasksInOrder(JSON.parse(taskKey) as string[], async id => {
    if (stoppedTasks.current.has(id)) return;
    stoppedTasks.current.add(id);
    try {
      await apiFetch("/api/v1/chat/tasks/" + encodeURIComponent(id) + "/cancel", { method: "POST", body: JSON.stringify({ session_id: sessionId }) });
    } catch {
      stoppedTasks.current.delete(id);
      setters.setMessage(t("chat2.error"));
    }
  }), [sessionId, taskKey, setters, t]);
  const stop = useCallback(async () => {
    if (!pendingStop.current) setStopRevision(value => value + 1);
    pendingStop.current = true; cancelSimpleChatStream();
    setters.setSending(false);
    await cancelKnownTasks();
  }, [setters, cancelKnownTasks]);
  useEffect(() => { if (pendingStop.current && activeTaskIds.length) void cancelKnownTasks(); }, [taskKey, cancelKnownTasks, activeTaskIds.length]);
  useEffect(() => { if (!active) sendLock.current = false; }, [active]);
  const send = useCallback(async (text: string) => {
    if (sendLock.current || active || blocked || materials.uploading || !text.trim()) return false;
    sendLock.current = true; pendingStop.current = false; stoppedTasks.current.clear();
    try {
      const accepted = await conversation.chatUi.handleSend(text);
      if (accepted) { setDraft(current => current === text ? "" : current); setSelectedJson(current => current === selectedJson ? "[]" : current); textarea.current?.focus(); }
      else sendLock.current = false;
      return accepted;
    } catch { sendLock.current = false; setters.setMessage(t("chat2.error")); return false; }
  }, [active, blocked, materials.uploading, conversation.chatUi, setDraft, setSelectedJson, selectedJson, setters, t]);
  const toggleMaterial = (id: string) => setSelectedJson(JSON.stringify(selected.includes(id) ? selected.filter(item => item !== id) : [...selected, id]));
  const upload = async (files: File[]) => {
    const created = await materials.upload(files);
    if (created.length) setSelectedJson(previous => JSON.stringify([...new Set([...materialSelection(previous), ...created.map(item => item.id)])].slice(0, 4)));
  };
  const sessions = historyOpen ? readChatSessions() : [];
  const chooseSession = (id: string) => { if (!active) { setSessionId(id); setHistoryOpen(false); setVoice(null); textarea.current?.focus(); } };
  useEffect(() => {
    const shell = shellRef.current;
    if (!shell) return;
    const closeContext = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (historyOpen) {
        setHistoryOpen(false);
        historyButton.current?.focus();
      } else if (materialsOpen) {
        setMaterialsOverride(false);
        materialButton.current?.focus();
      }
    };
    shell.addEventListener("keydown", closeContext);
    return () => shell.removeEventListener("keydown", closeContext);
  }, [historyOpen, materialsOpen]);
  return <div ref={shellRef} className="chat2" data-testid="chat2-shell">
    <nav className="studio-rail" aria-label={t("chat2.title")}><span className="studio-brand" aria-hidden="true">V</span>
      <button ref={historyButton} type="button" className="studio-icon" aria-label={t("chat2.history")} aria-expanded={historyOpen} aria-controls="studio-history" onClick={() => {
        if (!desktop) { setMaterialsOverride(false); }
        setHistoryOpen(!historyOpen);
      }}><History size={21} /></button>
      <button type="button" className="studio-icon" aria-label={t("chat2.newChat")} disabled={active || !sessionId} onClick={() => { conversation.sessionActions.handleSessionReset(); setters.setMessage(null); setVoice(null); }}><Plus size={21} /></button>
      {showLegacyLink && <Link className="studio-icon studio-back" href="/chat" prefetch={false} aria-label={t("chat2.back")}><ArrowLeft size={21} /></Link>}
      <button type="button" className={"studio-icon" + (showLegacyLink ? "" : " studio-back")} aria-label={t("chat2.theme")} onClick={() => setTheme(theme === "venom-light" ? "venom-dark" : "venom-light")}><Moon size={20} /></button>
    </nav>
    {historyOpen && <aside className="studio-history" id="studio-history" aria-label={t("chat2.history")}><header><h2>{t("chat2.history")}</h2><button type="button" className="studio-icon" aria-label={t("chat2.close")} onClick={() => { setHistoryOpen(false); historyButton.current?.focus(); }}><X size={16} /></button></header>
      {sessions.map(item => <button type="button" key={item.id} className="studio-session" disabled={active} aria-current={item.id === sessionId ? "true" : undefined} onClick={() => chooseSession(item.id)}>{item.title || t("chat2.newChat")}<small>{item.updatedAt.slice(0, 10)}</small></button>)}
    </aside>}
    <main className="studio-main"><header className="studio-top"><div><p className="studio-eyebrow">STUDIO</p><h1>{t("chat2.title")}</h1><p>{t("chat2.subtitle")}</p></div>
      <div className="studio-top-actions"><label className="studio-language"><span className="sr-only">{t("chat2.language")}</span><select aria-label={t("chat2.language")} value={language} onChange={event => setLanguage(event.target.value as "pl" | "en" | "de")}><option value="pl">PL</option><option value="en">EN</option><option value="de">DE</option></select></label>
        <button ref={materialButton} type="button" className="studio-button" aria-expanded={materialsOpen} aria-controls="studio-materials" onClick={() => { setHistoryOpen(false); setMaterialsOverride(!materialsOpen); }}><Paperclip size={16} />{t("chat2.materials")}</button></div>
    </header>
    <StudioModelPicker catalog={source.data.unifiedModelCatalog} interaction={interaction} session={sessionId} activeModel={source.data.activeServerInfo?.active_model} onApply={conversation.handleActivateModel} busy={active} />
    {source.error && <div className="studio-error" role="alert">{t("chat2.offline")}<button type="button" className="studio-button" onClick={() => { void source.refresh(); }}>{t("chat2.retry")}</button></div>}
    <div className={"studio-workspace" + (materialsOpen ? " studio-with-materials" : "")}><div className="studio-conversation">
      <StudioThread key={sessionId} messages={conversation.historyMessages} details={interaction.optimistic.simpleRequestDetails} scrollRef={scrollRef} onScroll={conversation.chatUi.handleChatScroll} loading={source.loading || !sessionId} onError={setters.setMessage} />
      {voice && <StudioVoice key={sessionId + voice} session={sessionId} mode={voice} stopRevision={stopRevision} busy={active} messages={conversation.historyMessages}
        onDraft={text => setDraft(previous => previous ? previous + " " + text : text)} onTurn={send} onStop={stop} onClose={() => setVoice(null)} />}
      <form className="studio-compose-wrap" onSubmit={event => { event.preventDefault(); void send(draft); }}>
        {!!selected.length && <div className="studio-attachments" aria-label={t("chat2.selectedMaterials")}>{selected.map(id => <button type="button" key={id} className="studio-chip" aria-label={t("chat2.detach") + ": " + (materials.items.find(item => item.id === id)?.name || id)} onClick={() => toggleMaterial(id)}><Paperclip size={13} />{materials.items.find(item => item.id === id)?.name || t("chat2.stale")}<X size={12} /></button>)}</div>}
        <div className="studio-compose"><textarea ref={textarea} aria-label={t("chat2.placeholder")} placeholder={t("chat2.placeholder")} value={draft} maxLength={50000} rows={3} disabled={!sessionId}
          onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(draft); } }} />
          <div className="studio-compose-actions"><div><button type="button" className="studio-icon" aria-label={t("chat2.chooseFiles")} onClick={() => { setHistoryOpen(false); setMaterialsOverride(true); }}><Paperclip size={19} /></button>
            <button type="button" className="studio-button studio-quiet" onClick={() => setVoice(voice === "dictation" ? null : "dictation")} disabled={active}><Mic size={17} />{t("chat2.dictate")}</button>
            <button type="button" className="studio-button studio-quiet" onClick={() => setVoice(voice === "conversation" ? null : "conversation")} disabled={active}><Headphones size={17} />{t("chat2.voice")}</button></div>
            {active ? <button type="button" className="studio-button studio-stop" onClick={() => { void stop(); }}><Square size={15} />{t("chat2.stop")}</button> : <button type="submit" className="studio-button studio-send" disabled={!sessionId || source.loading || !state.selectedLlmModel || !draft.trim() || blocked || materials.uploading}><Send size={17} />{t("chat2.send")}</button>}
          </div>
        </div>
        {blocked && !!selected.length && <p className="studio-error" role="alert">{t(missing ? "chat2.stale" : "chat2.incompatible")}</p>}
        {state.message && <p className="studio-error" role="alert">{state.message}</p>}
        <div className="studio-compose-footer"><span>{t("chat2.sendHint")}</span><output aria-live="polite">{t(active ? "chat2.generating" : "chat2.ready")}</output></div>
      </form>
    </div>
    {materialsOpen && <div ref={materialsLayer} className="studio-materials-layer" role={desktop ? undefined : "dialog"} aria-modal={desktop ? undefined : true} aria-label={desktop ? undefined : t("chat2.materials")}
      onClick={event => { if (!desktop && event.target === event.currentTarget) { setMaterialsOverride(false); materialButton.current?.focus(); } }}
      onKeyDown={event => {
        if (desktop || event.key !== "Tab") return;
        const controls = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),a[href],[tabindex="0"]')].filter(node => !node.hidden && node.getClientRects().length > 0);
        const first = controls[0], last = controls.at(-1);
        if (!first || !last) { event.preventDefault(); return; }
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }}>
      <StudioMaterials key={sessionId} materialState={materials} selected={selected} onToggle={toggleMaterial} onUpload={upload} onClose={() => { setMaterialsOverride(false); materialButton.current?.focus(); }} />
    </div>}
    </div></main>
  </div>;
}
