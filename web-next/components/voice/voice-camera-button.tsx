"use client";

import { Camera } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLanguage } from "@/lib/i18n";

type Props = Readonly<{
  className?: string;
  disabled: boolean;
  onBusy: (busy: boolean) => void;
  onCapture: (file: File) => void;
}>;

async function captureFrame(signal: AbortSignal): Promise<File> {
  const camera = navigator.mediaDevices;
  if (!camera?.getUserMedia) throw new Error("camera unavailable");
  const media = camera.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
  let stream: MediaStream | undefined;
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  let rejectAbort: (cause: unknown) => void = () => {};
  const aborted = new Promise<never>((_, reject) => { rejectAbort = reject; });
  const onAbort = () => rejectAbort(signal.reason);
  signal.addEventListener("abort", onAbort, { once: true });
  try {
    stream = await Promise.race([media, aborted]);
    video.srcObject = stream;
    await Promise.race([video.play(), aborted]);
    const width = video.videoWidth;
    const height = video.videoHeight;
    if (!width || !height) throw new Error("empty camera frame");
    const scale = Math.min(1, 1280 / Math.max(width, height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const context = canvas.getContext("2d");
    if (!context) throw new Error("camera canvas unavailable");
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const encoded = new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
    const blob = await Promise.race([encoded, aborted]);
    if (!blob?.size) throw new Error("camera encoding failed");
    return new File([blob], "camera-frame.jpg", { type: "image/jpeg" });
  } finally {
    signal.removeEventListener("abort", onAbort);
    video.srcObject = null;
    if (stream) {
      for (const track of stream.getTracks()) track.stop();
    } else {
      void media.then((late) => { for (const track of late.getTracks()) track.stop(); }, () => {});
    }
  }
}

/** Take exactly one still on request, then hand it to the existing image attachment flow. */
export function VoiceCameraButton({ className, disabled, onBusy, onCapture }: Props) {
  const { t } = useLanguage();
  const pending = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => () => {
    if (!pending.current) return;
    pending.current.abort();
    pending.current = null;
    onBusy(false);
  }, [onBusy]);

  useEffect(() => {
    if (disabled) pending.current?.abort();
  }, [disabled]);

  const takePicture = async () => {
    if (disabled || pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setFailed(false);
    setBusy(true);
    onBusy(true);
    try {
      const file = await captureFrame(AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]));
      if (!controller.signal.aborted) onCapture(file);
    } catch {
      if (!controller.signal.aborted) setFailed(true);
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        setBusy(false);
        onBusy(false);
      }
    }
  };

  return <>
    <button type="button" className={className} disabled={disabled || busy} onClick={() => void takePicture()}>
      <Camera size={15} aria-hidden />{t(busy ? "voice.multimodal.cameraPending" : "voice.multimodal.captureCamera")}
    </button>
    {failed && <p role="alert">{t("voice.multimodal.cameraFailed")}</p>}
  </>;
}
