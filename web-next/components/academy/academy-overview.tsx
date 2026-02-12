"use client";

import { RefreshCw, CheckCircle2, XCircle, AlertCircle, Cpu, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { AcademyStatus } from "@/lib/academy-api";

interface AcademyOverviewProps {
  readonly status: AcademyStatus;
  readonly onRefresh: () => void;
}

interface ComponentStatusProps {
  readonly name: string;
  readonly active: boolean;
}

const ComponentStatus = ({ name, active }: Readonly<ComponentStatusProps>) => (
  <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 p-3">
    {active ? (
      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
    ) : (
      <XCircle className="h-4 w-4 text-red-400" />
    )}
    <span className="text-sm text-zinc-300">{name}</span>
  </div>
);

interface StatCardProps {
  readonly label: string;
  readonly value: string | number;
  readonly icon: React.ElementType;
  readonly color?: "emerald" | "blue" | "yellow" | "red";
}

const StatCard = ({ label, value, icon: Icon, color = "emerald" }: Readonly<StatCardProps>) => {
  const colorClasses = {
    emerald: "border-emerald-500/20 bg-emerald-500/5 text-emerald-300",
    blue: "border-blue-500/20 bg-blue-500/5 text-blue-300",
    yellow: "border-yellow-500/20 bg-yellow-500/5 text-yellow-300",
    red: "border-red-500/20 bg-red-500/5 text-red-300",
  };

  return (
    <div className={`rounded-xl border p-4 ${colorClasses[color]}`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs opacity-70">{label}</p>
          <p className="mt-1 text-2xl font-bold">{value}</p>
        </div>
        <Icon className="h-5 w-5 opacity-50" />
      </div>
    </div>
  );
};

export function AcademyOverview({ status, onRefresh }: Readonly<AcademyOverviewProps>) {
  return (
    <div className="space-y-6">
      {/* Status nagłówek */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Status Academy</h2>
          <p className="text-sm text-zinc-400">Komponent do trenowania i fine-tuningu modeli</p>
        </div>
        <Button onClick={onRefresh} variant="outline" size="sm" className="gap-2">
          <RefreshCw className="h-4 w-4" />
          Odśwież
        </Button>
      </div>

      {/* GPU Status */}
      <div className={`rounded-xl border p-4 ${
        status.gpu.available
          ? "border-emerald-500/20 bg-emerald-500/5"
          : "border-yellow-500/20 bg-yellow-500/5"
      }`}>
        <div className="flex items-center gap-3">
          <Cpu className={`h-6 w-6 ${
            status.gpu.available ? "text-emerald-400" : "text-yellow-400"
          }`} />
          <div>
            <p className="font-medium text-white">
              {status.gpu.available ? "GPU dostępne" : "GPU niedostępne"}
            </p>
            <p className="text-sm text-zinc-400">
              {status.gpu.enabled
                ? "GPU włączone w konfiguracji"
                : "GPU wyłączone w konfiguracji (CPU fallback)"}
            </p>
          </div>
        </div>
      </div>

      {/* Statystyki */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Lessons Store"
          value={status.lessons.total_lessons || 0}
          icon={Database}
          color="blue"
        />
        <StatCard
          label="Wszystkie joby"
          value={status.jobs.total}
          icon={Database}
          color="emerald"
        />
        <StatCard
          label="W trakcie"
          value={status.jobs.running}
          icon={AlertCircle}
          color="yellow"
        />
        <StatCard
          label="Zakończone"
          value={status.jobs.finished}
          icon={CheckCircle2}
          color="emerald"
        />
      </div>

      {/* Komponenty */}
      <div>
        <h3 className="mb-3 text-sm font-medium text-zinc-300">Komponenty Academy</h3>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
          <ComponentStatus name="Professor" active={status.components.professor} />
          <ComponentStatus name="DatasetCurator" active={status.components.dataset_curator} />
          <ComponentStatus name="GPUHabitat" active={status.components.gpu_habitat} />
          <ComponentStatus name="LessonsStore" active={status.components.lessons_store} />
          <ComponentStatus name="ModelManager" active={status.components.model_manager} />
        </div>
      </div>

      {/* Konfiguracja */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-6">
        <h3 className="mb-4 text-sm font-medium text-zinc-300">Konfiguracja</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-zinc-400">Minimum lekcji</p>
            <p className="mt-1 text-lg font-semibold text-white">{status.config.min_lessons}</p>
          </div>
          <div>
            <p className="text-xs text-zinc-400">Interwał treningowy</p>
            <p className="mt-1 text-lg font-semibold text-white">{status.config.training_interval_hours}h</p>
          </div>
          <div>
            <p className="text-xs text-zinc-400">Model bazowy</p>
            <p className="mt-1 text-sm font-mono text-white">{status.config.default_base_model}</p>
          </div>
        </div>
      </div>

      {/* Ostrzeżenia */}
      {status.jobs.failed > 0 && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-red-400" />
            <p className="text-sm text-red-300">
              {status.jobs.failed} {status.jobs.failed === 1 ? "job zakończył" : "joby zakończyły"} się błędem.
              Sprawdź logi w zakładce &quot;Trening&quot;.
            </p>
          </div>
        </div>
      )}

      {!status.gpu.available && status.gpu.enabled && (
        <div className="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-4">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-yellow-400" />
            <div>
              <p className="text-sm text-yellow-300">
                GPU jest włączone w konfiguracji, ale niedostępne
              </p>
              <p className="mt-1 text-xs text-zinc-400">
                Sprawdź czy zainstalowano nvidia-container-toolkit i czy Docker ma dostęp do GPU
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
