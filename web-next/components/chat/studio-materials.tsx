"use client";
import Image from "next/image";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { FileText, ImageIcon, Paperclip, Trash2, X } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { getApiBaseUrl } from "@/lib/env";
import type { ChatMaterial } from "@/lib/chat-materials";
import type { useChatMaterials } from "./use-chat-materials";
type PreviewContent = { id: string; value: string; image: boolean };

/** Render one preview state without exposing stale content from another file. */
function renderPreview(preview: ChatMaterial, content: PreviewContent | null, failed: boolean, errorLabel: string, loadingLabel: string): ReactNode {
  if (failed) return <p role="alert">{errorLabel}</p>;
  if (content?.id !== preview.id) return <output>{loadingLabel}</output>;
  if (content.image) return <Image src={content.value} alt={preview.name} width={480} height={320} unoptimized />;
  return <pre>{content.value}</pre>;
}

export function StudioMaterials({ materialState, selected, onToggle, onUpload, onClose }: Readonly<{
  materialState: ReturnType<typeof useChatMaterials>; selected: string[]; onToggle: (id: string) => void;
  onUpload: (files: File[]) => Promise<void>; onClose: () => void;
}>) {
  const { t } = useLanguage();
  const input = useRef<HTMLInputElement>(null);
  const uploadFiles = useCallback((files: File[]) => { void onUpload(files); }, [onUpload]);
  const [preview, setPreview] = useState<ChatMaterial | null>(null);
  const [content, setContent] = useState<PreviewContent | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!preview) return;
    const request = new AbortController(); let url: string | null = null;
    const path = "/api/v1/chat/materials/" + encodeURIComponent(preview.id) + "/content?session_id=" + encodeURIComponent(preview.session_id);
    void fetch(getApiBaseUrl() + path, { signal: request.signal }).then(async response => {
      if (!response.ok) throw new Error("preview_unavailable");
      if (preview.kind === "image") {
        const blob = await response.blob(); if (request.signal.aborted) return;
        url = URL.createObjectURL(blob); setContent({ id: preview.id, value: url, image: true });
      } else {
        const text = await response.text(); if (!request.signal.aborted) setContent({ id: preview.id, value: text, image: false });
      }
    }).catch(() => { if (!request.signal.aborted) setFailed(true); });
    return () => { request.abort(); if (url) URL.revokeObjectURL(url); };
  }, [preview]);
  const openPreview = (item: ChatMaterial) => { setFailed(false); setPreview(item); };
  let imageStatus = "chat2.unknown";
  if (materialState.capabilities) {
    imageStatus = materialState.capabilities.image ? "chat2.ready" : "chat2.unsupported";
  }
  return <aside className="studio-materials" id="studio-materials" aria-label={t("chat2.materials")}
    onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); uploadFiles(Array.from(event.dataTransfer.files)); }}>
    <header><h2><Paperclip size={17} />{t("chat2.materials")}</h2><button className="studio-icon" type="button" onClick={onClose} aria-label={t("chat2.close")}><X size={18} /></button></header>
    <p className="studio-muted">{t("chat2.dropFiles")}</p>
    <button type="button" className="studio-button studio-upload" disabled={materialState.uploading} onClick={() => input.current?.click()}>{t("chat2.chooseFiles")}</button>
    <input ref={input} type="file" hidden multiple accept=".txt,.md,.csv,.json,.png,.jpg,.jpeg,.webp" onChange={event => { uploadFiles(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
    {materialState.uploading && <div><output className="block">{t("chat2.uploading")}</output><button type="button" className="studio-button" onClick={materialState.cancelUpload}>{t("chat2.cancelUpload")}</button></div>}
    {materialState.error && <p role="alert">{t("chat2." + materialState.error)}</p>}
    {materialState.loading && <output>{t("chat2.loading")}</output>}
    {!materialState.items.length && !materialState.loading && <p className="studio-empty-materials">{t("chat2.noMaterials")}</p>}
    <ul className="studio-file-list">{materialState.items.map(item => <li key={item.id}>
      <label><input type="checkbox" checked={selected.includes(item.id)} disabled={!selected.includes(item.id) && selected.length >= 4} onChange={() => { if (selected.includes(item.id) || selected.length < 4) onToggle(item.id); }} aria-label={t("chat2.attach") + ": " + item.name} />
        {item.kind === "image" ? <ImageIcon size={19} /> : <FileText size={19} />}<span>{item.name}<small>{(item.size_bytes / 1024).toFixed(1)} KiB · {item.mime_type}</small></span></label>
      <div className="studio-file-actions"><button type="button" className="studio-button" onClick={() => openPreview(item)}>{t("chat2.preview")}</button>
        <button type="button" className="studio-icon" aria-label={t("chat2.remove") + ": " + item.name} onClick={() => {
          void materialState.remove(item.id).then(removed => {
            if (!removed) return;
            if (selected.includes(item.id)) { onToggle(item.id); }
            if (preview?.id === item.id) { setPreview(null); }
          });
        }}><Trash2 size={15} /></button></div>
    </li>)}</ul>
    {preview && <section className="studio-preview" aria-label={t("chat2.preview")}><header><h3>{preview.name}</h3><button type="button" className="studio-icon" aria-label={t("chat2.close")} onClick={() => setPreview(null)}><X size={16} /></button></header>
      {renderPreview(preview, content, failed, t("chat2.error"), t("chat2.loading"))}
    </section>}
    <footer><h3>{t("chat2.capabilities")}</h3><p>{t("chat2.text")} · {t("chat2.documents")}</p>
      <p>{t("chat2.images")}: {t(imageStatus)}</p><p className="studio-muted">{t("chat2.mediaLimit")}</p></footer>
  </aside>;
}
