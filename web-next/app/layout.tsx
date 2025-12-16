import type { Metadata } from "next";
import { Geist, JetBrains_Mono } from "next/font/google";
import { Sidebar } from "@/components/layout/sidebar";
import { TopBar } from "@/components/layout/top-bar";
import { SystemStatusBar } from "@/components/layout/system-status-bar";
import "./globals.css";
import { Providers } from "./providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
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
    "Next.js frontend dla Venom: Cockpit, Flow Inspector, Brain i War Room.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pl">
      <body className={`${geistSans.variable} ${jetBrains.variable} antialiased`}>
        <Providers>
          <div className="relative min-h-screen overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(0,184,255,0.18),_transparent_55%)] text-zinc-100">
            <div className="pointer-events-none absolute inset-0 opacity-60 blur-3xl">
              <div className="absolute -left-10 top-10 h-64 w-64 rounded-full bg-emerald-500/10" />
              <div className="absolute bottom-10 right-10 h-72 w-72 rounded-full bg-violet-500/20" />
            </div>
            <div className="relative z-10 flex">
              <Sidebar />
              <div className="relative flex flex-1 flex-col lg:pl-72">
                <TopBar />
                <main className="flex-1 overflow-y-auto px-4 py-10 pb-24 sm:px-10">
                  <div className="mx-auto w-full max-w-6xl space-y-6">{children}</div>
                </main>
                <SystemStatusBar />
              </div>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
