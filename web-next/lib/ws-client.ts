import { getWsBaseUrl } from "./env";

type MessageHandler = (payload: unknown) => void;
type StatusHandler = (connected: boolean) => void;

export class VenomWebSocket {
  private ws: WebSocket | null = null;
  private readonly path: string;
  private readonly onMessage: MessageHandler;
  private readonly onStatus?: StatusHandler;
  private reconnectAttempts = 0;
  private reconnectAllowed = true;
  private readonly maxAttempts = 5;
  private reconnectTimer?: ReturnType<typeof setTimeout>;

  constructor(path: string, onMessage: MessageHandler, onStatus?: StatusHandler) {
    this.path = path.startsWith("ws") ? path : `${getWsBaseUrl()}${path}`;
    this.onMessage = onMessage;
    this.onStatus = onStatus;
  }

  connect() {
    this.reconnectAllowed = true;
    if (this.ws) return;
    if (process.env.NEXT_PUBLIC_DISABLE_WS_EVENTS === "true") {
      this.onStatus?.(false);
      return;
    }

    this.ws = new WebSocket(this.path);
    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.onStatus?.(true);
    };

    this.ws.onclose = () => {
      this.onStatus?.(false);
      this.scheduleReconnect();
    };

    this.ws.onerror = () => {
      this.onStatus?.(false);
      this.ws?.close();
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.onMessage(data);
      } catch {
        this.onMessage(event.data);
      }
    };
  }

  disconnect() {
    this.reconnectAllowed = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.onmessage = null;
      this.ws.onopen = null;
      this.ws.onerror = null;
      this.ws.close();
    }
    this.ws = null;
    this.onStatus?.(false);
  }

  private scheduleReconnect() {
    if (!this.reconnectAllowed || this.reconnectAttempts >= this.maxAttempts) {
      return;
    }
    const delay = Math.min(30000, 1000 * 2 ** this.reconnectAttempts);
    this.reconnectAttempts += 1;
    this.reconnectTimer = setTimeout(() => {
      if (!this.reconnectAllowed) return;
      this.ws = null;
      this.connect();
    }, delay);
  }
}
