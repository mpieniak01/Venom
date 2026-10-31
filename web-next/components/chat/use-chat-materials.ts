"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { listChatMaterials, readMaterialCapabilities, removeChatMaterial, uploadChatMaterial, materialMime,
  type ChatMaterial, type MaterialCapabilities } from "@/lib/chat-materials";

type MaterialScope = {
  session: string; epoch: number; active: boolean; revision: number; listSequence: number; appliedList: number;
  changes: Map<string, { revision: number; item: ChatMaterial | null }>;
  requests: Set<AbortController>; uploads: Set<AbortController>;
};
function current(scope: MaterialScope, epoch: number, session: string) {
  return scope.active && scope.epoch === epoch && scope.session === session;
}
export function useChatMaterials(session: string, model: string, runtime: string, activeRuntime: string, identity: string, enabled: boolean) {
  const [snapshot, setSnapshot] = useState<{ session: string; items: ChatMaterial[] }>({ session: "", items: [] });
  const [capability, setCapability] = useState<{ key: string; data: MaterialCapabilities } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(false);
  const scopeRef = useRef<MaterialScope>({ session: "", epoch: 0, active: false, revision: 0, listSequence: 0, appliedList: 0,
    changes: new Map(), requests: new Set(), uploads: new Set() });
  const capabilityKey = JSON.stringify([model, runtime, activeRuntime, identity]);
  useEffect(() => {
    const scope = scopeRef.current;
    scope.session = session; scope.epoch++; scope.active = true; scope.revision = 0;
    scope.listSequence = 0; scope.appliedList = 0; scope.changes.clear();
    setError(null); setUploading(false); setLoading(false); setCapability(null);
    return () => {
      scope.active = false; scope.epoch++;
      scope.requests.forEach(request => request.abort()); scope.requests.clear(); scope.uploads.clear();
    };
  }, [session]);
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const scope = scopeRef.current;
    if (!session || !scope.active || scope.session !== session || signal?.aborted) return;
    const epoch = scope.epoch, revision = scope.revision, sequence = ++scope.listSequence;
    const request = new AbortController(); scope.requests.add(request);
    const abort = () => request.abort(); signal?.addEventListener("abort", abort, { once: true });
    setLoading(true);
    try {
      const result = await listChatMaterials(session, request.signal);
      if (request.signal.aborted || !current(scope, epoch, session) || sequence < scope.appliedList) return;
      const items = new Map(result.materials.filter(item => item.session_id === session).map(item => [item.id, item]));
      // A list is a snapshot at request start. Preserve writes accepted while
      // that request was in flight, including removal tombstones.
      scope.changes.forEach((change, id) => {
        if (change.revision > revision) {
          if (change.item) items.set(id, change.item); else items.delete(id);
        }
      });
      scope.appliedList = sequence;
      scope.changes.forEach((change, id) => { if (change.revision <= revision) scope.changes.delete(id); });
      setSnapshot({ session, items: [...items.values()] });
    } catch {
      if (!request.signal.aborted && current(scope, epoch, session) && sequence === scope.listSequence && revision === scope.revision) setError("error");
    } finally {
      signal?.removeEventListener("abort", abort); scope.requests.delete(request);
      if (current(scope, epoch, session) && sequence === scope.listSequence) setLoading(false);
    }
  }, [session]);
  useEffect(() => {
    if (!enabled || !session) return;
    const request = new AbortController(); void refresh(request.signal);
    return () => request.abort();
  }, [enabled, session, refresh]);
  useEffect(() => {
    if (!model || !runtime) return;
    const scope = scopeRef.current, epoch = scope.epoch;
    const request = new AbortController(); scope.requests.add(request);
    void readMaterialCapabilities(model, request.signal).then(data => {
      if (!request.signal.aborted && current(scope, epoch, session)) setCapability({ key: capabilityKey,
        data: { ...data, image: data.image && runtime === activeRuntime } });
    }).catch(() => { /* unknown remains unavailable; no optimistic capability */ })
      .finally(() => scope.requests.delete(request));
    return () => request.abort();
  }, [model, runtime, activeRuntime, capabilityKey, session]);
  const cancelUpload = useCallback(() => {
    const scope = scopeRef.current;
    scope.uploads.forEach(request => request.abort()); scope.uploads.clear(); setUploading(false);
  }, []);
  const upload = useCallback(async (files: File[]) => {
    const scope = scopeRef.current;
    if (!session || !files.length || !scope.active || scope.session !== session) return [];
    const epoch = scope.epoch;
    const request = new AbortController(); scope.requests.add(request); scope.uploads.add(request);
    setUploading(true); setError(null);
    const created: ChatMaterial[] = [];
    try {
      for (const file of files) {
        if (file.size > 8 * 1024 * 1024) throw new Error("fileTooLarge");
        if (!["text/plain", "text/markdown", "text/csv", "application/json", "image/png", "image/jpeg", "image/webp"].includes(materialMime(file))) throw new Error("fileUnsupported");
        const material = await uploadChatMaterial(session, file, request.signal);
        if (request.signal.aborted || !current(scope, epoch, session)) return [];
        if (material.session_id !== session) throw new Error("material_session_mismatch");
        created.push(material); scope.changes.set(material.id, { revision: ++scope.revision, item: material });
        setSnapshot(previous => ({ session, items: [...(previous.session === session ? previous.items : []).filter(item => item.id !== material.id), material] }));
      }
      return created;
    } catch (cause) {
      if (!request.signal.aborted && current(scope, epoch, session)) setError(cause instanceof Error && ["fileTooLarge", "fileUnsupported"].includes(cause.message) ? cause.message : "error");
      return !request.signal.aborted && current(scope, epoch, session) ? created : [];
    } finally {
      scope.requests.delete(request); scope.uploads.delete(request);
      if (current(scope, epoch, session)) setUploading(scope.uploads.size > 0);
    }
  }, [session]);
  const remove = useCallback(async (id: string) => {
    const scope = scopeRef.current, epoch = scope.epoch;
    if (!session || !scope.active || scope.session !== session) return false;
    const request = new AbortController(); scope.requests.add(request); setError(null);
    try {
      await removeChatMaterial(session, id, request.signal);
      if (request.signal.aborted || !current(scope, epoch, session)) return false;
      scope.changes.set(id, { revision: ++scope.revision, item: null });
      setSnapshot(previous => ({ session, items: previous.session === session ? previous.items.filter(item => item.id !== id) : [] }));
      return true;
    } catch { if (!request.signal.aborted && current(scope, epoch, session)) setError("error"); return false; }
    finally { scope.requests.delete(request); }
  }, [session]);
  return { items: snapshot.session === session ? snapshot.items : [], capabilities: capability?.key === capabilityKey ? capability.data : null,
    error, uploading, loading, upload, remove, refresh, cancelUpload };
}
