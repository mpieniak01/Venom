import { Activity, Bug, Pause, Play, RefreshCw, Square } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";
import { getStatusTone } from "@/lib/workflow-control-screen";

interface WorkflowTargetPanelProps {
  status: string;
  allowedOperations?: string[];
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
  onRetry: () => void;
  onDryRun: () => void;
  isLoading?: boolean;
}

export function WorkflowTargetPanel({
  status,
  allowedOperations = [],
  onPause,
  onResume,
  onCancel,
  onRetry,
  onDryRun,
  isLoading,
}: Readonly<WorkflowTargetPanelProps>) {
  const t = useTranslation();
  const canPause = allowedOperations.includes("pause");
  const canResume = allowedOperations.includes("resume");
  const canCancel = allowedOperations.includes("cancel");
  const canRetry = allowedOperations.includes("retry");
  const canDryRun =
    allowedOperations.includes("dry-run") || allowedOperations.includes("dry_run");

  return (
    <section className="rounded-[28px] border border-white/10 bg-slate-950/80 p-5 shadow-[0_18px_60px_rgba(2,6,23,0.45)]">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-400">
            {t("workflowControl.labels.workflowTarget")}
          </div>
          <div className="mt-2 flex items-center gap-3">
            <h2 className="text-xl font-semibold text-slate-100">
              {t("workflowControl.operations.title")}
            </h2>
            <Badge tone={getStatusTone(status)}>{status}</Badge>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 lg:flex lg:flex-wrap">
          {canResume ? (
            <Button size="sm" variant="secondary" onClick={onResume} disabled={isLoading}>
              <Play className="h-3.5 w-3.5" />
              {t("workflowControl.actions.resume")}
            </Button>
          ) : (
            <Button
              size="sm"
              variant="amber"
              onClick={onPause}
              disabled={isLoading || !canPause}
            >
              <Pause className="h-3.5 w-3.5" />
              {t("workflowControl.actions.pause")}
            </Button>
          )}
          <Button
            size="sm"
            variant="danger"
            onClick={onCancel}
            disabled={isLoading || !canCancel}
          >
            <Square className="h-3.5 w-3.5" />
            {t("workflowControl.actions.stop")}
          </Button>
          {canRetry && (
            <Button size="sm" variant="primary" onClick={onRetry} disabled={isLoading}>
              <RefreshCw className="h-3.5 w-3.5" />
              {t("workflowControl.actions.retry")}
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={onDryRun}
            disabled={isLoading || !canDryRun}
          >
            <Bug className="h-3.5 w-3.5" />
            {t("workflowControl.actions.dryRun")}
          </Button>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2 text-xs text-slate-400">
        <Activity className="h-4 w-4 text-cyan-400" />
        <span>{t("workflowControl.messages.workflowTargetHint")}</span>
      </div>
    </section>
  );
}
