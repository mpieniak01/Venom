"use client";

import { LanguageProvider, type LanguageCode, type LocaleDictionary } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import { ThemeProvider } from "@/lib/theme";
import { ToastProvider } from "@/components/ui/toast";
import { ModelIntrospectionMechanismProvider } from "@/components/inspector/model-introspection-mechanism";

export function Providers({ children, initialLanguage, initialDictionary }: Readonly<{
  children: React.ReactNode;
  initialLanguage?: LanguageCode;
  initialDictionary?: LocaleDictionary;
}>) {
  return (
    <ThemeProvider>
      <LanguageProvider initialLanguage={initialLanguage} initialDictionary={initialDictionary}>
        <SessionProvider>
          <ModelIntrospectionMechanismProvider>
            <ToastProvider>{children}</ToastProvider>
          </ModelIntrospectionMechanismProvider>
        </SessionProvider>
      </LanguageProvider>
    </ThemeProvider>
  );
}
