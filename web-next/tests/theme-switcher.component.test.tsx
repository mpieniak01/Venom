import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, render, screen } from "@testing-library/react";

import { ThemeSwitcher } from "../components/layout/theme-switcher";
import { ThemeProvider } from "../lib/theme";
import { LanguageProvider } from "../lib/i18n";
import { THEME_STORAGE_KEY } from "../lib/theme-registry";

const LANGUAGE_STORAGE_KEY = "venom-language";

afterEach(() => {
  cleanup();
  window.localStorage.removeItem(THEME_STORAGE_KEY);
  window.localStorage.removeItem(LANGUAGE_STORAGE_KEY);
  delete document.documentElement.dataset.theme;
});

describe("ThemeSwitcher", () => {
  it("renders selector and both theme options", async () => {
    render(
      <ThemeProvider>
        <LanguageProvider>
          <ThemeSwitcher />
        </LanguageProvider>
      </ThemeProvider>,
    );

    await act(async () => {
      screen.getByTestId("topbar-theme-switcher").click();
    });

    assert.ok(screen.getByTestId("theme-option-venom-dark"));
    assert.ok(screen.getByTestId("theme-option-venom-light"));
  });

  it("switches theme and persists selection", async () => {
    render(
      <ThemeProvider>
        <LanguageProvider>
          <ThemeSwitcher />
        </LanguageProvider>
      </ThemeProvider>,
    );

    await act(async () => {
      screen.getByTestId("topbar-theme-switcher").click();
    });

    await act(async () => {
      screen.getByTestId("theme-option-venom-light").click();
    });

    assert.equal(document.documentElement.dataset.theme, "venom-light");
    assert.equal(window.localStorage.getItem(THEME_STORAGE_KEY), "venom-light");
  });

  it("keeps stable rendered labels for dark and light snapshots", async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "venom-dark");
    const dark = render(
      <ThemeProvider>
        <LanguageProvider>
          <ThemeSwitcher />
        </LanguageProvider>
      </ThemeProvider>,
    );
    const darkLabel = dark.getByTestId("topbar-theme-switcher").textContent?.replace(/\s+/g, " ");
    assert.equal(darkLabel?.includes("Dark"), true);
    dark.unmount();

    window.localStorage.setItem(THEME_STORAGE_KEY, "venom-light");
    render(
      <ThemeProvider>
        <LanguageProvider>
          <ThemeSwitcher />
        </LanguageProvider>
      </ThemeProvider>,
    );
    const lightLabel = screen
      .getByTestId("topbar-theme-switcher")
      .textContent?.replace(/\s+/g, " ");
    assert.equal(lightLabel?.includes("Light"), true);
  });
});
