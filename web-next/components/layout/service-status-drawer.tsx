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

type ServiceStatusDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function ServiceStatusDrawer({ open, onOpenChange }: ServiceStatusDrawerProps) {
  const { data: services } = useServiceStatus(20000);
  const serviceEntries = useMemo(() => services ?? [], [services]);

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
      <SheetContent className="flex h-full max-w-xl flex-col gap-4 border-l border-white/10 bg-zinc-950/95">
        <SheetHeader>
          <SheetTitle>Service status</SheetTitle>
          <SheetDescription>
            Aktualny stan usług systemowych z `/api/v1/system/services`.
          </SheetDescription>
        </SheetHeader>
        <div className="surface-card flex items-center justify-between gap-4 p-4 text-sm text-zinc-200">
          <div className="flex items-center gap-3">
            <ServerCog className="h-5 w-5 text-violet-300" />
            <div>
              <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Podsumowanie</p>
              <p className="text-base font-semibold text-white">
                {serviceEntries.length > 0 ? `${serviceEntries.length} usług` : "Brak danych"}
              </p>
            </div>
          </div>
          <div className="flex gap-2 text-xs">
            <Badge tone="success">{summary.healthy} healthy</Badge>
            <Badge tone="warning">{summary.degraded} degraded</Badge>
            <Badge tone="danger">{summary.down} down</Badge>
          </div>
        </div>
        <div className="flex-1 space-y-2 overflow-y-auto">
          {serviceEntries.length === 0 ? (
            <OverlayFallback
              icon={<RefreshCw className="h-4 w-4" />}
              title="Brak usług"
              description="API nie zwróciło listy usług. Sprawdź połączenie."
              hint="Service status"
              testId="service-status-offline"
            />
          ) : (
            serviceEntries.map((svc) => (
              <ListCard
                key={`${svc.name}-${svc.status}`}
                title={svc.name}
                subtitle={svc.detail ?? "Brak opisu"}
                badge={<Badge tone={toneFromStatus(svc.status)}>{svc.status}</Badge>}
              />
            ))
          )}
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
