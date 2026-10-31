/* Bounded mono PCM capture. Loaded only after an explicit microphone action. */
class VenomChatCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(4096);
    this.offset = 0;
    this.port.onmessage = event => {
      if (event.data?.type === "flush") {
        this.emit();
        this.port.postMessage({ flushed: true });
      }
    };
  }
  emit() {
    if (!this.offset) return;
    const data = this.buffer.slice(0, this.offset).buffer;
    this.port.postMessage(data, [data]);
    this.offset = 0;
  }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (input) for (const sample of input) {
      this.buffer[this.offset++] = Number.isFinite(sample) ? sample : 0;
      if (this.offset === this.buffer.length) this.emit();
    }
    return true;
  }
}
registerProcessor("venom-chat2-capture", VenomChatCapture);
