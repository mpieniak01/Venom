"use client";

import { LanguageProvider } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import { ThemeProvider } from "@/lib/theme";
import { ToastProvider } from "@/components/ui/toast";
import { ModelIntrospectionMechanismProvider } from "@/components/inspector/model-introspection-mechanism";

export function Providers({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <SessionProvider>
          <ModelIntrospectionMechanismProvider>
            <ToastProvider>{children}</ToastProvider>
          </ModelIntrospectionMechanismProvider>
        </SessionProvider>
      </LanguageProvider>
    </ThemeProvider>
  );
}
