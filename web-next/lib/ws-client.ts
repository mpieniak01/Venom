import { getWsBaseUrl } from "./env";

type MessageHandler = (payload: unknown) => void;
type StatusHandler = (connected: boolean) => void;

export class VenomWebSocket {
  private ws: WebSocket | null = null;
  private readonly path: string;
  private readonly onMessage: MessageHandler;
  private readonly onStatus?: StatusHandler;
  private reconnectAttempts = 0;
  private readonly maxAttempts = 5;
  private reconnectTimer?: ReturnType<typeof setTimeout>;

  constructor(path: string, onMessage: MessageHandler, onStatus?: StatusHandler) {
    this.path = path.startsWith("ws") ? path : `${getWsBaseUrl()}${path}`;
    this.onMessage = onMessage;
    this.onStatus = onStatus;
  }

  connect() {
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
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    this.ws?.close();
    this.ws = null;
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxAttempts) {
      return;
    }
    const delay = Math.min(30000, 1000 * 2 ** this.reconnectAttempts);
    this.reconnectAttempts += 1;
    this.reconnectTimer = setTimeout(() => {
      this.ws = null;
      this.connect();
    }, delay);
  }
}
