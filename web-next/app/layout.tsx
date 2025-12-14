import type { Metadata } from "next";
import { Geist, JetBrains_Mono } from "next/font/google";
import { Sidebar } from "@/components/layout/sidebar";
import { TopBar } from "@/components/layout/top-bar";
import "./globals.css";

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
      <body
        className={`${geistSans.variable} ${jetBrains.variable} antialiased`}
      >
        <div className="flex min-h-screen bg-[url('/grid.svg')] bg-cover text-white">
          <Sidebar />
          <div className="flex flex-1 flex-col lg:pl-64">
            <TopBar />
            <main className="flex-1 overflow-y-auto px-4 py-8 sm:px-8">
              <div className="mx-auto w-full max-w-6xl space-y-6">{children}</div>
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
