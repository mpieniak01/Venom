/**
 * Browser-only B07 acceptance against explicit fake API/audio adapters.
 * Use a dedicated browser context/profile and a UI built with CHAT2 enabled.
 * No real provider, microphone, audio device, model, robot or account is contacted.
 * Self-contained: the same default function can be embedded in Playwright CLI run-code.
 */
export default async function chat2Acceptance(page, baseURL) {
  const assertions = [];
  const failures = [];
  const pageErrors = [];
  const hydrationErrors = [];
  const check = (condition, name) => {
    if (!condition) { failures.push(name); throw new Error("Chat2 acceptance failed: " + name); }
    assertions.push(name);
  };
  const errorListener = error => pageErrors.push(String(error?.message ?? error).slice(0, 200));
  const consoleListener = message => {
    if (message.type() === "error" && /hydration|did not match|does not match|server rendered html/i.test(message.text())) hydrationErrors.push(message.text().slice(0, 200));
  };
  page.on("pageerror", errorListener);
  page.on("console", consoleListener);
  await page.addInitScript(() => {
    const key = "venom-chat2-b07-fake-state";
    const nativeFetch = globalThis.fetch.bind(globalThis);
    const NativeWebSocket = globalThis.WebSocket;
    const nativeCreateURL = URL.createObjectURL.bind(URL);
    const nativeRevokeURL = URL.revokeObjectURL.bind(URL);
    const load = () => { try { return JSON.parse(localStorage.getItem(key) ?? "null"); } catch { return null; } };
    let state = load();
    const existingSession = localStorage.getItem("venom-session-id");
    const unsafe = state?.unsafeExistingSession === true || (!state && !!existingSession && !existingSession.startsWith("chat2-b07-"));
    state ??= {
      version: 1, calls: [], accepted: 0, simplePosts: 0, rejected: 0, streamAborts: 0,
      sttCalls: 0, ttsCalls: 0, micRequests: 0, tracksCreated: 0, tracksStopped: 0,
      contextsCreated: 0, contextsClosed: 0, playbackStarted: 0, playbackActive: 0,
      objectURLsCreated: 0, objectURLsRevoked: 0, socketAttempts: 0, hmrSockets: 0, externalAttempts: 0,
      unexpectedWrites: [], histories: {}, materials: {}, materialBodies: {}, requests: [], normalTasks: {}, normalPosts: 0, eventSourceIds: [],
      nextMode: "complete", speechText: "Fixture dictated turn", denyMicOnce: false,
      active: { active_server: "ollama", active_model: "fixture-vision", runtime_id: "ollama", config_hash: "fixture-vision-hash", active_endpoint: "http://fixture.invalid/v1" },
    };
    state.hmrSockets ??= 0;
    state.unsafeExistingSession = unsafe;
    const save = () => localStorage.setItem(key, JSON.stringify(state));
    const read = () => JSON.parse(JSON.stringify(state));
    const patch = changes => { Object.assign(state, changes); save(); };
    const modelRow = (name, runtime, active) => ({ id: name, name, provider: runtime, runtime_id: runtime,
      source_type: runtime === "ollama" ? "local-runtime" : "cloud-api", active, chat_compatible: true, model_kind: "base_model" });
    const activePayload = () => ({ status: "success", ...state.active });
    const catalog = () => ({ active: { ...state.active }, runtimes: [
      { runtime_id: "ollama", label: "Fixture Ollama", source_type: "local-runtime", configured: true, available: true, status: "running", active: state.active.active_server === "ollama",
        models: ["fixture-vision", "fixture-text"].map(name => modelRow(name, "ollama", state.active.active_model === name)) },
      { runtime_id: "openrouter", label: "Fixture OpenRouter", source_type: "cloud-api", configured: true, available: true, status: "connected", active: state.active.active_server === "openrouter", models: [modelRow("fixture/free", "openrouter", state.active.active_model === "fixture/free")] },
    ], model_catalog: { all_models: [], chat_models: [], coding_models: [], runtime_servable_models: [], trainable_base_models: [] } });
    const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
    const uuid = number => "00000000-0000-4000-8000-" + String(number).padStart(12, "0");
    const remember = (body, id, answer, status) => {
      const stamp = new Date().toISOString();
      const previous = (state.histories[body.session_id] ?? []).filter(entry => entry.request_id !== id);
      state.histories[body.session_id] = [...previous,
        { role: "user", content: body.content, session_id: body.session_id, request_id: id, timestamp: stamp, status: "COMPLETED", ...(body.material_ids?.length ? { material_ids: [...body.material_ids] } : {}) },
        { role: "assistant", content: answer, session_id: body.session_id, request_id: id, timestamp: stamp, status, pending: status === "PROCESSING" },
      ];
    };
    const stream = (body, signal) => {
      state.simplePosts++;
      if (state.nextMode === "reject") { state.nextMode = "complete"; state.rejected++; state.lastRejectedWire = body; save(); return json({ detail: { reason_code: "material_context_limit" } }, 413); }
      const mode = state.nextMode; state.nextMode = "complete";
      const count = ++state.accepted;
      const id = uuid(count);
      const partial = "Fixture partial " + count;
      const answer = partial + " complete";
      const row = { ...body, request_id: id, status: "PROCESSING" };
      state.requests.push(row); state.lastAcceptedWire = body; save();
      const encoder = new TextEncoder();
      let settled = false;
      let firstTimer, finalTimer;
      const output = new ReadableStream({ start(controller) {
        const emit = (event, value) => controller.enqueue(encoder.encode("event: " + event + "\ndata: " + JSON.stringify(value) + "\n\n"));
        const stop = () => {
          if (settled) return; settled = true; clearTimeout(firstTimer); clearTimeout(finalTimer);
          row.status = "CANCELLED"; state.streamAborts++; remember(body, id, partial, "CANCELLED"); save();
          controller.error(new DOMException("Stopped", "AbortError"));
        };
        if (signal?.aborted) { stop(); return; }
        signal?.addEventListener("abort", stop, { once: true });
        firstTimer = setTimeout(() => { if (!settled) { emit("content", { text: partial }); remember(body, id, partial, "PROCESSING"); save(); } }, 40);
        finalTimer = setTimeout(() => {
          if (settled) return; settled = true;
          emit("content", { text: " complete" });
          const cost = { state: "settled", currency: "USD", estimated_usd: "0", reserved_usd: "0", reported_usd: "0", conversation_reported_usd: "0", conversation_reserved_usd: "0", conversation_state: "settled" };
          emit("done", { requested_model: body.model, confirmed_model: body.model, confirmed_provider: state.active.active_server, generation_id: "fixture-" + count, usage_source: "upstream", usage: { prompt_tokens: 12, completion_tokens: 4, total_tokens: 16 }, cost });
          row.status = "COMPLETED"; remember(body, id, answer, "COMPLETED"); save(); controller.close();
        }, mode === "partial" ? 15000 : 140);
      }, cancel() { settled = true; clearTimeout(firstTimer); clearTimeout(finalTimer); } });
      return new Response(output, { headers: { "Content-Type": "text/event-stream", "x-request-id": id } });
    };
    const bodyOf = async (input, init) => {
      if (typeof init?.body === "string") { try { return JSON.parse(init.body); } catch { return {}; } }
      if (input instanceof Request && !init?.body) { try { return await input.clone().json(); } catch { return {}; } }
      return {};
    };
    let releaseAck = () => {};
    globalThis.fetch = async (input, init = {}) => {
      const url = new URL(input instanceof URL ? input.href : typeof input === "string" ? input : input.url, location.href);
      const method = (init.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
      if (url.origin !== location.origin) { state.externalAttempts++; save(); return json({ detail: "external_network_disabled" }, 403); }
      if (!url.pathname.startsWith("/api/")) {
        return nativeFetch(input, init);
      }
      if (unsafe) return json({ detail: "use_dedicated_test_context" }, 409);
      const path = url.pathname;
      state.calls.push({ path, method }); state.calls = state.calls.slice(-600); save();
      const body = await bodyOf(input, init);
      if (path === "/api/v1/system/status") return json({ status: "ok", boot_id: "chat2-b07-boot", version: "fixture" });
      if (path === "/api/v1/config/runtime") return json({ status: "success", config: { UI_THEME_DEFAULT: "venom-dark" } });
      if (path === "/api/v1/system/llm-runtime/options") return json(catalog());
      if (["/api/v1/system/llm-servers/active", "/api/v1/system/llm-runtime/active"].includes(path)) {
        if (method === "POST") {
          const provider = body.server_name || body.provider || state.active.active_server;
          const model = body.model || (provider === "openrouter" ? "fixture/free" : "fixture-vision");
          state.active = { active_server: provider, active_model: model, runtime_id: provider === "openrouter" ? "openrouter@" + model : provider, config_hash: "fixture-" + provider + "-" + model, active_endpoint: "http://fixture.invalid/v1" }; save();
        }
        return json(activePayload());
      }
      if (path === "/api/v1/llm/simple/stream" && method === "POST") {
        if (state.holdNextAck) {
          state.holdNextAck = false; state.waitingAck = true; save();
          await new Promise(resolve => { releaseAck = () => { state.waitingAck = false; save(); resolve(); }; });
        }
        return stream(body, init.signal || (input instanceof Request ? input.signal : null));
      }
      if (path === "/api/v1/tasks" && method === "POST") {
        const id = uuid(++state.accepted); state.normalPosts++;
        const task = { id, task_id: id, session_id: body.session_id, status: "PROCESSING", result: "Fixture Normal partial", logs: [], created_at: new Date().toISOString(), context_history: { session: { session_id: body.session_id } }, prompt: body.content, content: body.content };
        state.normalTasks[id] = task; state.lastNormalId = id;
        remember(body, id, task.result, "PROCESSING");
        state.histories[body.session_id] = state.histories[body.session_id].filter(entry => !(entry.request_id === id && entry.role === "assistant"));
        save(); return json({ task_id: id });
      }
      if (/^\/api\/v1\/tasks\/[^/]+$/.test(path) && method === "GET") {
        const task = state.normalTasks[path.split("/")[4]];
        return task ? json(task) : json({ detail: "fixture_task_not_found" }, 404);
      }
      if (path === "/api/v1/openrouter/status") return json({ enabled: true, configured: true, library_available: true, available: true, authenticated: true, reason: null, pricing_as_of: "2026-10-30" });
      if (path === "/api/v1/openrouter/catalog") return json({ pricing_as_of: "2026-10-30", models: [{ id: "fixture/free", name: "Fixture free model", input_price_per_million: "0", output_price_per_million: "0", request_price: "0", context_length: 32768, max_output_tokens: 1024, pricing_as_of: "2026-10-30" }] });
      if (path === "/api/v1/openrouter/quote") return json({ estimated_usd: "0", currency: "USD", max_output_tokens: 1024, input_token_upper_bound: 200, context_length: 32768, config_hash: state.active.config_hash, quote_hash: "a".repeat(64) });
      if (path.startsWith("/api/v1/memory/session/")) { const session = decodeURIComponent(path.slice("/api/v1/memory/session/".length)); const history = state.histories[session] ?? []; return json({ status: "success", session_id: session, history, summary: null, count: history.length }); }
      if (path === "/api/v1/memory/ingest") return json({ status: "success", id: "fixture-memory" });
      if (path === "/api/v1/chat/materials/capabilities") return json({ document: true, image: state.active.active_server === "ollama" && url.searchParams.get("model") === "fixture-vision", audio: false, video: false, max_bytes: 8388608, max_document_chars: 64000, runtime_id: state.active.runtime_id, config_hash: state.active.config_hash, model: url.searchParams.get("model") });
      if (path === "/api/v1/chat/materials") {
        const session = url.searchParams.get("session_id");
        if (method === "GET") return json({ materials: Object.values(state.materials).filter(item => item.session_id === session) });
        if (method === "POST") {
          const id = uuid(10000 + Object.keys(state.materials).length);
          const file = init.body;
          const name = url.searchParams.get("name");
          const mime = new Headers(init.headers).get("Content-Type") || "text/plain";
          const item = { id, session_id: session, name, mime_type: mime, size_bytes: file.size, kind: mime.startsWith("image/") ? "image" : "document", status: "ready", created_at: new Date().toISOString(), preview_url: "/api/v1/chat/materials/" + id + "/content?session_id=" + encodeURIComponent(session) };
          state.materials[id] = item; state.materialBodies[id] = item.kind === "document" ? await file.text() : "image"; save(); return json(item);
        }
      }
      if (path.startsWith("/api/v1/chat/materials/")) {
        const id = path.split("/")[5]; const item = state.materials[id];
        if (!item || item.session_id !== url.searchParams.get("session_id")) return json({ detail: { reason_code: "material_not_found" } }, 404);
        if (method === "DELETE") { delete state.materials[id]; delete state.materialBodies[id]; save(); return new Response(null, { status: 204 }); }
        if (path.endsWith("/content")) return new Response(item.kind === "document" ? state.materialBodies[id] : new Uint8Array([137, 80, 78, 71]), { headers: { "Content-Type": item.mime_type } });
        return json(item);
      }
      if (path === "/api/v1/chat/audio/transcribe") { state.sttCalls++; save(); return json({ session_id: url.searchParams.get("session_id"), text: state.speechText, pipeline: "host_stt" }); }
      if (path === "/api/v1/chat/audio/speak") { state.ttsCalls++; save(); return new Response(new Uint8Array([82, 73, 70, 70, 0, 0, 0, 0, 87, 65, 86, 69]), { headers: { "Content-Type": "audio/wav" } }); }
      if (path === "/api/v1/history/requests") return json(state.requests.map(item => ({ request_id: item.request_id, session_id: item.session_id, prompt: item.content, status: item.status, created_at: "2026-10-30T12:00:00Z" })));
      if (path.startsWith("/api/v1/chat/tasks/") && method === "POST") {
        const id = path.split("/")[5]; const task = state.normalTasks[id];
        if (!task || task.session_id !== body.session_id) return json({ detail: { reason_code: "chat_task_not_found" } }, 404);
        task.status = "FAILED"; remember(task, id, task.result, "CANCELLED"); save();
        sources.forEach(source => source.emitTask());
        return json({ success: true, task_id: id, status: "cancelled" });
      }
      if (method !== "GET" && method !== "HEAD") { state.unexpectedWrites.push(path); save(); return json({ detail: "unexpected_write_blocked" }, 405); }
      return json({ status: "success", fixture_read_only_empty: true });
    };
    class FakeSocket {
      static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3;
      readyState = 3;
      constructor(url, protocols) {
        const target = new URL(url instanceof URL ? url.href : String(url), location.href);
        const socketOrigin = location.origin.replace(/^http/, "ws");
        const localUI = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
        if (localUI && target.origin === socketOrigin && ["/_next/webpack-hmr", "/_next/hmr"].includes(target.pathname)) {
          state.hmrSockets++; save();
          return protocols === undefined ? new NativeWebSocket(url) : new NativeWebSocket(url, protocols);
        }
        state.socketAttempts++;
        if (target.origin !== socketOrigin) state.externalAttempts++;
        save();
      }
      addEventListener() {} removeEventListener() {} close() {} send() {}
    }
    const sources = new Set();
    class FakeEventSource {
      static CONNECTING = 0; static OPEN = 1; static CLOSED = 2;
      readyState = 1; handlers = new Map(); timer = null;
      constructor(url) {
        this.id = new URL(url, location.href).pathname.split("/")[4];
        state.socketAttempts++; state.eventSourceIds.push(this.id); save(); sources.add(this);
        this.timer = setTimeout(() => { this.onopen?.({ type: "open" }); this.emitTask(); }, 20);
      }
      addEventListener(name, listener) { const list = this.handlers.get(name) ?? []; list.push(listener); this.handlers.set(name, list); }
      removeEventListener(name, listener) { this.handlers.set(name, (this.handlers.get(name) ?? []).filter(item => item !== listener)); }
      emitTask() {
        const task = state.normalTasks[this.id]; if (!task || this.readyState === 2) return;
        const type = ["COMPLETED", "FAILED"].includes(task.status) ? "task_finished" : "task_update";
        const data = JSON.stringify({ task_id: task.id, status: task.status, result: task.result, logs: [], timestamp: new Date().toISOString() });
        for (const listener of this.handlers.get(type) ?? []) listener({ type, data });
      }
      close() { this.readyState = 2; clearTimeout(this.timer); sources.delete(this); }
    }
    const completeNormal = () => {
      for (const task of Object.values(state.normalTasks)) {
        if (task.status !== "PROCESSING") continue;
        task.status = "COMPLETED"; task.result = "Fixture Normal completed after reload";
        remember(task, task.id, task.result, "COMPLETED");
      }
      save(); sources.forEach(source => source.emitTask());
    };
    globalThis.WebSocket = FakeSocket;
    globalThis.EventSource = FakeEventSource;
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: async () => {
      state.micRequests++; save();
      if (state.denyMicOnce) { state.denyMicOnce = false; save(); throw new DOMException("Fixture denied", "NotAllowedError"); }
      state.tracksCreated++; save(); let stopped = false;
      const track = { stop() { if (!stopped) { stopped = true; state.tracksStopped++; save(); } }, kind: "audio", enabled: true };
      return { getTracks: () => [track], getAudioTracks: () => [track] };
    } } });
    const node = () => ({ connect() {}, disconnect() {} });
    class FakeAudioContext {
      sampleRate = 16000; state = "running"; destination = {};
      audioWorklet = { addModule: async () => {} };
      constructor() { state.contextsCreated++; save(); }
      async resume() { this.state = "running"; }
      async close() { if (this.state !== "closed") { state.contextsClosed++; save(); } this.state = "closed"; }
      createMediaStreamSource() { return node(); }
      createGain() { return { ...node(), gain: { value: 0 } }; }
    }
    class FakeAudioWorkletNode {
      constructor() {
        this.port = { onmessage: null, close() {}, postMessage: message => {
          if (message.type === "flush") queueMicrotask(() => {
            this.port.onmessage?.({ data: new Float32Array([0.1, -0.1, 0.2, -0.2]).buffer });
            this.port.onmessage?.({ data: { flushed: true } });
          });
        } };
      }
      connect() {} disconnect() {}
    }
    globalThis.AudioContext = FakeAudioContext;
    globalThis.AudioWorkletNode = FakeAudioWorkletNode;
    URL.createObjectURL = blob => { state.objectURLsCreated++; save(); return nativeCreateURL(blob); };
    URL.revokeObjectURL = url => { state.objectURLsRevoked++; save(); return nativeRevokeURL(url); };
    class FakeAudio {
      onended = null; onerror = null; endedTimer = null; playing = false;
      constructor(url) { this.src = url; }
      async play() { this.playing = true; state.playbackStarted++; state.playbackActive++; save(); this.endedTimer = setTimeout(() => { this.pause(); this.onended?.(); }, 15000); }
      pause() { if (this.playing) { this.playing = false; state.playbackActive--; save(); } if (this.endedTimer) clearTimeout(this.endedTimer); }
      removeAttribute() { this.src = ""; }
    }
    globalThis.Audio = FakeAudio;
    globalThis.__CHAT2_B07__ = { read, patch, completeNormal, releaseAck: () => releaseAck() };
    if (!unsafe) {
      if (!existingSession) { localStorage.setItem("venom-session-id", "chat2-b07-session-a"); localStorage.setItem("venom-next-build-id", "unknown"); }
      localStorage.setItem("venom-backend-boot-id", "chat2-b07-boot");
      localStorage.setItem("venom-language", "pl");
      document.cookie = "venom-language=pl; Path=/; SameSite=Lax";
    }
    save();
  });  const fixture = () => page.evaluate(() => globalThis.__CHAT2_B07__.read());
  const configure = changes => page.evaluate(value => globalThis.__CHAT2_B07__.patch(value), changes);
  const waitFixture = predicate => page.waitForFunction(predicate, undefined, { timeout: 20000 });
  const input = page.locator(".studio-compose textarea");
  const sendButton = page.locator(".studio-send");
  const lastAssistant = page.getByTestId("chat2-message-assistant").last();
  const awaitAnswer = async number => {
    const expected = "Fixture partial " + number + " complete";
    await page.waitForFunction(text => {
      const rows = document.querySelectorAll('[data-testid="chat2-message-assistant"]');
      return rows.length > 0 && rows[rows.length - 1].textContent.includes(text);
    }, expected, { timeout: 20000 });
    await sendButton.waitFor({ state: "visible" });
  };
  const postText = async text => {
    const before = await fixture();
    await input.fill(text); await input.press("Enter");
    await page.waitForFunction(expected => globalThis.__CHAT2_B07__.read().accepted === expected, before.accepted + 1);
    await awaitAnswer(before.accepted + 1);
    return before.accepted + 1;
  };
  const chooseFiles = files => page.locator('.studio-materials input[type="file"]').setInputFiles(files);
  const documentName = "reference-b07.txt";
  const documentText = "<img src=x onerror=globalThis.__b07Injected=true>\nB07 inert reference text";
  try {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(new URL("/chat2", baseURL).href, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => !!globalThis.__CHAT2_B07__);
    let state = await fixture();
    check(!state.unsafeExistingSession, "dedicated test context contains no real Venom session");
    check(state.accepted === 0 && state.micRequests === 0, "fresh fake fixture without previous generation or microphone");
    await page.getByTestId("chat2-shell").waitFor({ state: "visible" });
    await page.waitForFunction(() => document.documentElement.lang === "pl");
    await input.waitFor({ state: "visible" });
    await page.getByRole("combobox", { name: "Model", exact: true }).selectOption("fixture-vision");
    await waitFixture(() => globalThis.__CHAT2_B07__.read().calls.some(call => call.path === "/api/v1/chat/materials/capabilities"));
    state = await fixture();
    const allowedStartup = new Set([
      "/api/v1/system/status", "/api/v1/config/runtime", "/api/v1/system/llm-runtime/options",
      "/api/v1/system/llm-servers/active", "/api/v1/chat/materials", "/api/v1/chat/materials/capabilities",
      "/api/v1/memory/session/chat2-b07-session-a",
    ]);
    const startupPaths = state.calls.filter(call => call.method === "GET").map(call => call.path);
    const startupCount = startupPaths.length;
    check(await page.getByTestId("sidebar").count() === 0, "Studio does not mount the existing sidebar");
    check(await page.getByTestId("cockpit-chat-history").count() === 0, "Studio does not mount the old cockpit chat");
    check(startupPaths.every(path => allowedStartup.has(path) || path.startsWith("/api/v1/memory/session/")), "startup uses only chat, identity, preference and session endpoints");
    check(startupCount <= 24, "startup API request budget <=24 on fake backend");
    check(state.socketAttempts === 0 && state.externalAttempts === 0, "no unsolicited sockets or external network at entry");
    check(state.micRequests === 0 && state.accepted === 0, "opening Studio does not start microphone or generation");
    const originalSession = await page.evaluate(() => localStorage.getItem("venom-session-id"));

    await postText("B07 synthetic turn one");
    await postText("B07 synthetic turn two");
    state = await fixture();
    check(state.lastAcceptedWire.history.some(turn => turn.content === "B07 synthetic turn one"), "second turn carries the same conversation history");
    check(state.lastAcceptedWire.session_id === originalSession, "text turns retain their session identity");

    await configure({ nextMode: "partial" });
    const beforePartial = await fixture();
    await input.fill("B07 partial response to stop"); await input.press("Enter");
    await page.waitForFunction(number => {
      const rows = document.querySelectorAll('[data-testid="chat2-message-assistant"]');
      return rows.length && rows[rows.length - 1].textContent.includes("Fixture partial " + number);
    }, beforePartial.accepted + 1);
    await page.locator(".studio-stop").click();
    await waitFixture(() => globalThis.__CHAT2_B07__.read().streamAborts >= 1);
    await sendButton.waitFor({ state: "visible" });
    check((await lastAssistant.textContent()).includes("Fixture partial " + (beforePartial.accepted + 1)), "Stop preserves the partial assistant response");
    await postText("B07 next turn after Stop");
    check((await lastAssistant.textContent()).includes("complete"), "conversation remains usable after Stop");

    await chooseFiles({ name: documentName, mimeType: "text/plain", buffer: Buffer.from(documentText) });
    await page.locator(".studio-chip").filter({ hasText: documentName }).waitFor({ state: "visible" });
    await page.locator(".studio-file-list li").filter({ hasText: documentName }).getByRole("button", { name: "Podgląd", exact: true }).click();
    await page.locator(".studio-preview pre").waitFor({ state: "visible" });
    check((await page.locator(".studio-preview pre").textContent()) === documentText, "document preview displays inert literal text");
    check(await page.evaluate(() => globalThis.__b07Injected !== true), "preview cannot execute reference HTML");

    await configure({ nextMode: "reject" });
    await input.fill("B07 rejected material draft"); await input.press("Enter");
    await waitFixture(() => globalThis.__CHAT2_B07__.read().rejected === 1);
    await sendButton.waitFor({ state: "visible" });
    check(await input.inputValue() === "B07 rejected material draft", "server rejection preserves editable draft");
    check(await page.locator(".studio-chip").filter({ hasText: documentName }).count() === 1, "server rejection preserves material attachment");
    await postText("B07 accepted material draft");
    state = await fixture();
    check(state.lastAcceptedWire.material_ids?.length === 1, "document is sent as an owned material ID");
    check(await page.locator(".studio-chip").count() === 0, "successful acknowledgement clears draft material selection");
    const materialSession = state.lastAcceptedWire.session_id;
    check(materialSession === originalSession, "materials use the same text conversation session");

    await page.getByRole("button", { name: "Nowa rozmowa", exact: true }).click();
    await page.waitForFunction(previous => localStorage.getItem("venom-session-id") !== previous, originalSession);
    await page.getByRole("button", { name: "Rozmowy", exact: true }).click();
    await page.locator(".studio-session").filter({ hasText: "B07 synthetic turn one" }).click();
    await page.waitForFunction(expected => localStorage.getItem("venom-session-id") === expected, originalSession);
    await page.waitForFunction(() => document.querySelector('[data-testid="chat2-thread"]')?.textContent.includes("B07 accepted material draft"));
    check((await page.getByTestId("chat2-thread").textContent()).includes("B07 synthetic turn one"), "return to an older conversation preserves earlier messages");
    check((await page.getByTestId("chat2-thread").textContent()).includes("Materiały: 1"), "return to an older conversation preserves material references");
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByTestId("chat2-shell").waitFor({ state: "visible" });
    await page.waitForFunction(() => document.querySelector('[data-testid="chat2-thread"]')?.textContent.includes("B07 accepted material draft"));
    check(await page.evaluate(expected => localStorage.getItem("venom-session-id") === expected, originalSession), "reload retains the selected session");
    check((await page.getByTestId("chat2-thread").textContent()).includes("Materiały: 1"), "reload restores persisted material history from fake SessionStore");
    await page.getByRole("combobox", { name: "Model", exact: true }).selectOption("fixture-vision");

    const png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jgU0AAAAASUVORK5CYII=";
    await chooseFiles({ name: "image-b07.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
    await page.locator(".studio-chip").filter({ hasText: "image-b07.png" }).waitFor({ state: "visible" });
    await input.fill("B07 keep image draft");
    await page.getByRole("combobox", { name: "Model", exact: true }).selectOption("fixture-text");
    await page.waitForFunction(() => document.querySelector(".studio-send")?.disabled === true);
    check(await input.inputValue() === "B07 keep image draft", "incompatible model retains the draft");
    check(await page.locator(".studio-chip").filter({ hasText: "image-b07.png" }).count() === 1, "incompatible model retains image attachment");
    await page.locator(".studio-chip").filter({ hasText: "image-b07.png" }).click();
    await page.getByRole("combobox", { name: "Model", exact: true }).selectOption("fixture-vision");
    await input.fill("keyboard line one"); await input.press("Shift+Enter"); await input.pressSequentially("keyboard line two");
    check((await input.inputValue()).includes("\nkeyboard line two"), "Shift+Enter inserts a newline instead of sending");
    await input.fill("");

    const beforeDictation = await fixture();
    await page.getByRole("button", { name: "Dyktuj do szkicu", exact: true }).click();
    await page.locator(".studio-voice").waitFor({ state: "visible" });
    state = await fixture();
    check(state.micRequests === beforeDictation.micRequests, "opening dictation panel does not request microphone");
    await configure({ denyMicOnce: true });
    await page.locator(".studio-voice").getByRole("button", { name: "Nagrywaj turę", exact: true }).click();
    await page.locator(".studio-voice").getByRole("alert").waitFor({ state: "visible" });
    check((await fixture()).tracksCreated === beforeDictation.tracksCreated, "denied microphone permission creates no capture resource");
    await page.locator(".studio-voice").getByRole("button", { name: "Nagrywaj turę", exact: true }).click();
    await page.locator(".studio-voice").getByRole("button", { name: "Zakończ turę", exact: true }).click();
    await page.waitForFunction(() => document.querySelector(".studio-compose textarea")?.value === "Fixture dictated turn");
    state = await fixture();
    check(state.accepted === beforeDictation.accepted, "dictation does not send a model request");
    check(state.sttCalls === beforeDictation.sttCalls + 1, "dictation uses exactly one host STT request");
    check(state.tracksStopped === state.tracksCreated, "dictation releases microphone tracks after the turn");
    await page.locator(".studio-voice").getByRole("button", { name: "Zakończ głos", exact: true }).last().click();

    await input.fill(""); await configure({ speechText: "Fixture spoken turn" });
    const beforeVoice = await fixture();
    await page.getByRole("button", { name: "Rozmowa głosowa", exact: true }).click();
    await page.locator(".studio-voice").waitFor({ state: "visible" });
    check((await fixture()).micRequests === beforeVoice.micRequests, "opening conversation mode does not request microphone");
    await page.locator(".studio-voice").getByRole("button", { name: "Nagrywaj turę", exact: true }).click();
    await page.locator(".studio-voice").getByRole("button", { name: "Zakończ turę", exact: true }).click();
    await page.waitForFunction(expected => globalThis.__CHAT2_B07__.read().accepted === expected, beforeVoice.accepted + 1);
    await page.waitForFunction(expected => globalThis.__CHAT2_B07__.read().ttsCalls === expected, beforeVoice.ttsCalls + 1);
    await page.waitForFunction(expected => globalThis.__CHAT2_B07__.read().playbackStarted === expected, beforeVoice.playbackStarted + 1);
    state = await fixture();
    check(state.simplePosts === beforeVoice.simplePosts + 1, "voice submits exactly one request through the shared text chat");
    check(state.lastAcceptedWire.session_id === originalSession && state.lastAcceptedWire.content === "Fixture spoken turn", "voice and text share session and conversation transport");
    await page.locator(".studio-voice").getByRole("button", { name: "Zakończ głos", exact: true }).last().click();
    await page.locator(".studio-voice").waitFor({ state: "hidden" });
    state = await fixture();
    check(state.tracksStopped === state.tracksCreated && state.contextsClosed === state.contextsCreated, "end voice releases all fake microphone and AudioContext resources");
    check(state.playbackActive === 0 && state.objectURLsRevoked === state.objectURLsCreated, "end voice stops playback and releases object URLs");

    await configure({ holdNextAck: true });
    const beforeAck = await fixture();
    await input.fill("B07 acknowledged snapshot A"); await input.press("Enter");
    await page.waitForFunction(() => globalThis.__CHAT2_B07__.read().waitingAck === true);
    await input.fill("B07 newer unsent draft B");
    await chooseFiles({ name: "new-during-ack.txt", mimeType: "text/plain", buffer: Buffer.from("new attachment") });
    await page.locator(".studio-chip").filter({ hasText: "new-during-ack.txt" }).waitFor({ state: "visible" });
    await page.evaluate(() => globalThis.__CHAT2_B07__.releaseAck());
    await awaitAnswer(beforeAck.accepted + 1);
    check(await input.inputValue() === "B07 newer unsent draft B", "late ACK never clears a newer unsent draft");
    check(await page.locator(".studio-chip").filter({ hasText: "new-during-ack.txt" }).count() === 1, "late ACK never clears a newly selected material");
    await page.locator(".studio-chip").filter({ hasText: "new-during-ack.txt" }).click(); await input.fill("");

    await page.getByRole("combobox", { name: "Tryb pracy", exact: true }).selectOption("normal");
    const beforeNormal = await fixture();
    await input.fill("B07 Normal active across reload"); await input.press("Enter");
    await page.waitForFunction(expected => globalThis.__CHAT2_B07__.read().normalPosts === expected, beforeNormal.normalPosts + 1);
    await page.locator(".studio-stop").waitFor({ state: "visible" });
    const normalId = (await fixture()).lastNormalId;
    await page.waitForFunction(id => globalThis.__CHAT2_B07__.read().eventSourceIds.includes(id), normalId);
    const beforeReloadSubscriptions = (await fixture()).eventSourceIds.filter(id => id === normalId).length;
    await page.waitForFunction(id => Object.keys(sessionStorage).filter(key => key.startsWith("venom-session-history:"))
      .some(key => { try { return JSON.parse(sessionStorage.getItem(key)).some(entry => entry.request_id === id && entry.role === "assistant" && (entry.pending || ["PENDING", "PROCESSING"].includes(entry.status))); } catch { return false; } }), normalId);
    check(true, "active Normal task persists a recoverable pending session snapshot");
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByTestId("chat2-shell").waitFor({ state: "visible" });
    await page.waitForFunction(({ id, count }) => globalThis.__CHAT2_B07__.read().eventSourceIds.filter(value => value === id).length > count, { id: normalId, count: beforeReloadSubscriptions });
    check(true, "reload reconnects the exact persisted Normal task UUID");
    await page.evaluate(() => globalThis.__CHAT2_B07__.completeNormal());
    await page.waitForFunction(() => document.querySelector('[data-testid="chat2-thread"]')?.textContent.includes("Fixture Normal completed after reload"));
    await sendButton.waitFor({ state: "visible" });
    check(true, "terminal SSE after reload clears pending state and unlocks the composer");
    await page.getByRole("combobox", { name: "Tryb pracy", exact: true }).selectOption("direct");

    const normalSourceSession = await page.evaluate(() => localStorage.getItem("venom-session-id"));
    await page.getByRole("button", { name: "Rozmowy", exact: true }).click();
    const otherSession = page.locator(".studio-session").filter({ hasNotText: "B07 synthetic turn one" }).first();
    await otherSession.click();
    await page.waitForFunction(previous => localStorage.getItem("venom-session-id") !== previous, normalSourceSession);
    await page.waitForFunction(() => document.querySelector(".studio-model-line select")?.value === "ollama");
    check(!(await page.getByTestId("chat2-thread").textContent()).includes("Fixture Normal completed after reload"), "selecting another session excludes the previous Normal stream");
    await page.getByRole("combobox", { name: "Tryb pracy", exact: true }).selectOption("normal");
    const secondNormal = await fixture();
    await input.fill("B07 Normal in second session"); await input.press("Enter");
    await page.waitForFunction(expected => globalThis.__CHAT2_B07__.read().normalPosts === expected, secondNormal.normalPosts + 1);
    await page.evaluate(() => globalThis.__CHAT2_B07__.completeNormal());
    await page.waitForFunction(() => document.querySelector(".studio-send") !== null);
    check(await page.getByTestId("chat2-message-user").filter({ hasText: "B07 Normal active across reload" }).count() === 0, "a new Normal task never reintroduces another conversation history");
    await page.getByRole("combobox", { name: "Tryb pracy", exact: true }).selectOption("direct");

    for (let cycle = 0; cycle < 2; cycle++) {
      await page.getByRole("button", { name: "Dyktuj do szkicu", exact: true }).click();
      await page.locator(".studio-voice").getByRole("button", { name: "Nagrywaj turę", exact: true }).click();
      await page.locator(".studio-voice").getByRole("button", { name: "Zakończ turę", exact: true }).click();
      await page.waitForFunction(() => document.querySelector(".studio-compose textarea")?.value === "Fixture spoken turn");
      await page.locator(".studio-voice").getByRole("button", { name: "Zakończ głos", exact: true }).last().click();
      await input.fill("");
    }
    state = await fixture();
    check(state.tracksCreated === state.tracksStopped && state.contextsCreated === state.contextsClosed && state.playbackActive === 0,
      "repeated voice mount/capture/end cycles leave no active microphone, context or playback");
    await page.evaluate(() => {
      const session = localStorage.getItem("venom-session-id");
      const state = globalThis.__CHAT2_B07__.read();
      const history = [];
      for (let index = 0; index < 120; index++) {
        const request_id = "10000000-0000-4000-8000-" + String(index).padStart(12, "0");
        for (const role of ["user", "assistant"]) history.push({ role, request_id, session_id: session,
          content: "B07 long " + role + " " + index, status: "COMPLETED", timestamp: new Date(Date.now() + index).toISOString() });
      }
      globalThis.__CHAT2_B07__.patch({ histories: { ...state.histories, [session]: history } });
    });
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "Pokaż wcześniejsze wiadomości", exact: true }).waitFor({ state: "visible" });
    check(await page.locator(".studio-message").count() === 60, "long conversation initially mounts only 60 recent messages");
    await page.getByRole("button", { name: "Pokaż wcześniejsze wiadomości", exact: true }).click();
    check(await page.locator(".studio-message").count() === 120, "earlier history is available explicitly without eagerly mounting the whole thread");

    for (const [code, label] of [["en", "Send message"], ["de", "Nachricht senden"], ["pl", "Wyślij wiadomość"]]) {
      await page.locator(".studio-language select").selectOption(code);
      await page.waitForFunction(expected => document.documentElement.lang === expected, code);
      await page.getByRole("button", { name: label, exact: true }).waitFor({ state: "visible" });
      check(true, "shell localizes controls in " + code.toUpperCase());
    }
    await page.setViewportSize({ width: 390, height: 844 });
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), "mobile shell does not overflow horizontally");
    check(await page.locator(".studio-materials").count() === 0, "mobile materials stay closed until requested");
    check(await page.locator(".studio-model-line").evaluate(node => { const controls = [...node.querySelectorAll("select,button")].map(control => control.getBoundingClientRect()); return controls.every((box, i) => controls.slice(i + 1).every(other => box.right <= other.left + 1 || box.left >= other.right - 1 || box.bottom <= other.top + 1 || box.top >= other.bottom - 1)); }), "mobile model controls never overlap");
    check(await page.locator(".studio-compose").evaluate(node => { const box = node.getBoundingClientRect(); return box.top >= 0 && box.bottom <= innerHeight; }), "mobile composer stays inside the visible viewport");
    await page.getByRole("button", { name: "Materiały", exact: true }).click();
    await page.getByRole("dialog", { name: "Materiały", exact: true }).waitFor({ state: "visible" });
    await page.keyboard.press("Escape");
    await page.getByRole("dialog", { name: "Materiały", exact: true }).waitFor({ state: "hidden" });
    check(await page.getByRole("button", { name: "Materiały", exact: true }).evaluate(node => document.activeElement === node), "Escape closes mobile materials and restores opener focus");
    await page.getByRole("button", { name: "Zmień motyw", exact: true }).click();
    check(await page.evaluate(() => document.documentElement.dataset.theme === "venom-light"), "Studio uses the existing light theme contract");
    await page.getByRole("button", { name: "Zmień motyw", exact: true }).click();

    await page.setViewportSize({ width: 1440, height: 1000 });
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), "desktop shell does not overflow horizontally");
    state = await fixture();
    check(state.unexpectedWrites.length === 0 && state.externalAttempts === 0, "all mutations used explicitly mocked contracts without external traffic");
    check(pageErrors.length === 0 && hydrationErrors.length === 0, "no uncaught browser or hydration errors");
    return { fakeAPI: true, realProviderCalls: 0, realMicrophoneCalls: 0, assertions, startupCount,
      startupUniqueEndpoints: [...new Set(startupPaths.map(path => path.startsWith("/api/v1/memory/session/") ? "/api/v1/memory/session/:id" : path))],
      counters: { acceptedGenerations: state.accepted, rejectedRequests: state.rejected, cancelledStreams: state.streamAborts,
        normalRequests: state.normalPosts, sttRequests: state.sttCalls, ttsRequests: state.ttsCalls, fakeMicrophoneRequests: state.micRequests,
        tracksCreated: state.tracksCreated, tracksStopped: state.tracksStopped,
        audioContextsCreated: state.contextsCreated, audioContextsClosed: state.contextsClosed,
        playbackStarted: state.playbackStarted, playbackActive: state.playbackActive,
        objectURLsCreated: state.objectURLsCreated, objectURLsRevoked: state.objectURLsRevoked,
        hmrSockets: state.hmrSockets, externalAttempts: state.externalAttempts, unexpectedWrites: state.unexpectedWrites.length,
        pageErrors: pageErrors.length, hydrationErrors: hydrationErrors.length } };
  } catch (error) {
    throw new Error("Chat2 fake acceptance: " + (error instanceof Error ? error.message : String(error)) + "; completed assertions=" + assertions.length + "; failed=" + failures.join(","));
  } finally {
    page.off("pageerror", errorListener); page.off("console", consoleListener);
  }
}
