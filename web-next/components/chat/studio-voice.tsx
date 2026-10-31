"use client";
import { Headphones, Mic, MicOff, Square, X } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import type { ChatMessage } from "@/components/cockpit/cockpit-chat-thread";
import { useStudioVoice } from "./use-studio-voice";
export function StudioVoice(props: Readonly<{ session: string; stopRevision?: number; mode: "dictation" | "conversation"; busy: boolean; messages: ChatMessage[];
  onDraft: (text: string) => void; onTurn: (text: string) => Promise<boolean>; onStop: () => Promise<void>; onClose: () => void }>) {
  const { t, language } = useLanguage();
  const voice = useStudioVoice({ ...props, language });
  const capturing = voice.status === "listening";
  const processing = ["permission", "transcribing", "generating", "speaking"].includes(voice.status);
  return <section className="studio-voice" aria-label={t(props.mode === "dictation" ? "chat2.dictate" : "chat2.voice")}>
    <header><h2>{t(props.mode === "dictation" ? "chat2.dictate" : "chat2.voice")}</h2><button type="button" className="studio-icon" aria-label={t("chat2.endVoice")} onClick={voice.end}><X size={17} /></button></header>
    <div className="studio-orb" data-listening={capturing}>{props.mode === "dictation" ? <Mic size={25} /> : <Headphones size={25} />}</div>
    <p role="status" aria-live="polite">{t("chat2." + voice.status)}</p><p>{t(props.mode === "dictation" ? "chat2.dictationHint" : "chat2.voiceHint")}</p>
    {voice.error && <p role="alert">{t("chat2." + voice.error)}</p>}
    <div className="studio-voice-controls">
      {capturing ? <button type="button" className="studio-button" onClick={() => { void voice.finish(); }}><Square size={15} />{t("chat2.finishTurn")}</button> : <button type="button" className="studio-button" disabled={processing || props.busy} onClick={() => { void voice.start(); }}><Mic size={15} />{t(voice.status === "muted" ? "chat2.unmute" : "chat2.listen")}</button>}
      <button type="button" className="studio-button" disabled={!capturing} onClick={voice.mute}><MicOff size={15} />{t("chat2.mute")}</button>
      <button type="button" className="studio-button" disabled={!["speaking", "generating"].includes(voice.status)} onClick={() => { void voice.stop(); }}><Square size={15} />{t("chat2.stop")}</button>
      <button type="button" className="studio-button" onClick={voice.end}>{t("chat2.endVoice")}</button>
    </div>
  </section>;
}
