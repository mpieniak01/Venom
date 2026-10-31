import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { StudioMaterials } from "../components/chat/studio-materials";
import { pl } from "../lib/i18n/locales/pl";
import type { ChatMaterial } from "../lib/chat-materials";

function item(id: string, image = false): ChatMaterial {
  return { id, session_id: "one", name: id + (image ? ".png" : ".txt"), mime_type: image ? "image/png" : "text/plain",
    size_bytes: 1, kind: image ? "image" : "document", status: "ready", created_at: "now", preview_url: "unused" };
}
function state(items: ChatMaterial[]) {
  return { items, capabilities: null, error: null, uploading: false, loading: false,
    upload: async () => [], remove: async () => true, refresh: async () => {}, cancelUpload: () => {} };
}
afterEach(() => { cleanup(); mock.restoreAll(); });

test("a fourth selected material blocks unchecked rows but still allows deselection", () => {
  const materialState = state(Array.from({ length: 5 }, (_, index) => item("file" + index)));
  const toggles: string[] = [], onToggle = (id: string) => { toggles.push(id); };
  const onUpload = async () => {}, onClose = () => {};
  const view = render(<StudioMaterials materialState={materialState} selected={["file0", "file1", "file2", "file3"]} onToggle={onToggle} onUpload={onUpload} onClose={onClose} />);
  const extra = screen.getByRole("checkbox", { name: /file4/ }) as HTMLInputElement;
  assert.equal(extra.disabled, true);
  fireEvent.click(extra); assert.deepEqual(toggles, []);
  fireEvent.click(screen.getByRole("checkbox", { name: /file0/ }));
  assert.deepEqual(toggles, ["file0"]);
  view.rerender(<StudioMaterials materialState={materialState} selected={["file1", "file2", "file3"]} onToggle={onToggle} onUpload={onUpload} onClose={onClose} />);
  assert.equal(extra.disabled, false);
  fireEvent.click(extra); assert.deepEqual(toggles, ["file0", "file4"]);
});

test("file choice and drop call the supplied upload callback once each", () => {
  const batches: File[][] = [], onUpload = async (files: File[]) => { batches.push(files); };
  const view = render(<StudioMaterials materialState={state([])} selected={[]} onToggle={() => {}} onUpload={onUpload} onClose={() => {}} />);
  const file = new File(["context"], "context.txt");
  fireEvent.change(view.container.querySelector('input[type="file"]')!, { target: { files: [file] } });
  fireEvent.drop(view.container.querySelector("aside")!, { dataTransfer: { files: [file] } });
  assert.deepEqual(batches, [[file], [file]]);
});

test("unmount aborts preview fetch and revokes the object URL already displayed", async () => {
  let signal: AbortSignal | null = null;
  mock.method(globalThis, "fetch", async (_input: RequestInfo | URL, init?: RequestInit) => { signal = init?.signal as AbortSignal; return new Response(new Uint8Array([1, 2])); });
  mock.method(URL, "createObjectURL", () => "blob:preview-one");
  const revoke = mock.method(URL, "revokeObjectURL", () => {});
  const view = render(<StudioMaterials materialState={state([item("image", true)])} selected={[]} onToggle={() => {}} onUpload={async () => {}} onClose={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: pl.chat2.preview }));
  await waitFor(() => assert.ok(screen.getByRole("img", { name: "image.png" })));
  view.unmount();
  assert.equal((signal as AbortSignal | null)?.aborted, true);
  assert.deepEqual(revoke.mock.calls.map(call => call.arguments), [["blob:preview-one"]]);
});

test("a late blob response after preview unmount never creates an orphan URL", async () => {
  let resolve!: (value: Response) => void;
  const pending = new Promise<Response>(done => { resolve = done; });
  mock.method(globalThis, "fetch", () => pending);
  const create = mock.method(URL, "createObjectURL", () => "blob:must-not-be-created");
  const view = render(<StudioMaterials materialState={state([item("late", true)])} selected={[]} onToggle={() => {}} onUpload={async () => {}} onClose={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: pl.chat2.preview }));
  view.unmount();
  await act(async () => { resolve(new Response(new Uint8Array([1]))); });
  assert.equal(create.mock.calls.length, 0);
});


test("upload and list progress use native status outputs and keep cancellation separate", () => {
  const view = render(<StudioMaterials materialState={{ ...state([]), uploading: true, loading: true }} selected={[]} onToggle={() => {}} onUpload={async () => {}} onClose={() => {}} />);
  const statuses = screen.getAllByRole("status");
  assert.equal(statuses.length, 2);
  assert.ok(statuses.every(element => element.tagName === "OUTPUT"));
  const cancel = screen.getByRole("button", { name: pl.chat2.cancelUpload });
  assert.equal(cancel.closest("output"), null);
  assert.ok(view.container.querySelector("aside"));
});

test("failed removal keeps preview and selection; confirmed removal clears both", async () => {
  mock.method(globalThis, "fetch", async () => new Response("preview context"));
  let removed = false;
  const toggled: string[] = [];
  const materialState = { ...state([item("document")]), remove: async () => removed };
  const view = render(<StudioMaterials materialState={materialState} selected={["document"]} onToggle={id => toggled.push(id)} onUpload={async () => {}} onClose={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: pl.chat2.preview }));
  assert.equal(screen.getByRole("status").tagName, "OUTPUT");
  await waitFor(() => assert.ok(screen.getByText("preview context")));
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: pl.chat2.remove + ": document.txt" })); });
  assert.equal(toggled.length, 0);
  assert.ok(screen.getByText("preview context"));
  removed = true;
  view.rerender(<StudioMaterials materialState={materialState} selected={["document"]} onToggle={id => toggled.push(id)} onUpload={async () => {}} onClose={() => {}} />);
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: pl.chat2.remove + ": document.txt" })); });
  assert.deepEqual(toggled, ["document"]);
  assert.equal(screen.queryByText("preview context"), null);
});


for (const closeFirst of [true, false]) {
  test(`opening the same image ${closeFirst ? "after closing" : "while open"} waits for a fresh URL`, async () => {
    let calls = 0;
    let resolveSecond!: (response: Response) => void;
    mock.method(globalThis, "fetch", () => {
      calls++;
      if (calls === 1) return Promise.resolve(new Response(new Uint8Array([1])));
      return new Promise<Response>(resolve => { resolveSecond = resolve; });
    });
    let urls = 0;
    mock.method(URL, "createObjectURL", () => "blob:preview-" + ++urls);
    const revoke = mock.method(URL, "revokeObjectURL", () => {});
    const view = render(<StudioMaterials materialState={state([item("same", true)])} selected={[]} onToggle={() => {}} onUpload={async () => {}} onClose={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: pl.chat2.preview }));
    await waitFor(() => assert.equal(screen.getByRole("img", { name: "same.png" }).getAttribute("src"), "blob:preview-1"));
    if (closeFirst) {
      fireEvent.click(within(screen.getByRole("region", { name: pl.chat2.preview })).getByRole("button", { name: pl.chat2.close }));
      assert.deepEqual(revoke.mock.calls.map(call => call.arguments), [["blob:preview-1"]]);
    }
    fireEvent.click(screen.getByRole("button", { name: pl.chat2.preview }));
    assert.equal(screen.queryByRole("img", { name: "same.png" }) === null, true);
    assert.equal(screen.getByRole("status").textContent, pl.chat2.loading);
    assert.equal(calls, 2);
    await act(async () => { resolveSecond(new Response(new Uint8Array([2]))); });
    await waitFor(() => assert.equal(screen.getByRole("img", { name: "same.png" }).getAttribute("src"), "blob:preview-2"));
    view.unmount();
    assert.deepEqual(revoke.mock.calls.map(call => call.arguments), [["blob:preview-1"], ["blob:preview-2"]]);
  });
}
