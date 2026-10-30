"use client";

import { useMemo } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useServiceStatus } from "@/hooks/use-api";
import { ListCard } from "@/components/ui/list-card";
import { Badge } from "@/components/ui/badge";
import { ServerCog, RefreshCw } from "lucide-react";
import { OverlayFallback } from "./overlay-fallback";
import { useTranslation } from "@/lib/i18n";

type ServiceStatusDrawerProps = Readonly<{
  open: boolean;
  onOpenChange: (open: boolean) => void;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
}>;

export function ServiceStatusDrawer({ open, onOpenChange, returnFocusRef }: ServiceStatusDrawerProps) {
  const { data: services } = useServiceStatus(20000, open);
  const serviceEntries = useMemo(() => services ?? [], [services]);
  const servicesOffline = !serviceEntries || serviceEntries.length === 0;
  const t = useTranslation();

  const summary = useMemo(() => serviceEntries.reduce(
    (acc, service) => {
      acc[classifyServiceStatus(service.status)] += 1;
      return acc;
    },
    { healthy: 0, degraded: 0, down: 0, unknown: 0 },
  ), [serviceEntries]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        returnFocusRef={returnFocusRef}
        data-testid="service-status-drawer"
        className="glass-panel flex h-full max-w-xl flex-col gap-4 border-l border-[color:var(--ui-border)] bg-[color:var(--bg-panel)] text-[color:var(--text-primary)]"
      >
        <SheetHeader>
          <SheetTitle>{t("serviceStatus.title")}</SheetTitle>
          <SheetDescription>{t("serviceStatus.description")}</SheetDescription>
        </SheetHeader>
        <div className="surface-card flex items-center justify-between gap-4 p-4 text-sm text-[color:var(--text-primary)]">
          <div className="flex items-center gap-3">
            <ServerCog className="h-5 w-5 text-violet-300" />
            <div>
              <p className="eyebrow">
                {t("serviceStatus.summary")}
              </p>
              <p className="text-base font-semibold text-[color:var(--text-heading)]">
                {serviceEntries.length > 0
                  ? t("serviceStatus.servicesCount", { count: serviceEntries.length })
                  : t("serviceStatus.noData")}
              </p>
            </div>
          </div>
          <div className="flex gap-2 text-xs" data-testid="service-status-summary">
            <Badge tone="success">
              {t("serviceStatus.badges.healthy", { count: summary.healthy })}
            </Badge>
            <Badge tone="warning">
              {t("serviceStatus.badges.degraded", { count: summary.degraded })}
            </Badge>
            <Badge tone="danger">
              {t("serviceStatus.badges.down", { count: summary.down })}
            </Badge>
            {summary.unknown > 0 && <Badge tone="neutral">{t("common.unknown")}: {summary.unknown}</Badge>}
          </div>
        </div>
        <div className="flex-1 space-y-2 overflow-y-auto">
          {servicesOffline && (
            <OverlayFallback
              icon={<RefreshCw className="h-4 w-4" />}
              title={t("serviceStatus.offlineTitle")}
              description={t("serviceStatus.offlineDescription")}
              hint={t("serviceStatus.hint")}
              testId="service-status-offline"
            />
          )}
          {!servicesOffline &&
            serviceEntries.map((svc) => (
              <ListCard
                key={`${svc.name}-${svc.status}`}
                title={svc.name}
                subtitle={svc.detail ?? t("common.noDescription")}
                badge={<Badge tone={toneFromStatus(svc.status)}>{svc.status}</Badge>}
              />
            ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function classifyServiceStatus(status?: string): "healthy" | "degraded" | "down" | "unknown" {
  switch (status?.trim().toLowerCase()) {
    case "online":
    case "healthy":
      return "healthy";
    case "degraded":
    case "warn":
    case "warning":
      return "degraded";
    case "offline":
    case "unhealthy":
    case "down":
    case "error":
      return "down";
    default:
      return "unknown";
  }
}

function toneFromStatus(status?: string) {
  const category = classifyServiceStatus(status);
  if (category === "healthy") return "success" as const;
  if (category === "degraded") return "warning" as const;
  if (category === "down") return "danger" as const;
  return "neutral" as const;
}
