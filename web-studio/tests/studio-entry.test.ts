import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, readdirSync, lstatSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { prepareStudio } from "../scripts/prepare-studio.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.dirname(appRoot);
const require = createRequire(import.meta.url);

function fixture() {
  const repository = mkdtempSync(path.join(os.tmpdir(), "venom-studio-entry-"));
  const app = path.join(repository, "web-studio");
  mkdirSync(app);
  writeFileSync(path.join(app, "package.json"), JSON.stringify({ name: "studio-fixture", version: "1.0.0" }));
  return { repository, app, shared: path.join(repository, "web-next", "node_modules") };
}

function installFixtureTree(shared: string) {
  mkdirSync(path.join(shared, "next"), { recursive: true });
  writeFileSync(path.join(shared, "next", "package.json"), "{}");
  const publicDir = path.join(path.dirname(shared), "public");
  mkdirSync(publicDir);
  writeFileSync(path.join(publicDir, "chat2-capture-worklet.js"), readFileSync(path.join(repositoryRoot, "web-next/public/chat2-capture-worklet.js")));
}

test("preparation refuses absent shared dependencies without partial installation", () => {
  const item = fixture();
  try {
    assert.throws(() => prepareStudio(item.app), /existing web-next\/node_modules/);
    assert.deepEqual(readdirSync(item.app), ["package.json"]);
  } finally { rmSync(item.repository, { recursive: true, force: true }); }
});

test("preparation shares dependencies idempotently and prepares only own metadata and required worklet", () => {
  const item = fixture();
  const originalRole = process.env.ENVIRONMENT_ROLE;
  try {
    process.env.ENVIRONMENT_ROLE = "preprod";
    installFixtureTree(item.shared);
    const sharedSentinel = path.join(path.dirname(item.shared), "shared-sentinel.json");
    writeFileSync(sharedSentinel, "untouched");
    prepareStudio(item.app);
    const link = path.join(item.app, "node_modules");
    assert.equal(lstatSync(link).isSymbolicLink(), true);
    assert.equal(realpathSync(link), realpathSync(item.shared));
    const inode = lstatSync(link).ino;
    const metadata = JSON.parse(readFileSync(path.join(item.app, "public/meta.json"), "utf8"));
    assert.equal(metadata.appName, "studio-fixture");
    assert.equal(metadata.version, "1.0.0");
    assert.equal(metadata.environmentRole, "preprod");
    assert.equal(metadata.generatedBy, "web-studio/scripts/prepare-studio.mjs");
    prepareStudio(item.app);
    assert.equal(lstatSync(link).ino, inode);
    assert.equal(readFileSync(sharedSentinel, "utf8"), "untouched");
    assert.deepEqual(readdirSync(path.dirname(item.shared)).sort(), ["node_modules", "public", "shared-sentinel.json"]);
    assert.deepEqual(readdirSync(item.app).sort(), ["node_modules", "package.json", "public"]);
  } finally {
    if (originalRole === undefined) delete process.env.ENVIRONMENT_ROLE;
    else process.env.ENVIRONMENT_ROLE = originalRole;
    rmSync(item.repository, { recursive: true, force: true });
  }
});

test("preparation copies real worklet bytes, refreshes changed source and omits unrelated assets", () => {
  const item = fixture();
  try {
    installFixtureTree(item.shared);
    const sharedPublic = path.join(path.dirname(item.shared), "public");
    const worklet = path.join(sharedPublic, "chat2-capture-worklet.js");
    const target = path.join(item.app, "public", "chat2-capture-worklet.js");
    const sha = (value: Uint8Array) => createHash("sha256").update(value).digest("hex");
    const actualSource = readFileSync(path.join(repositoryRoot, "web-next/public/chat2-capture-worklet.js"));
    writeFileSync(path.join(sharedPublic, "unrelated.svg"), "not copied");
    prepareStudio(item.app);
    assert.deepEqual(readFileSync(target), actualSource);
    const initialHash = sha(readFileSync(target));
    assert.equal(initialHash, sha(actualSource));
    const updated = Buffer.concat([actualSource, Buffer.from("\n// fixture source revision\n")]);
    writeFileSync(worklet, updated);
    prepareStudio(item.app);
    assert.deepEqual(readFileSync(target), updated);
    assert.equal(sha(readFileSync(target)), sha(readFileSync(worklet)));
    assert.notEqual(sha(readFileSync(target)), initialHash);
    assert.deepEqual(readdirSync(path.join(item.app, "public")).sort(), ["chat2-capture-worklet.js", "meta.json"]);
    assert.equal(readFileSync(path.join(sharedPublic, "unrelated.svg"), "utf8"), "not copied");
  } finally { rmSync(item.repository, { recursive: true, force: true }); }
});

test("preparation fails before writes when the required shared worklet is absent", () => {
  const item = fixture();
  try {
    installFixtureTree(item.shared);
    rmSync(path.join(path.dirname(item.shared), "public", "chat2-capture-worklet.js"));
    assert.throws(() => prepareStudio(item.app), /chat2-capture-worklet/);
    assert.deepEqual(readdirSync(item.app), ["package.json"]);
  } finally { rmSync(item.repository, { recursive: true, force: true }); }
});

/** Evaluate real TSX with inert boundary adapters; no fetch, media or runtime. */
function loadTsx(file: string, imports: Record<string, unknown>) {
  const code = ts.transpileModule(readFileSync(file, "utf8"), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
  } }).outputText;
  const loaded = { exports: {} as Record<string, unknown> };
  const resolve = (name: string) => {
    if (Object.hasOwn(imports, name)) return imports[name];
    if (["react", "react/jsx-runtime"].includes(name)) return require(name);
    throw new Error("Unexpected Studio test dependency: " + name);
  };
  new Function("require", "module", "exports", code)(resolve, loaded, loaded.exports);
  return loaded.exports;
}

function shell() {
  const noCall = () => { throw new Error("No runtime/transport expected during SSR"); };
  const nullComponent = () => null;
  const imports: Record<string, unknown> = {
    "next/link": ({ children, prefetch, ...props }: React.PropsWithChildren<Record<string, unknown>>) => { void prefetch; return createElement("a", props, children); },
    "next/dynamic": () => nullComponent,
    "lucide-react": new Proxy({}, { get: () => nullComponent }),
    "@/lib/i18n": { useLanguage: () => ({ t: (key: string) => key, language: "pl", setLanguage: noCall }) },
    "@/lib/theme": { useTheme: () => ({ theme: "venom-dark", setTheme: noCall }) },
    "@/lib/session": { useSession: () => ({ sessionId: "fixture-session", setSessionId: noCall }) },
    "@/lib/api-client": { apiFetch: noCall },
    "@/hooks/use-api": { cancelSimpleChatStream: noCall },
    "@/lib/chat-sessions": { readChatSessions: () => [] },
    "@/lib/chat-materials": { materialBlocked: () => false },
    "@/components/cockpit/hooks/use-cockpit-interactive-state": { useCockpitInteractiveState: () => ({
      state: { sending: false, chatMode: "direct", selectedLlmModel: "fixture", selectedLlmServer: "ollama" },
      setters: { setMessage: noCall, setSending: noCall }, optimistic: { simpleRequestDetails: {} },
    }) },
    "@/components/cockpit/hooks/use-cockpit-layout": { useCockpitLayout: () => ({}) },
    "./use-conversation-controller": { useConversationController: () => ({
      historyMessages: [], normalRequestIds: [], chatUi: { handleSend: noCall, handleChatScroll: noCall },
      sessionActions: { handleSessionReset: noCall },
    }) },
    "./use-conversation-data": { useConversationData: () => ({ data: {}, loading: false, error: null, refresh: noCall }) },
    "./use-session-draft": { useSessionDraft: () => useState("") },
    "./use-chat-materials": { useChatMaterials: () => ({ items: [], capabilities: null, uploading: false, upload: noCall }) },
    "./studio-model-picker": { StudioModelPicker: nullComponent },
    "./studio-materials": { StudioMaterials: nullComponent },
    "./studio-thread": { StudioThread: nullComponent },
    "./studio.css": {},
  };
  return loadTsx(path.join(repositoryRoot, "web-next/components/chat/studio-shell.tsx"), imports).StudioShell as React.ComponentType<{ showLegacyLink?: boolean }>;
}

test("shared Full shell retains its legacy navigation by default", () => {
  const html = renderToStaticMarkup(createElement(shell()));
  assert.match(html, /data-testid="chat2-shell"/);
  assert.match(html, /href="\/chat"/);
  assert.match(html, /aria-label="chat2.back"/);
});

test("standalone entry renders the same shell without a dead classic link", () => {
  const StudioShell = shell();
  const Page = loadTsx(path.join(appRoot, "app/chat2/page.tsx"), {
    "@/components/chat/studio-shell": { StudioShell },
  }).default as React.ComponentType;
  const html = renderToStaticMarkup(createElement(Page));
  assert.match(html, /data-testid="chat2-shell"/);
  assert.match(html, /aria-label="chat2.placeholder"/);
  assert.doesNotMatch(html, /href="\/chat"/);
  assert.match(html, /chat2.send/);
});

test("standalone root redirects to chat2 without touching a provider", () => {
  const redirects: string[] = [];
  const Page = loadTsx(path.join(appRoot, "app/page.tsx"), {
    "next/navigation": { redirect: (url: string) => { redirects.push(url); } },
  }).default as () => void;
  Page();
  assert.deepEqual(redirects, ["/chat2"]);
});

test("route discovery stays inside the standalone app and cannot expose Full pages", () => {
  function pages(directory: string): string[] {
    return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
      const absolute = path.join(directory, entry.name);
      if (entry.isDirectory()) return pages(absolute);
      return /^page\.(tsx?|jsx?)$/.test(entry.name) ? [path.relative(path.join(appRoot, "app"), absolute)] : [];
    });
  }
  assert.deepEqual(pages(path.join(appRoot, "app")).sort(), ["chat2/page.tsx", "page.tsx"]);
  const config = JSON.parse(readFileSync(path.join(appRoot, "tsconfig.json"), "utf8"));
  assert.deepEqual(config.compilerOptions.paths["@/*"], ["../web-next/*"]);
  const layout = readFileSync(path.join(appRoot, "app/layout.tsx"), "utf8");
  assert.match(layout, /export \{ default \} from "@\/app\/layout"/);
  assert.doesNotMatch(layout, /Sidebar|ConsoleLayout|TopBar|SystemStatusBar|ModelIntrospection/);
});

for (const command of ["dev:turbo", "dev:turbo:debug"]) {
  test(`${command} prepares fresh dependencies and forwards UI host/port unchanged through npm`, () => {
    const item = fixture();
    try {
      installFixtureTree(item.shared);
      writeFileSync(path.join(item.app, "package.json"), readFileSync(path.join(appRoot, "package.json")));
      mkdirSync(path.join(item.app, "scripts"));
      writeFileSync(path.join(item.app, "scripts/prepare-studio.mjs"), readFileSync(path.join(appRoot, "scripts/prepare-studio.mjs")));
      const sharedScripts = path.join(path.dirname(item.shared), "scripts");
      mkdirSync(sharedScripts);
      const capture = path.join(item.repository, "arguments.json");
      writeFileSync(path.join(sharedScripts, "serve-with-proxy.mjs"), `
        import {writeFileSync,existsSync,realpathSync} from 'node:fs';
        writeFileSync(process.env.ARGV_CAPTURE, JSON.stringify({
          args:process.argv.slice(2), prepared:existsSync('public/chat2-capture-worklet.js'),
          dependencies:realpathSync('node_modules'), apiPort:process.env.PORT
        }));
      `);
      execFileSync("npm", ["run", command, "--", "--hostname", "127.0.0.1", "--port", "3300"], {
        cwd:item.app, env:{...process.env, PORT:"8800", ARGV_CAPTURE:capture}, stdio:"pipe",
      });
      const observed = JSON.parse(readFileSync(capture, "utf8"));
      assert.deepEqual(observed.args, ["dev", "--turbo", "--hostname", "127.0.0.1", "--port", "3300"]);
      assert.equal(observed.prepared, true);
      assert.equal(observed.dependencies, realpathSync(item.shared));
      assert.equal(observed.apiPort, "8800");
    } finally { rmSync(item.repository, {recursive:true, force:true}); }
  });
}
