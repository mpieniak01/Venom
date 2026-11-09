"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const MAX_IMAGE_BYTES = 2 * 1024 * 1024;
export const VOICE_IMAGE_ACCEPT = "image/jpeg,image/png";

type VoiceImageSelection =
  | { status: "reading"; name: string }
  | { status: "ready"; name: string; base64: string }
  | { status: "invalid" };

/** Read one bounded JPEG or PNG at a time and discard callbacks from replaced selections. */
export function useVoiceImageSelection() {
  const [selection, setSelection] = useState<VoiceImageSelection | null>(null);
  const readerRef = useRef<FileReader | null>(null);

  const cancelRead = useCallback(() => {
    const reader = readerRef.current;
    readerRef.current = null;
    reader?.abort();
  }, []);

  useEffect(() => cancelRead, [cancelRead]);

  const clearImage = useCallback(() => {
    cancelRead();
    setSelection(null);
  }, [cancelRead]);

  /** Replace the current image, retaining its filename while the browser reads it. */
  const chooseImage = (file: File) => {
    cancelRead();
    if (
      !["image/jpeg", "image/png"].includes(file.type)
      || file.size === 0
      || file.size > MAX_IMAGE_BYTES
    ) {
      setSelection({ status: "invalid" });
      return;
    }
    const reader = new window.FileReader();
    readerRef.current = reader;
    setSelection({ status: "reading", name: file.name });
    /** Commit the read only if this reader still owns the selection. */
    const finishRead = (base64: string | undefined) => {
      if (readerRef.current !== reader) return;
      readerRef.current = null;
      setSelection(base64
        ? { status: "ready", name: file.name, base64 }
        : { status: "invalid" });
    };
    reader.onload = () => finishRead(typeof reader.result === "string" ? reader.result.split(",", 2)[1] : undefined);
    reader.onerror = () => finishRead(undefined);
    reader.readAsDataURL(file);
  };

  return { selection, chooseImage, clearImage };
}
