import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";
import { useRef, useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "../components/ui/sheet";
import { ServiceStatusDrawer } from "../components/layout/service-status-drawer";
import { LanguageProvider } from "../lib/i18n";
import { en } from "../lib/i18n/locales/en";

const originalFetch = globalThis.fetch;

function Panel({ open, onOpenChange }: { open: boolean; onOpenChange: (value: boolean) => void }) {
  const [draft, setDraft] = useState("");
  return <Sheet open={open} onOpenChange={onOpenChange}>
    <SheetContent><SheetTitle>Panel</SheetTitle><SheetDescription>Panel details</SheetDescription>
      <input aria-label="draft" value={draft} onChange={(event) => setDraft(event.target.value)} />
    </SheetContent>
  </Sheet>;
}

function DeferredPanel() {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  return <>
    <button onClick={() => { setMounted(true); setOpen(true); }}>open panel</button>
    {mounted && <Panel open={open} onOpenChange={setOpen} />}
  </>;
}

function CustomFocusPanel() {
  const [open, setOpen] = useState(false);
  const target = useRef<HTMLButtonElement>(null);
  return <>
    <button onClick={() => setOpen(true)}>open custom</button>
    <button ref={target}>custom return</button>
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent onCloseAutoFocus={(event) => { event.preventDefault(); target.current?.focus(); }}>
        <SheetTitle>Custom</SheetTitle><SheetDescription>Custom focus</SheetDescription>
      </SheetContent>
    </Sheet>
  </>;
}

function english(children: React.ReactNode) {
  return <LanguageProvider initialLanguage="en" initialDictionary={en}>{children}</LanguageProvider>;
}

beforeEach(() => {
  window.localStorage.setItem("venom-language", "en");
  document.cookie = "venom-language=en; Path=/";
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("Sheet invoking control focus", () => {
  it("restores Escape and Close focus for a lazily mounted panel and retains its state on reopen", async () => {
    render(english(<DeferredPanel />));
    const opener = screen.getByRole("button", { name: "open panel" });
    opener.focus();
    fireEvent.click(opener);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => assert.ok(dialog.contains(document.activeElement)));
    fireEvent.change(screen.getByRole("textbox", { name: "draft" }), { target: { value: "retained draft" } });
    fireEvent.keyDown(document.activeElement ?? dialog, { key: "Escape" });
    await waitFor(() => assert.equal(screen.queryByRole("dialog"), null));
    await waitFor(() => assert.equal(document.activeElement, opener));

    fireEvent.click(opener);
    await screen.findByRole("dialog");
    assert.equal((screen.getByRole("textbox", { name: "draft" }) as HTMLInputElement).value, "retained draft");
    fireEvent.click(screen.getByRole("button", { name: "Close", exact: true }));
    await waitFor(() => assert.equal(screen.queryByRole("dialog"), null));
    await waitFor(() => assert.equal(document.activeElement, opener));
  });

  it("preserves a caller's explicit close focus handler", async () => {
    render(english(<CustomFocusPanel />));
    const opener = screen.getByRole("button", { name: "open custom" });
    opener.focus();
    fireEvent.click(opener);
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "Close", exact: true }));
    await waitFor(() => assert.equal(screen.queryByRole("dialog"), null));
    await waitFor(() => assert.equal(document.activeElement, screen.getByRole("button", { name: "custom return" })));
  });

  it("retains the Radix trigger behavior for sheets that use a SheetTrigger", async () => {
    render(english(<Sheet><SheetTrigger asChild><button>native trigger</button></SheetTrigger>
      <SheetContent><SheetTitle>Triggered</SheetTitle><SheetDescription>Native trigger details</SheetDescription></SheetContent>
    </Sheet>));
    const opener = screen.getByRole("button", { name: "native trigger" });
    opener.focus();
    fireEvent.click(opener);
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "Close", exact: true }));
    await waitFor(() => assert.equal(screen.queryByRole("dialog"), null));
    await waitFor(() => assert.equal(document.activeElement, opener));
  });
});

describe("ServiceStatusDrawer summary", () => {
  it("counts four online rows as healthy instead of offline", async () => {
    globalThis.fetch = async () => Response.json({ services: ["LanceDB", "Redis", "Kernel", "MCP"].map(name => ({ name, status: "online" })) });
    render(english(<ServiceStatusDrawer open onOpenChange={() => {}} />));
    await screen.findByText("LanceDB");
    const summary = screen.getByTestId("service-status-summary");
    assert.ok(within(summary).getByText("4 healthy", { exact: true }));
    assert.ok(within(summary).getByText("0 degraded", { exact: true }));
    assert.ok(within(summary).getByText("0 down", { exact: true }));
    assert.equal(screen.getAllByText("online", { exact: true }).length, 4);
  });

  it("uses consistent categories for online, healthy, degraded, offline and unknown rows", async () => {
    const statuses = ["online", "HEALTHY", "degraded", "warn", "offline", "unhealthy", "unknown"];
    globalThis.fetch = async () => Response.json({ services: statuses.map((status, index) => ({ name: "row-" + index, status })) });
    render(english(<ServiceStatusDrawer open onOpenChange={() => {}} />));
    await screen.findByText("row-6");
    const summary = screen.getByTestId("service-status-summary");
    assert.ok(within(summary).getByText("2 healthy", { exact: true }));
    assert.ok(within(summary).getByText("2 degraded", { exact: true }));
    assert.ok(within(summary).getByText("2 down", { exact: true }));
    assert.ok(within(summary).getByText("Unknown: 1", { exact: true }));
    for (const status of statuses) assert.ok(screen.getByText(status, { exact: true }));
  });
});
