import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Sidebar } from "@/components/layout/sidebar";
import { TopBarWrapper, TopBarSkeleton } from "@/components/layout/top-bar-wrapper";
import { SystemStatusBarWrapper, SystemStatusBarSkeleton } from "@/components/layout/system-status-bar-wrapper";
import "./globals.css";
import { Providers } from "./providers";
import { Suspense } from "react";

export const dynamic = "force-dynamic";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const jetBrains = JetBrains_Mono({
  variable: "--font-jetbrains",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Venom Cockpit Next",
  description:
    "Next.js frontend for Venom: Cockpit, Flow Inspector, Brain and War Room.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pl" suppressHydrationWarning>
      <body className={`${inter.variable} ${jetBrains.variable} font-sans antialiased`}>
        <Providers>
          <div className="relative min-h-screen overflow-x-hidden bg-[radial-gradient(circle_at_top,_rgba(0,184,255,0.18),_transparent_55%)] text-zinc-100">
            <div className="pointer-events-none absolute inset-0 opacity-60 blur-3xl">
              <div className="absolute -left-10 top-10 h-64 w-64 rounded-full bg-emerald-500/10" />
              <div className="absolute bottom-10 right-10 h-72 w-72 rounded-full bg-violet-500/20" />
            </div>
            <div className="relative z-10 flex">
              <Sidebar />
              <div className="relative flex flex-1 flex-col transition-all duration-300 ease-in-out lg:pl-[var(--sidebar-width)]">
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
