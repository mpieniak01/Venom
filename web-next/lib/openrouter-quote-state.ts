import {useSyncExternalStore} from "react";
import type {OpenRouterQuote} from "./openrouter-chat";

type QuoteSnapshot = {model: string; session: string; quote: OpenRouterQuote};
let snapshot: QuoteSnapshot | null = null;
const subscribers = new Set<() => void>();
const subscribe = (listener: () => void) => {subscribers.add(listener); return () => {subscribers.delete(listener);};};
const serverSnapshot = () => null;

/** An informational last-send estimate; the backend remains the authority for spending. */
export function publishOpenRouterQuote(model: string, session: string, quote: OpenRouterQuote) {
  snapshot = {model, session, quote};
  for (const listener of subscribers) listener();
}

export function useOpenRouterLastQuote(model: string, session: string) {
  return useSyncExternalStore(subscribe,
    () => snapshot?.model === model && snapshot.session === session ? snapshot.quote : null,
    serverSnapshot);
}
