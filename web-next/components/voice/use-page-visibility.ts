"use client";

import { useEffect, useState } from "react";

function isDocumentVisible(): boolean {
  if (globalThis.document === undefined) return true;
  return globalThis.document.visibilityState !== "hidden";
}

export function usePageVisibility(): boolean {
  const [visible, setVisible] = useState<boolean>(isDocumentVisible);

  useEffect(() => {
    if (globalThis.document === undefined) return;
    const onVisibilityChange = () => {
      setVisible(isDocumentVisible());
    };
    globalThis.document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      globalThis.document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  return visible;
}
