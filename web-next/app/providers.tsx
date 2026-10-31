"use client";

import { LanguageProvider, type LanguageCode, type LocaleDictionary } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import { ThemeProvider } from "@/lib/theme";
import { ToastProvider } from "@/components/ui/toast";

export function Providers({ children, initialLanguage, initialDictionary }: Readonly<{
  children: React.ReactNode;
  initialLanguage?: LanguageCode;
  initialDictionary?: LocaleDictionary;
}>) {
  return (
    <ThemeProvider>
      <LanguageProvider initialLanguage={initialLanguage} initialDictionary={initialDictionary}>
        <SessionProvider>
            <ToastProvider>{children}</ToastProvider>
        </SessionProvider>
      </LanguageProvider>
    </ThemeProvider>
  );
}
