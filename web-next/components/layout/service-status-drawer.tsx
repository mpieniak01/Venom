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

type ServiceStatusDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function ServiceStatusDrawer({ open, onOpenChange }: ServiceStatusDrawerProps) {
  const { data: services } = useServiceStatus(20000);
  const serviceEntries = useMemo(() => services ?? [], [services]);
  const servicesOffline = !serviceEntries || serviceEntries.length === 0;
  const t = useTranslation();

  const summary = useMemo(() => {
    if (!serviceEntries.length) {
      return {
        healthy: 0,
        degraded: 0,
        down: 0,
      };
    }
    return serviceEntries.reduce(
      (acc, svc) => {
        const status = (svc.status || "").toLowerCase();
        if (status.includes("healthy")) acc.healthy += 1;
        else if (status.includes("degraded")) acc.degraded += 1;
        else acc.down += 1;
        return acc;
      },
      { healthy: 0, degraded: 0, down: 0 },
    );
  }, [serviceEntries]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        data-testid="service-status-drawer"
        className="flex h-full max-w-xl flex-col gap-4 border-l border-white/10 bg-zinc-950/95"
      >
        <SheetHeader>
          <SheetTitle>{t("serviceStatus.title")}</SheetTitle>
          <SheetDescription>{t("serviceStatus.description")}</SheetDescription>
        </SheetHeader>
        <div className="surface-card flex items-center justify-between gap-4 p-4 text-sm text-zinc-200">
          <div className="flex items-center gap-3">
            <ServerCog className="h-5 w-5 text-violet-300" />
            <div>
              <p className="eyebrow">
                {t("serviceStatus.summary")}
              </p>
              <p className="text-base font-semibold text-white">
                {serviceEntries.length > 0
                  ? t("serviceStatus.servicesCount", { count: serviceEntries.length })
                  : t("serviceStatus.noData")}
              </p>
            </div>
          </div>
          <div className="flex gap-2 text-xs">
            <Badge tone="success">
              {t("serviceStatus.badges.healthy", { count: summary.healthy })}
            </Badge>
            <Badge tone="warning">
              {t("serviceStatus.badges.degraded", { count: summary.degraded })}
            </Badge>
            <Badge tone="danger">
              {t("serviceStatus.badges.down", { count: summary.down })}
            </Badge>
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

function toneFromStatus(status?: string) {
  if (!status) return "neutral" as const;
  const value = status.toLowerCase();
  if (value.includes("healthy") || value.includes("online")) return "success" as const;
  if (value.includes("degraded") || value.includes("warn")) return "warning" as const;
  if (value.includes("down") || value.includes("error")) return "danger" as const;
  return "neutral" as const;
}
