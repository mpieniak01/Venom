import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import { isLanguageCode, languageFromHeader, LANGUAGE_COOKIE } from "@/lib/i18n/preferences";
import { loadLocale } from "@/lib/i18n/load-locale";
import localFont from "next/font/local";
import { Sidebar } from "@/components/layout/sidebar";
import { TopBarWrapper, TopBarSkeleton } from "@/components/layout/top-bar-wrapper";
import { SystemStatusBarWrapper, SystemStatusBarSkeleton } from "@/components/layout/system-status-bar-wrapper";
import "./globals.css";
import { Providers } from "./providers";
import { Suspense } from "react";
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
          <div className="relative min-h-screen overflow-x-clip bg-[radial-gradient(circle_at_top,var(--app-shell-radial),_transparent_55%)] text-[color:var(--text-primary)]">
            <div className="pointer-events-none absolute inset-0 opacity-60 blur-3xl">
              <div className="absolute -left-10 top-10 h-64 w-64 rounded-full bg-[color:var(--app-orb-left)]" />
              <div className="absolute bottom-10 right-10 h-72 w-72 rounded-full bg-[color:var(--app-orb-right)]" />
            </div>
            <div className="relative z-10 flex">
              <Sidebar />
              <div className="relative flex min-w-0 flex-1 flex-col transition-all duration-300 ease-in-out lg:pl-[var(--sidebar-width)]">
                <Suspense fallback={<TopBarSkeleton />}>
                  <TopBarWrapper />
                </Suspense>
                <main className="px-4 py-10 pb-28 sm:px-8 lg:px-10 lg:pb-32 xl:px-12">
                  <div className="mr-auto w-full max-w-[1320px] xl:max-w-[1536px] 2xl:max-w-[85vw] space-y-6">
                    {children}
                  </div>
                </main>
                <Suspense fallback={<SystemStatusBarSkeleton />}>
                  <SystemStatusBarWrapper />
                </Suspense>
              </div>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
