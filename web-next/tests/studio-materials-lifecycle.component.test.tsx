import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
