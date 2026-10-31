import { Suspense } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { TopBarWrapper, TopBarSkeleton } from "@/components/layout/top-bar-wrapper";
import { SystemStatusBarWrapper, SystemStatusBarSkeleton } from "@/components/layout/system-status-bar-wrapper";
import { ModelIntrospectionMechanismProvider } from "@/components/inspector/model-introspection-mechanism";

export default function ConsoleLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <ModelIntrospectionMechanismProvider>
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
  </ModelIntrospectionMechanismProvider>;
}
