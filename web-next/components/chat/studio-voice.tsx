"use client";
import { useRef, useState } from "react";
import { Headphones, Mic, MicOff, Paperclip, Square, X } from "lucide-react";
import { VoicePipelinePicker } from "@/components/voice/voice-pipeline-picker";
import { useLanguage } from "@/lib/i18n";
import { useStudioVoice, type StudioVoiceOptions } from "./use-studio-voice";
export function StudioVoice(props: Readonly<Omit<StudioVoiceOptions, "language"> & { activeModel?: string | null; onModelApplied?: (model: string) => void }>) {
  const { t, language } = useLanguage();
  const [switching, setSwitching] = useState(false);
  const voice = useStudioVoice({ ...props, language, busy: props.busy || switching });
  const imagePicker = useRef<HTMLInputElement>(null);
  const capturing = voice.status === "listening";
  const processing = ["permission", "transcribing", "generating", "speaking"].includes(voice.status);
  return <section className="studio-voice" aria-label={t(props.mode === "dictation" ? "chat2.dictate" : "chat2.voice")}>
    <header><h2>{t(props.mode === "dictation" ? "chat2.dictate" : "chat2.voice")}</h2><button type="button" className="studio-icon" aria-label={t("chat2.endVoice")} onClick={voice.end}><X size={17} /></button></header>
    {props.mode === "conversation" && <VoicePipelinePicker surface="chat2" disabled={props.busy || capturing || processing}
      onApplied={props.onModelApplied} onSwitching={setSwitching} refreshKey={props.activeModel} />}
    <div className="studio-orb" data-listening={capturing}>{props.mode === "dictation" ? <Mic size={25} /> : <Headphones size={25} />}</div>
    <output className="block" aria-live="polite">{t("chat2." + voice.status)}</output><p>{t(props.mode === "dictation" ? "chat2.dictationHint" : "chat2.voiceHint")}</p>
    {voice.error && <p role="alert">{t("chat2." + voice.error)}</p>}
    {voice.sources.length > 0 && <p className="break-words" aria-live="polite">{t("chat2.voiceSources")}: {voice.sources.join(", ")}</p>}
    {props.mode === "conversation" && props.multimodalEnabled && <div className="studio-voice-controls">
      <input ref={imagePicker} type="file" accept="image/png,image/jpeg" hidden onChange={event => {
        const file = event.currentTarget.files?.item(0);
        event.currentTarget.value = "";
        if (file) voice.selectImage(file);
      }} />
      <button type="button" className="studio-button" disabled={processing || capturing || props.busy}
        onClick={() => imagePicker.current?.click()}><Paperclip size={15} />{t("chat2.attachVoiceImage")}</button>
      {voice.image && <button type="button" className="studio-chip" disabled={processing || capturing || props.busy}
        aria-label={t("chat2.detach") + ": " + voice.image.name} onClick={() => voice.selectImage(null)}>{voice.image.name}<X size={14} /></button>}
    </div>}
    <div className="studio-voice-controls">
      {capturing ? <button type="button" className="studio-button" onClick={() => { void voice.finish(); }}><Square size={15} />{t("chat2.finishTurn")}</button> : <button type="button" className="studio-button" disabled={processing || props.busy || switching} onClick={() => { void voice.start(); }}><Mic size={15} />{t(voice.status === "muted" ? "chat2.unmute" : "chat2.listen")}</button>}
      <button type="button" className="studio-button" disabled={!capturing} onClick={voice.mute}><MicOff size={15} />{t("chat2.mute")}</button>
      <button type="button" className="studio-button" disabled={!["speaking", "generating"].includes(voice.status)} onClick={() => { void voice.stop(); }}><Square size={15} />{t("chat2.stop")}</button>
      <button type="button" className="studio-button" onClick={voice.end}>{t("chat2.endVoice")}</button>
    </div>
  </section>;
}
