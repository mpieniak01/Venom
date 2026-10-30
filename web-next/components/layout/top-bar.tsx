"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import dynamic from "next/dynamic";
import { Sparkles, BellRing, Cpu, Command as CommandIcon, Rows, ServerCog } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { MobileNav } from "./mobile-nav";
import { StatusPills, type StatusPillsInitialData } from "./status-pills";
import { LanguageSwitcher } from "./language-switcher";
import { ThemeSwitcher } from "./theme-switcher";
import { ModelIntrospectionMechanismControl } from "@/components/inspector/model-introspection-mechanism";
import { useTranslation } from "@/lib/i18n";

const CommandCenter = dynamic(() => import("./command-center").then((module) => module.CommandCenter));
const AlertCenter = dynamic(() => import("./alert-center").then((module) => module.AlertCenter));
const QuickActions = dynamic(() => import("./quick-actions").then((module) => module.QuickActions));
const CommandPalette = dynamic(() => import("./command-palette").then((module) => module.CommandPalette));
const NotificationDrawer = dynamic(() => import("./notification-drawer").then((module) => module.NotificationDrawer));
const ServiceStatusDrawer = dynamic(() => import("./service-status-drawer").then((module) => module.ServiceStatusDrawer));

function useDeferredPanel() {
  const [state, setState] = useState({ open: false, mounted: false });
  const onOpenChange = useCallback((open: boolean) => {
    setState((previous) => ({ open, mounted: previous.mounted || open }));
  }, []);
  return [state.open, state.mounted, onOpenChange] as const;
}

export function TopBar({ initialStatusData }: Readonly<{ initialStatusData?: StatusPillsInitialData }>) {
  const [commandOpen, commandMounted, setCommandOpen] = useDeferredPanel();
  const [alertsOpen, alertsMounted, setAlertsOpen] = useDeferredPanel();
  const [actionsOpen, actionsMounted, setActionsOpen] = useDeferredPanel();
  const [paletteOpen, paletteMounted, setPaletteOpen] = useDeferredPanel();
  const [notificationsOpen, notificationsMounted, setNotificationsOpen] = useDeferredPanel();
  const [servicesOpen, servicesMounted, setServicesOpen] = useDeferredPanel();
  const commandButtonRef = useRef<HTMLButtonElement | null>(null);
  const alertsButtonRef = useRef<HTMLButtonElement | null>(null);
  const actionsButtonRef = useRef<HTMLButtonElement | null>(null);
  const notificationsButtonRef = useRef<HTMLButtonElement | null>(null);
  const servicesButtonRef = useRef<HTMLButtonElement | null>(null);
  const t = useTranslation();

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
    };
    globalThis.window.addEventListener("keydown", handler);
    return () => globalThis.window.removeEventListener("keydown", handler);
  }, [setPaletteOpen]);

  return (
    <div className="glass-panel allow-overflow sticky top-0 z-30 border-b border-[color:var(--ui-border)] bg-[color:var(--topbar-bg)] px-4 py-4 backdrop-blur-2xl sm:px-6">
      <div className="mr-auto flex w-full flex-wrap max-w-[1320px] items-center justify-between gap-6 2xl:max-w-[68vw]">
        <div className="flex items-center gap-3">
          <MobileNav />
        </div>
        <div className="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-4">
          <StatusPills initialData={initialStatusData} />
          <ModelIntrospectionMechanismControl variant="compact" />
          <TopBarIconAction
            icon={<BellRing className="h-4 w-4 text-amber-300" />}
            label={t("topBar.alertCenter")}
            onClick={() => setAlertsOpen(true)}
            testId="topbar-alerts"
            buttonRef={alertsButtonRef}
          />
          <TopBarIconAction
            icon={<Rows className="h-4 w-4 text-emerald-300" />}
            label={t("topBar.notifications")}
            onClick={() => setNotificationsOpen(true)}
            hidden="mobile"
            testId="topbar-notifications"
            buttonRef={notificationsButtonRef}
          />
          <TopBarIconAction
            icon={<CommandIcon className="h-4 w-4 text-[color:var(--text-primary)]" />}
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
            buttonRef={actionsButtonRef}
          />
          <TopBarIconAction
            icon={<ServerCog className="h-4 w-4 text-indigo-300" />}
            label={t("topBar.services")}
            onClick={() => setServicesOpen(true)}
            hidden="mobile"
            testId="topbar-services"
            buttonRef={servicesButtonRef}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCommandOpen(true)}
            data-testid="topbar-command-center"
            ref={commandButtonRef}
          >
            <Sparkles className="h-4 w-4 text-violet-300" />
            <span className="text-xs uppercase tracking-wider" suppressHydrationWarning>
              {t("topBar.commandCenter")}
            </span>
          </Button>
          <ThemeSwitcher />
          <LanguageSwitcher />
        </div>
      </div>
      {commandMounted && <CommandCenter open={commandOpen} onOpenChange={setCommandOpen} returnFocusRef={commandButtonRef} />}
      {alertsMounted && <AlertCenter open={alertsOpen} onOpenChange={setAlertsOpen} returnFocusRef={alertsButtonRef} />}
      {actionsMounted && <QuickActions open={actionsOpen} onOpenChange={setActionsOpen} returnFocusRef={actionsButtonRef} />}
      {paletteMounted && <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        onOpenQuickActions={() => setActionsOpen(true)}
      />}
      {notificationsMounted && <NotificationDrawer open={notificationsOpen} onOpenChange={setNotificationsOpen} returnFocusRef={notificationsButtonRef} />}
      {servicesMounted && <ServiceStatusDrawer open={servicesOpen} onOpenChange={setServicesOpen} returnFocusRef={servicesButtonRef} />}
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
  buttonRef,
}: Readonly<{
  label: string;
  icon: ReactNode;
  onClick: () => void;
  hidden?: TopBarActionVisibility;
  testId?: string;
  buttonRef?: React.RefObject<HTMLButtonElement | null>;
}>) {
  const displayClass = (() => {
    if (hidden === "desktop") return "lg:hidden";
    if (hidden === "mobile") return "hidden lg:inline-flex";
    return "flex"; // Default to "flex" if not hidden
  })();

  return (
    <Button
      type="button"
      onClick={onClick}
      data-testid={testId}
      ref={buttonRef}
      variant="outline"
      size="sm"
      className={cn(
        "relative p-2.5 transition-colors hover:bg-[color:var(--button-outline-hover)]",
        displayClass,
      )}
    >
      {icon}
      <span className="hidden md:inline-flex" suppressHydrationWarning>{label}</span>
    </Button>
  );
}
