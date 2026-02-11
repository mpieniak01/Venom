"use client";

import { useState, useEffect } from "react";
import { GraduationCap, Database, Zap, Server, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { cn } from "@/lib/utils";
import { AcademyOverview } from "./academy-overview";
import { DatasetPanel } from "./dataset-panel";
import { TrainingPanel } from "./training-panel";
import { AdaptersPanel } from "./adapters-panel";
import { getAcademyStatus, type AcademyStatus } from "@/lib/academy-api";

export function AcademyDashboard() {
  const [activeTab, setActiveTab] = useState<"overview" | "dataset" | "training" | "adapters">("overview");
  const [status, setStatus] = useState<AcademyStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadStatus();
  }, []);

  async function loadStatus() {
    try {
      setLoading(true);
      setError(null);
      const data = await getAcademyStatus();
      setStatus(data);
    } catch (err) {
      console.error("Failed to load Academy status:", err);
      setError(err instanceof Error ? err.message : "Failed to load status");
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <div className="text-zinc-400">Ładowanie Academy...</div>
      </div>
    );
  }

  if (error || !status) {
    return (
      <div className="space-y-6">
        <SectionHeading
          eyebrow="THE ACADEMY"
          title="Model Training & Fine-tuning"
          description="Autonomiczne ulepszanie modeli przez LoRA/QLoRA"
          as="h1"
          size="lg"
          rightSlot={<GraduationCap className="page-heading-icon" />}
        />
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-6">
          <p className="text-sm text-red-300">
            ❌ Academy niedostępne: {error || "Unknown error"}
          </p>
          <p className="mt-2 text-xs text-zinc-400">
            Sprawdź czy ENABLE_ACADEMY=true w konfiguracji i czy zainstalowano zależności
            (pip install -r requirements-academy.txt)
          </p>
          <Button
            onClick={loadStatus}
            variant="outline"
            size="sm"
            className="mt-4"
          >
            Spróbuj ponownie
          </Button>
        </div>
      </div>
    );
  }

  if (!status.enabled) {
    return (
      <div className="space-y-6">
        <SectionHeading
          eyebrow="THE ACADEMY"
          title="Model Training & Fine-tuning"
          description="Autonomiczne ulepszanie modeli przez LoRA/QLoRA"
          as="h1"
          size="lg"
          rightSlot={<GraduationCap className="page-heading-icon" />}
        />
        <div className="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-6">
          <p className="text-sm text-yellow-300">
            ⚠️ Academy jest wyłączone w konfiguracji
          </p>
          <p className="mt-2 text-xs text-zinc-400">
            Aby włączyć, ustaw ENABLE_ACADEMY=true w pliku .env i zrestartuj backend
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="THE ACADEMY"
        title="Model Training & Fine-tuning"
        description="Autonomiczne ulepszanie modeli przez LoRA/QLoRA"
        as="h1"
        size="lg"
        rightSlot={<GraduationCap className="page-heading-icon" />}
      />

      {/* Tabs */}
      <div className="flex gap-2 border-b border-white/10">
        <Button
          onClick={() => setActiveTab("overview")}
          variant="ghost"
          size="sm"
          className={cn(
            "gap-2 rounded-t-xl rounded-b-none px-4 py-3 text-sm font-medium",
            activeTab === "overview"
              ? "border-b-2 border-emerald-400 bg-emerald-500/10 text-emerald-300"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          )}
        >
          <Server className="h-4 w-4" />
          Przegląd
        </Button>
        <Button
          onClick={() => setActiveTab("dataset")}
          variant="ghost"
          size="sm"
          className={cn(
            "gap-2 rounded-t-xl rounded-b-none px-4 py-3 text-sm font-medium",
            activeTab === "dataset"
              ? "border-b-2 border-emerald-400 bg-emerald-500/10 text-emerald-300"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          )}
        >
          <Database className="h-4 w-4" />
          Dataset
        </Button>
        <Button
          onClick={() => setActiveTab("training")}
          variant="ghost"
          size="sm"
          className={cn(
            "gap-2 rounded-t-xl rounded-b-none px-4 py-3 text-sm font-medium",
            activeTab === "training"
              ? "border-b-2 border-emerald-400 bg-emerald-500/10 text-emerald-300"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          )}
        >
          <Play className="h-4 w-4" />
          Trening
        </Button>
        <Button
          onClick={() => setActiveTab("adapters")}
          variant="ghost"
          size="sm"
          className={cn(
            "gap-2 rounded-t-xl rounded-b-none px-4 py-3 text-sm font-medium",
            activeTab === "adapters"
              ? "border-b-2 border-emerald-400 bg-emerald-500/10 text-emerald-300"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          )}
        >
          <Zap className="h-4 w-4" />
          Adaptery
        </Button>
      </div>

      {/* Content */}
      <div className="min-h-[500px]">
        {activeTab === "overview" && <AcademyOverview status={status} onRefresh={loadStatus} />}
        {activeTab === "dataset" && <DatasetPanel status={status} />}
        {activeTab === "training" && <TrainingPanel status={status} />}
        {activeTab === "adapters" && <AdaptersPanel status={status} />}
      </div>
    </div>
  );
}
