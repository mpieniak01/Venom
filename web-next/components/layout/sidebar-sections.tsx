import Link from "next/link";
import {
    Sparkles,
    Shield,
    PanelLeftClose,
    PanelLeftOpen
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { navItems, AUTONOMY_LEVELS, AutonomySnapshot } from "./sidebar-helpers";

export function BrandSection({
    collapsed,
    isSynced,
    onToggle,
    t
}: {
    collapsed: boolean;
    isSynced: boolean;
    onToggle: () => void;
    t: (key: string) => string;
}) {
    return (
        <div className="flex flex-col gap-6">
            <div className={cn("flex items-center", collapsed ? "justify-center" : "justify-between")}>
                <div className="flex items-center">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-xl">
                        🐍
                    </div>
                    <div className={cn(isSynced && "transition-all duration-300 ease-in-out", collapsed ? "max-w-0 opacity-0 overflow-hidden" : "max-w-[200px] opacity-100 ml-3")}>
                        <div className="flex items-center gap-2 whitespace-nowrap">
                            <p className="eyebrow">{t("sidebar.brand.caption")}</p>
                            <span className="pill-badge">v1.0</span>
                        </div>
                    </div>
                </div>
                <div className={cn(isSynced && "transition-all duration-300", collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100 w-auto")}>
                    <button
                        type="button"
                        aria-label={collapsed ? t("sidebar.expand") : t("sidebar.collapse")}
                        className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/20 bg-black/80 text-white shadow-card transition hover:border-white/40 hover:bg-white/10"
                        onClick={onToggle}
                        data-testid="sidebar-toggle"
                    >
                        <PanelLeftClose className="h-4 w-4" />
                    </button>
                </div>
            </div>

            <div className={cn("flex justify-center", isSynced && "transition-all duration-300", collapsed ? "max-h-12 opacity-100" : "max-h-0 opacity-0 overflow-hidden")}>
                <button
                    type="button"
                    aria-label={t("sidebar.expand")}
                    className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/20 bg-black/80 text-white shadow-card transition hover:border-white/40 hover:bg-white/10"
                    onClick={() => onToggle()}
                >
                    <PanelLeftOpen className="h-4 w-4" />
                </button>
            </div>
        </div>
    );
}

export function NavigationSection({
    collapsed,
    isSynced,
    pathname,
    t
}: {
    collapsed: boolean;
    isSynced: boolean;
    pathname: string;
    t: (key: string) => string;
}) {
    return (
        <nav className="mt-8 space-y-5">
            <div>
                <div className={cn(isSynced && "transition-all duration-300 ease-in-out", collapsed ? "opacity-0 max-h-0 overflow-hidden" : "opacity-100 max-h-12 mb-3")}>
                    <p className="eyebrow">{t("sidebar.modulesTitle")}</p>
                </div>
                <div className="mt-3 space-y-2">
                    {navItems.map((item) => {
                        const Icon = item.icon;
                        const active = pathname === item.href;
                        const label = item.labelKey ? t(item.labelKey) : item.label;
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                title={label}
                                aria-label={label}
                                className={cn(
                                    "flex w-full items-center rounded-2xl border text-sm font-medium pointer-events-auto",
                                    isSynced && "transition-all duration-300 ease-in-out",
                                    collapsed ? "justify-center px-0 py-3" : "px-4 py-2",
                                    active
                                        ? "border-emerald-300/60 bg-gradient-to-r from-emerald-500/10 to-transparent text-emerald-200 shadow-neon"
                                        : "border-white/10 bg-black/30 text-white hover:border-white/30 hover:bg-white/5",
                                    "cursor-pointer",
                                )}
                                aria-current={active ? "page" : undefined}
                            >
                                <Icon className={cn("h-4 w-4 shrink-0 transition-colors", active ? "text-emerald-300" : "text-zinc-400")} />
                                <span className={cn(isSynced && "transition-all duration-300 ease-in-out", "whitespace-nowrap overflow-hidden", collapsed ? "max-w-0 opacity-0 ml-0" : "max-w-[200px] opacity-100 ml-3")}>
                                    {label}
                                </span>
                            </Link>
                        );
                    })}
                </div>
            </div>
        </nav>
    );
}

export function CostModeSection({
    costMode,
    costLoading,
    onToggle,
    t
}: {
    costMode: { enabled: boolean; provider?: string } | null;
    costLoading: boolean;
    onToggle: () => void;
    t: (key: string) => string;
}) {
    return (
        <section className="rounded-2xl card-shell bg-gradient-to-b from-emerald-500/5 to-transparent p-4 text-sm" data-testid="sidebar-cost-mode">
            <div className="flex items-start justify-between gap-3">
                <div>
                    <p className="eyebrow">{t("sidebar.cost.title")}</p>
                    <p className="text-lg font-semibold text-white">
                        {costMode?.enabled ? t("sidebar.cost.pro") : t("sidebar.cost.eco")}
                    </p>
                    <p className="text-xs text-zinc-400">
                        {t("common.provider")}: {costMode?.provider ?? "brak"}
                    </p>
                </div>
                <Sparkles className="h-5 w-5 text-emerald-200" />
            </div>
            <Button
                className="mt-3 w-full justify-center"
                size="sm"
                variant={costMode?.enabled ? "warning" : "secondary"}
                disabled={costLoading}
                onClick={onToggle}
            >
                {costLoading ? t("sidebar.cost.switching") : (costMode?.enabled ? t("sidebar.cost.switchToEco") : t("sidebar.cost.switchToPro"))}
            </Button>
        </section>
    );
}

export function AutonomySection({
    autonomyInfo,
    selectedAutonomy,
    autonomyLoading,
    onAutonomyChange,
    t
}: {
    autonomyInfo: AutonomySnapshot;
    selectedAutonomy: string;
    autonomyLoading: number | null;
    onAutonomyChange: (level: number) => void;
    t: (key: string) => string;
}) {
    return (
        <section className="rounded-2xl card-shell bg-gradient-to-b from-violet-500/5 to-transparent p-4 text-sm" data-testid="sidebar-autonomy">
            <div className="flex items-start justify-between gap-3">
                <div>
                    <p className="eyebrow">{t("sidebar.autonomy.title")}</p>
                    <p className="text-lg font-semibold text-white">{autonomyInfo.name}</p>
                    <p className="text-xs text-zinc-400">
                        Poziom {autonomyInfo.level ?? "brak"} • {autonomyInfo.risk}
                    </p>
                </div>
                <Shield className="h-5 w-5 text-violet-200" />
            </div>
            <div className="mt-3">
                <label className="text-xs text-zinc-500" htmlFor="autonomy-select">
                    {t("sidebar.autonomy.selectLabel")}
                </label>
                <select
                    id="autonomy-select"
                    data-testid="sidebar-autonomy-select"
                    className="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-violet-400 focus:ring-0"
                    value={selectedAutonomy}
                    onChange={(e) => onAutonomyChange(Number(e.target.value))}
                    disabled={autonomyLoading !== null}
                >
                    <option value="" disabled>
                        {autonomyInfo.level === null ? t("sidebar.autonomy.noData") : t("sidebar.autonomy.select")}
                    </option>
                    {AUTONOMY_LEVELS.map((level) => (
                        <option key={level} value={level}>
                            {t(`sidebar.autonomy.levels.${level}` as string) ?? `Poziom ${level}`}
                        </option>
                    ))}
                </select>
            </div>
            <p className="mt-3 text-xs text-zinc-400">{autonomyInfo.description}</p>
        </section>
    );
}
