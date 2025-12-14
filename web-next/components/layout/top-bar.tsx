"use client";

import { useEffect, useState, type ReactNode } from "react";
import { WifiOff, Wifi, Sparkles, BellRing, Cpu, Command as CommandIcon, Rows } from "lucide-react";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import { setCostMode, useCostMode } from "@/hooks/use-api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { CommandCenter } from "./command-center";
import { AlertCenter } from "./alert-center";
import { MobileNav } from "./mobile-nav";
import { StatusPills } from "./status-pills";
import { QuickActions } from "./quick-actions";
import { CommandPalette } from "./command-palette";
import { NotificationDrawer } from "./notification-drawer";

export function TopBar() {
  const { connected } = useTelemetryFeed();
  const { data: costMode, refresh: refreshCost } = useCostMode(10000);
  const [updating, setUpdating] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);

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

  const toggleMode = async () => {
    if (updating) return;
    setUpdating(true);
    try {
      await setCostMode(!(costMode?.enabled ?? false));
      refreshCost();
    } catch (error) {
      console.error(error);
    } finally {
      setUpdating(false);
    }
  };

  const proEnabled = costMode?.enabled ?? false;

  return (
    <div className="sticky top-0 z-30 flex items-center justify-between border-b border-white/5 bg-gradient-to-r from-zinc-950/95 to-zinc-900/30 px-6 py-4 backdrop-blur-xl">
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
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">WS</p>
          <p className="flex items-center gap-2 text-sm font-semibold text-white">
            {connected ? (
              <>
                <Wifi className="h-3.5 w-3.5 text-emerald-400" /> Połączono
              </>
            ) : (
              <>
                <WifiOff className="h-3.5 w-3.5 text-rose-400" /> Offline
              </>
            )}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <StatusPills />
        <TopBarIconAction icon={<BellRing className="h-4 w-4 text-amber-300" />} label="Alert center" onClick={() => setAlertsOpen(true)} />
        <TopBarIconAction
          icon={<Rows className="h-4 w-4 text-emerald-300" />}
          label="Notifications"
          onClick={() => setNotificationsOpen(true)}
          hidden="mobile"
        />
        <TopBarIconAction
          icon={<CommandIcon className="h-4 w-4 text-zinc-200" />}
          label="Command ⌘K"
          onClick={() => setPaletteOpen(true)}
          hidden="mobile"
        />
        <TopBarIconAction
          icon={<Cpu className="h-4 w-4 text-sky-300" />}
          label="Quick actions"
          onClick={() => setActionsOpen(true)}
          hidden="mobile"
        />
        <Button variant="outline" size="sm" onClick={() => setCommandOpen(true)}>
          <Sparkles className="h-4 w-4 text-violet-300" />
          <span className="text-xs uppercase tracking-wider">Command Center</span>
        </Button>
        <div className="text-right">
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
            MODE
          </p>
          <p className="text-sm font-semibold text-white">
            {proEnabled ? "Pro" : "Eco"}
          </p>
        </div>
        <Button
          onClick={toggleMode}
          disabled={updating}
          variant={proEnabled ? "primary" : "outline"}
          size="sm"
        >
          <span className="text-xs uppercase tracking-wider">
            {proEnabled ? "Switch to Eco" : "Switch to Pro"}
          </span>
        </Button>
      </div>
      <CommandCenter open={commandOpen} onOpenChange={setCommandOpen} />
      <AlertCenter open={alertsOpen} onOpenChange={setAlertsOpen} />
      <QuickActions open={actionsOpen} onOpenChange={setActionsOpen} />
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <NotificationDrawer open={notificationsOpen} onOpenChange={setNotificationsOpen} />
    </div>
  );
}

type TopBarActionVisibility = "desktop" | "mobile" | "always";

function TopBarIconAction({
  label,
  icon,
  onClick,
  hidden,
}: {
  label: string;
  icon: ReactNode;
  onClick: () => void;
  hidden?: TopBarActionVisibility;
}) {
  const visibilityClass =
    hidden === "desktop"
      ? "hidden md:flex"
      : hidden === "mobile"
        ? "md:hidden"
        : "flex";

  return (
    <div className={cn("items-center gap-2 text-xs uppercase tracking-wider text-white", visibilityClass)}>
      <IconButton label={label} icon={icon} variant="outline" size="sm" onClick={onClick} className="p-0" />
      <span className="hidden md:inline-flex">{label}</span>
    </div>
  );
}
