"use client";

import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import type { TelemetryFeedEntry } from "@/components/cockpit/cockpit-utils";

type CockpitTelemetryPanelProps = Readonly<{
  telemetryFeed: TelemetryFeedEntry[];
}>;

export function CockpitTelemetryPanel({ telemetryFeed }: CockpitTelemetryPanelProps) {
  return (
    <Panel
      eyebrow="Live telemetry"
      title="Zdarzenia /ws/events"
      description="Najświeższe sygnały TASK_* i QUEUE_* – pozwalają śledzić napływające wyniki bez przeładowania."
    >
      {telemetryFeed.length === 0 ? (
        <p className="text-hint">Brak zdarzeń – czekam na telemetrię.</p>
      ) : (
        <div className="space-y-2">
          {telemetryFeed.map((event) => (
            <div
              key={event.id}
              className="list-row items-start gap-3 text-sm text-white"
            >
              <div>
                <p className="font-semibold">{event.type}</p>
                <p className="text-hint">{event.message}</p>
              </div>
              <div className="text-right text-xs text-zinc-500">
                <Badge tone={event.tone}>{event.timestamp}</Badge>
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
