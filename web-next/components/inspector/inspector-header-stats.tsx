"use client";

import { SectionHeading } from "@/components/ui/section-heading";
import { Badge } from "@/components/ui/badge";
import { LatencyCard } from "@/components/inspector/lag-card";
import { HeroStat } from "@/components/inspector/hero-stat";
import { Activity, BugPlay, Layers, Radar, TimerReset } from "lucide-react";

type Translator = (key: string, params?: Record<string, string | number>) => string;

type Props = {
  t: Translator;
  inspectorStats: {
    successRate: number;
    completed: number;
    total: number;
    processing: number;
    avgDuration: number | null;
    activeTasks: number;
  };
  taskBreakdown: Array<{ status: string; count: number }>;
  latencyCards: Array<{ label: string; value: string; hint: string }>;
};

export function InspectorHeaderStats({ t, inspectorStats, taskBreakdown, latencyCards }: Props) {
  return (
    <>
      <SectionHeading
        eyebrow={t("inspector.page.eyebrow")}
        title={t("inspector.page.title")}
        description={t("inspector.page.description")}
        as="h1"
        size="lg"
        rightSlot={
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex flex-wrap gap-2 text-xs">
              <Badge tone="neutral">/api/v1/history/requests</Badge>
              <Badge tone="neutral">/api/v1/tasks</Badge>
              <Badge tone="neutral">/history/requests/:id</Badge>
            </div>
            <BugPlay className="page-heading-icon" />
          </div>
        }
      />

      <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <HeroStat
          icon={<Activity className="h-4 w-4 text-emerald-300" />}
          label={t("inspector.stats.successRate")}
          primary={`${inspectorStats.successRate}%`}
          hint={t("inspector.stats.completed", { count: inspectorStats.completed })}
        />
        <HeroStat
          icon={<Layers className="h-4 w-4 text-violet-300" />}
          label={t("inspector.stats.history")}
          primary={inspectorStats.total.toString()}
          hint={t("inspector.stats.activeTracing", { count: inspectorStats.processing })}
        />
        <HeroStat
          icon={<TimerReset className="h-4 w-4 text-sky-300" />}
          label={t("inspector.stats.avgDuration")}
          primary={latencyCards[0]?.value ?? "—"}
          hint={t("inspector.stats.last50")}
        />
        <HeroStat
          icon={<Radar className="h-4 w-4 text-indigo-300" />}
          label={t("inspector.stats.activeTasks")}
          primary={inspectorStats.activeTasks.toString()}
          hint={t("inspector.stats.processing", { count: taskBreakdown.find((b) => b.status === "PROCESSING")?.count ?? 0 })}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {latencyCards.map((card) => (
          <LatencyCard key={card.label} label={card.label} value={card.value} hint={card.hint} />
        ))}
      </div>
    </>
  );
}
