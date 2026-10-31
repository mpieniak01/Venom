import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import { isLanguageCode, languageFromHeader, LANGUAGE_COOKIE } from "@/lib/i18n/preferences";
import { loadLocale } from "@/lib/i18n/load-locale";
import localFont from "next/font/local";
import "./globals.css";
import { Providers } from "./providers";
import {
  DEFAULT_THEME,
  LEGACY_THEME_ALIASES,
  THEME_IDS,
  THEME_STORAGE_KEY,
} from "@/lib/theme-registry";

const inter = localFont({
  src: "./fonts/InterVariable.woff",
  variable: "--font-inter",
  weight: "100 900",
  style: "normal",
  display: "swap",
});

const jetBrains = localFont({
  src: "./fonts/JetBrainsMonoVariable.woff",
  variable: "--font-jetbrains",
  weight: "100 800",
  style: "normal",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Venom Cockpit Next",
  description:
    "Next.js frontend for Venom: Cockpit, Flow Inspector, Brain and War Room.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cookieLanguage = (await cookies()).get(LANGUAGE_COOKIE)?.value;
  const initialLanguage = isLanguageCode(cookieLanguage)
    ? cookieLanguage
    : languageFromHeader((await headers()).get("accept-language"));
  const initialDictionary = initialLanguage === "pl" ? undefined : await loadLocale(initialLanguage);
  const serializedThemeIds = JSON.stringify(THEME_IDS);
  const serializedThemeAliases = JSON.stringify(LEGACY_THEME_ALIASES);
  const serializedAppMeta = JSON.stringify({
    version: process.env.NEXT_PUBLIC_APP_VERSION,
    commit: process.env.NEXT_PUBLIC_APP_COMMIT,
    environmentRole: process.env.NEXT_PUBLIC_ENVIRONMENT_ROLE,
  });
  const themeBootstrapScript = `
    (function () {
      var validThemes = ${serializedThemeIds};
      var legacyAliases = ${serializedThemeAliases};
      try {
        var stored = globalThis.localStorage.getItem("${THEME_STORAGE_KEY}");
        var resolved = typeof stored === "string" && validThemes.includes(stored)
          ? stored
          : (typeof stored === "string" ? legacyAliases[stored] : null);
        var theme = resolved || "${DEFAULT_THEME}";
        if (resolved && stored !== resolved) {
          globalThis.localStorage.setItem("${THEME_STORAGE_KEY}", resolved);
        }
        var root = globalThis.document.documentElement;
        root.dataset.theme = theme;
        root.style.colorScheme = theme === "venom-light" ? "light" : "dark";
      } catch (e) {
        var fallbackRoot = globalThis.document.documentElement;
        fallbackRoot.dataset.theme = "${DEFAULT_THEME}";
        fallbackRoot.style.colorScheme = "dark";
      }
    })();
  `;
  const appMetaBootstrapScript = `
    (function () {
      try {
        globalThis.__VENOM_APP_META__ = ${serializedAppMeta};
      } catch (e) {
        globalThis.__VENOM_APP_META__ = {};
      }
    })();
  `;

  return (
    <html lang={initialLanguage} data-theme={DEFAULT_THEME} suppressHydrationWarning>
      <head>
        <script
          id="venom-theme-bootstrap"
          suppressHydrationWarning
          dangerouslySetInnerHTML={{ __html: themeBootstrapScript }}
        />
        <script
          id="venom-app-meta-bootstrap"
          suppressHydrationWarning
          dangerouslySetInnerHTML={{ __html: appMetaBootstrapScript }}
        />
      </head>
      <body className={`${inter.variable} ${jetBrains.variable} font-sans antialiased`}>
        <Providers initialLanguage={initialLanguage} initialDictionary={initialDictionary}>
          {children}
        </Providers>
      </body>
    </html>
  );
}
