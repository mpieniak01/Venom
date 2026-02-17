"use client";

import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { SystemStatusPanel } from "./system-status-panel";
import { AuthorSignature } from "./author-signature";
import { useTranslation } from "@/lib/i18n";
import { useSidebarLogic } from "./use-sidebar-logic";
import {
  BrandSection,
  NavigationSection,
  CostModeSection,
  AutonomySection
} from "./sidebar-sections";

export function Sidebar() {
  const pathname = usePathname();
  const t = useTranslation();

  const {
    collapsed,
    setCollapsed,
    isSynced,
    costMode,
    costLoading,
    handleCostToggle,
    autonomyInfo,
    selectedAutonomy,
    autonomyLoading,
    handleAutonomyChange,
    statusMessage,
  } = useSidebarLogic(t);

  return (
    <aside
      className={cn(
        "glass-panel fixed inset-y-0 left-0 z-40 hidden border-r border-white/5 bg-black/25 text-zinc-100 shadow-card lg:block",
        isSynced && "transition-all duration-300 ease-in-out",
        collapsed ? "w-24 px-3 py-6 pb-8" : "w-72 px-5 py-6 pb-8",
      )}
      data-testid="sidebar"
    >
      <BrandSection
        collapsed={collapsed}
        isSynced={isSynced}
        onToggle={() => setCollapsed(!collapsed)}
        t={t}
      />

      <div>
        <NavigationSection
          collapsed={collapsed}
          isSynced={isSynced}
          pathname={pathname}
          t={t}
        />

        <div className={cn("mt-4", isSynced && "transition-all duration-300 ease-in-out", collapsed ? "opacity-0 translate-y-4 pointer-events-none overflow-hidden max-h-0" : "opacity-100 translate-y-0 max-h-[1000px]")}>
          <div className="space-y-4 pt-3">
            <SystemStatusPanel />

            <CostModeSection
              costMode={costMode}
              costLoading={costLoading}
              onToggle={handleCostToggle}
              t={t}
            />

            <AutonomySection
              autonomyInfo={autonomyInfo}
              selectedAutonomy={selectedAutonomy}
              autonomyLoading={autonomyLoading}
              onAutonomyChange={handleAutonomyChange}
              t={t}
            />

            {statusMessage && (
              <p className="text-xs text-emerald-300" data-testid="sidebar-status-message">
                {statusMessage}
              </p>
            )}

            <AuthorSignature />
          </div>
        </div>
      </div>
    </aside>
  );
}
