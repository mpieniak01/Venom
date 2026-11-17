"use client";
import { useState } from "react";
import { useLanguage } from "@/lib/i18n";
import { nativeTextQuality } from "@/lib/native-text-chat";
import type { NativeTextChat } from "./use-native-text-chat";

export function NativeTextPicker({native, busy}: Readonly<{native: NativeTextChat; busy: boolean}>) {
  const {t} = useLanguage();
  const [candidate, setCandidate] = useState("");
  const current = native.state.selection;
  if (!native.adapters.length && !current && native.ready) return null;
  return <section className="studio-models" aria-label={t("chat2.nativeText.title")}>
    <div className="studio-model-line">
      <label>{t("chat2.nativeText.title")}<select aria-label={t("chat2.nativeText.title")} value={candidate}
        disabled={busy || native.busy || !native.ready} onChange={event => setCandidate(event.target.value)}>
        <option value="">{t("chat2.nativeText.choose")}</option>
        {native.adapters.map(item => <option key={item.adapter_id} value={item.adapter_id}>{item.label} · {t(nativeTextQuality(item))}</option>)}
      </select></label>
      <button type="button" className="studio-button" disabled={busy || native.busy || !native.ready || !candidate}
        onClick={() => { void native.change(candidate); }}>{t("chat2.nativeText.apply")}</button>
      <button type="button" className="studio-button" disabled={busy || native.busy || !native.ready || !current}
        onClick={() => { void native.change(); }}>{t("chat2.nativeText.rollback")}</button>
      <button type="button" className="studio-button" disabled={busy || native.busy} onClick={() => { void native.refresh(); }}>{t("chat2.nativeText.refresh")}</button>
    </div>
    <p className="studio-muted">{t("chat2.nativeText.scope")}</p>
    <output aria-live="polite">{native.busy ? t("chat2.nativeText.probing") : current
      ? current.adapter_id + " · " + current.weights_sha256 : t("chat2.nativeText.ordinary")}</output>
    {native.error && <p className="studio-error" role="alert">{t(native.error)}</p>}
  </section>;
}
