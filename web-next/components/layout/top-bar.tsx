"use client";

import { useEffect, useState, type ReactNode } from "react";
import { WifiOff, Wifi, Sparkles, BellRing, Cpu, Command as CommandIcon, Rows, ServerCog } from "lucide-react";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { CommandCenter } from "./command-center";
import { AlertCenter } from "./alert-center";
import { MobileNav } from "./mobile-nav";
import { StatusPills } from "./status-pills";
import { QuickActions } from "./quick-actions";
import { CommandPalette } from "./command-palette";
import { NotificationDrawer } from "./notification-drawer";
import { ServiceStatusDrawer } from "./service-status-drawer";
import { LanguageSwitcher } from "./language-switcher";
import { useTranslation } from "@/lib/i18n";

export function TopBar() {
  const { connected } = useTelemetryFeed();
  const [commandOpen, setCommandOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [servicesOpen, setServicesOpen] = useState(false);
  const t = useTranslation();

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <div className="glass-panel allow-overflow sticky top-0 z-30 flex items-center justify-between border-b border-white/5 bg-black/40 px-6 py-4 backdrop-blur-2xl">
      <div className="flex items-center gap-3">
        <MobileNav />
        <span
          className={cn(
            "relative h-3 w-3 rounded-full",
            connected ? "bg-emerald-400" : "bg-rose-500",
          )}
        >
          <span
            className={cn(
              "absolute inset-0 rounded-full",
              connected ? "animate-[pulse_2s_ease-in-out_infinite]" : "",
            )}
          />
        </span>
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
            {t("topBar.wsLabel")}
          </p>
          <p className="flex items-center gap-2 text-sm font-semibold text-white">
            {connected ? (
              <>
                <Wifi className="h-3.5 w-3.5 text-emerald-400" /> {t("topBar.connected")}
              </>
            ) : (
              <>
                <WifiOff className="h-3.5 w-3.5 text-rose-400" /> {t("topBar.offline")}
              </>
            )}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <StatusPills />
        <TopBarIconAction
          icon={<BellRing className="h-4 w-4 text-amber-300" />}
          label={t("topBar.alertCenter")}
          onClick={() => setAlertsOpen(true)}
          testId="topbar-alerts"
        />
        <TopBarIconAction
          icon={<Rows className="h-4 w-4 text-emerald-300" />}
          label={t("topBar.notifications")}
          onClick={() => setNotificationsOpen(true)}
          hidden="mobile"
          testId="topbar-notifications"
        />
        <TopBarIconAction
          icon={<CommandIcon className="h-4 w-4 text-zinc-200" />}
          label={t("topBar.commandPalette")}
          onClick={() => setPaletteOpen(true)}
          hidden="mobile"
          testId="topbar-command"
        />
        <TopBarIconAction
          icon={<Cpu className="h-4 w-4 text-sky-300" />}
          label={t("topBar.quickActions")}
          onClick={() => setActionsOpen(true)}
          hidden="mobile"
          testId="topbar-quick-actions"
        />
        <TopBarIconAction
          icon={<ServerCog className="h-4 w-4 text-indigo-300" />}
          label={t("topBar.services")}
          onClick={() => setServicesOpen(true)}
          hidden="mobile"
          testId="topbar-services"
        />
        <Button
          variant="outline"
          size="sm"
          onClick={() => setCommandOpen(true)}
          data-testid="topbar-command-center"
        >
          <Sparkles className="h-4 w-4 text-violet-300" />
          <span className="text-xs uppercase tracking-wider">
            {t("topBar.commandCenter")}
          </span>
        </Button>
        <LanguageSwitcher />
      </div>
      <CommandCenter open={commandOpen} onOpenChange={setCommandOpen} />
      <AlertCenter open={alertsOpen} onOpenChange={setAlertsOpen} />
      <QuickActions open={actionsOpen} onOpenChange={setActionsOpen} />
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        onOpenQuickActions={() => setActionsOpen(true)}
      />
      <NotificationDrawer open={notificationsOpen} onOpenChange={setNotificationsOpen} />
      <ServiceStatusDrawer open={servicesOpen} onOpenChange={setServicesOpen} />
    </div>
  );
}

type TopBarActionVisibility = "desktop" | "mobile" | "always";

function TopBarIconAction({
  label,
  icon,
  onClick,
  hidden,
  testId,
}: {
  label: string;
  icon: ReactNode;
  onClick: () => void;
  hidden?: TopBarActionVisibility;
  testId?: string;
}) {
  const visibilityClass =
    hidden === "desktop"
      ? "md:hidden"
      : hidden === "mobile"
        ? "hidden md:flex"
        : "flex";

  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={cn(
        "flex items-center gap-2 rounded-full border border-white/10 px-3 py-2 text-xs uppercase tracking-wider text-white transition hover:border-white/40 hover:bg-white/5 focus:outline-none focus:ring-2 focus:ring-emerald-400",
        visibilityClass,
      )}
    >
      {icon}
      <span className="hidden md:inline-flex">{label}</span>
    </button>
  );
}
