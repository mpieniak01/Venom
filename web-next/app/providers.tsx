"use client";

import { LanguageProvider } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import { ToastProvider } from "@/components/ui/toast";

export function Providers({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <LanguageProvider>
      <SessionProvider>
        <ToastProvider>{children}</ToastProvider>
      </SessionProvider>
    </LanguageProvider>
  );
}
