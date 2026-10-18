import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";

import { CommandPalette } from "../components/layout/command-palette";
import { LanguageProvider } from "../lib/i18n";

const router = { bfcacheId: "test-router", back() {}, forward() {}, refresh() {}, push() {}, replace() {}, prefetch() {} };
function Harness() {
  const [open, setOpen] = useState(false);
  return <AppRouterContext.Provider value={router}><LanguageProvider>
    <button onClick={() => setOpen(true)}>open commands</button>
    <CommandPalette open={open} onOpenChange={setOpen} onOpenQuickActions={() => {}} />
  </LanguageProvider></AppRouterContext.Provider>;
}
afterEach(cleanup);

describe("CommandPalette managed dialog focus", () => {
  it("focuses search only after opening and restores the invoking control", async () => {
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "open commands" });
    opener.focus();
    assert.equal(document.activeElement, opener);
    fireEvent.click(opener);
    await screen.findByRole("dialog");
    const input = screen.getByRole("textbox");
    await waitFor(() => assert.equal(document.activeElement, input));
    fireEvent.change(input, { target: { value: "test" } });
    assert.equal(document.activeElement, input);
    fireEvent.keyDown(input, { key: "Escape" });
    await waitFor(() => assert.equal(screen.queryByRole("dialog"), null));
    await waitFor(() => assert.equal(document.activeElement, opener));
  });
});
