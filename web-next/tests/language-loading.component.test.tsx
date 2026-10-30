import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it, mock } from "node:test";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { LanguageProvider, useLanguage } from "../lib/i18n";
import type { LocaleDictionary, LanguageCode } from "../lib/i18n";
import { de } from "../lib/i18n/locales/de";

function Probe() {
  const { language, setLanguage, t } = useLanguage();
  return <><span data-testid="language">{language}</span><span data-testid="label">{t("common.loading")}</span>
    <button onClick={() => setLanguage("en")}>EN</button>
    <button onClick={() => setLanguage("de")}>DE</button>
    <button onClick={() => setLanguage("pl")}>PL</button></>;
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem("venom-language", "pl");
  document.cookie = "venom-language=; Path=/; Max-Age=0";
});
afterEach(() => { cleanup(); mock.restoreAll(); });

describe("selected language loading", () => {
  it("renders selected server dictionary in the first snapshot", () => {
    const html = renderToString(<LanguageProvider initialLanguage="de" initialDictionary={de}><Probe /></LanguageProvider>);
    assert.match(html, />de</);
    assert.match(html, /Wird geladen|Laden/);
    assert.doesNotMatch(html, /Ładowanie/);
  });

  it("keeps the previous whole language until a requested dictionary is ready", async () => {
    const pending = deferred<LocaleDictionary>();
    const calls: LanguageCode[] = [];
    render(<LanguageProvider loadDictionary={(code) => { calls.push(code); return pending.promise; }}><Probe /></LanguageProvider>);
    assert.deepEqual(calls, []);
    fireEvent.click(screen.getByText("EN", { selector: "button" }));
    assert.equal(screen.getByTestId("language").textContent, "pl");
    assert.equal(screen.getByTestId("label").textContent, "Ładowanie...");
    await act(async () => pending.resolve({ common: { loading: "Loading..." } }));
    await waitFor(() => assert.equal(screen.getByTestId("language").textContent, "en"));
    assert.equal(screen.getByTestId("label").textContent, "Loading...");
    assert.deepEqual(calls, ["en"]);
    assert.match(document.cookie, /venom-language=en/);
    assert.equal(window.localStorage.getItem("venom-language"), "en");
  });

  it("does not apply an older dictionary after a newer selection", async () => {
    const en = deferred<LocaleDictionary>();
    const german = deferred<LocaleDictionary>();
    render(<LanguageProvider loadDictionary={(code) => code === "en" ? en.promise : german.promise}><Probe /></LanguageProvider>);
    fireEvent.click(screen.getByText("EN", { selector: "button" }));
    fireEvent.click(screen.getByText("DE", { selector: "button" }));
    await act(async () => german.resolve({ common: { loading: "Laden..." } }));
    await act(async () => en.resolve({ common: { loading: "Loading..." } }));
    assert.equal(screen.getByTestId("language").textContent, "de");
    assert.equal(screen.getByTestId("label").textContent, "Laden...");
  });

  it("keeps the working language on a failed chunk and permits retry", async () => {
    mock.method(console, "warn", () => {});
    let attempts = 0;
    render(<LanguageProvider loadDictionary={() => ++attempts === 1
      ? Promise.reject(new Error("chunk unavailable"))
      : Promise.resolve({ common: { loading: "Loading..." } })}><Probe /></LanguageProvider>);
    await act(async () => fireEvent.click(screen.getByText("EN", { selector: "button" })));
    assert.equal(screen.getByTestId("language").textContent, "pl");
    assert.equal(window.localStorage.getItem("venom-language"), "pl");
    await act(async () => fireEvent.click(screen.getByText("EN", { selector: "button" })));
    assert.equal(screen.getByTestId("language").textContent, "en");
  });

  it("migrates legacy localStorage without overwriting it with the initial locale", async () => {
    window.localStorage.setItem("venom-language", "de");
    render(<LanguageProvider loadDictionary={() => Promise.resolve(de)}><Probe /></LanguageProvider>);
    await waitFor(() => assert.equal(screen.getByTestId("language").textContent, "de"));
    assert.match(document.cookie, /venom-language=de/);
    assert.equal(window.localStorage.getItem("venom-language"), "de");
  });

  it("contains denied browser storage and retains cookie preference", async () => {
    document.cookie = "venom-language=de; Path=/";
    mock.method(Object.getPrototypeOf(window.localStorage), "getItem", () => { throw new Error("denied"); });
    mock.method(Object.getPrototypeOf(window.localStorage), "setItem", () => { throw new Error("denied"); });
    render(<LanguageProvider initialLanguage="de" initialDictionary={de}><Probe /></LanguageProvider>);
    assert.equal(screen.getByTestId("language").textContent, "de");
  });
});
