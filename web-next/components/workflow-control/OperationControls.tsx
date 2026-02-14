"use client";

import { Button } from "@/components/ui/button";
import {
  Pause,
  Play,
  XCircle,
  RotateCcw,
  PlayCircle,
} from "lucide-react";
import { useTranslation } from "@/lib/i18n";
import { getWorkflowStatusMeta } from "@/lib/workflow-control-ui-helpers";

interface OperationControlsProps {
  workflowStatus?: string;
  onPause: () => Promise<void>;
  onResume: () => Promise<void>;
  onCancel: () => Promise<void>;
  onRetry: () => Promise<void>;
  onDryRun: () => Promise<void>;
  isLoading: boolean;
}

export function OperationControls({
  workflowStatus,
  onPause,
  onResume,
  onCancel,
  onRetry,
  onDryRun,
  isLoading,
}: OperationControlsProps) {
  const t = useTranslation();
  const statusMeta = getWorkflowStatusMeta(workflowStatus);
  const { canPause, canResume, canCancel, canRetry } = statusMeta;

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1">
        <div className="text-sm font-medium">{t("workflowControl.operations.currentStatus")}:</div>
        <div className="text-xs text-muted-foreground">
          <span
            className={`inline-block px-2 py-1 rounded ${statusMeta.colorClass}`}
          >
            {t(`workflowControl.status.${statusMeta.statusKey}`)}
          </span>
        </div>
      </div>

      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={onPause}
          disabled={!canPause || isLoading}
          title={t("workflowControl.buttons.pause")}
        >
          <Pause className="h-4 w-4 mr-1" />
          {t("workflowControl.buttons.pause")}
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={onResume}
          disabled={!canResume || isLoading}
          title={t("workflowControl.buttons.resume")}
        >
          <Play className="h-4 w-4 mr-1" />
          {t("workflowControl.buttons.resume")}
        </Button>

        <Button
          variant="danger"
          size="sm"
          onClick={onCancel}
          disabled={!canCancel || isLoading}
          title={t("workflowControl.buttons.cancel")}
        >
          <XCircle className="h-4 w-4 mr-1" />
          {t("workflowControl.buttons.cancel")}
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={onRetry}
          disabled={!canRetry || isLoading}
          title={t("workflowControl.buttons.retry")}
        >
          <RotateCcw className="h-4 w-4 mr-1" />
          {t("workflowControl.buttons.retry")}
        </Button>

        <Button
          variant="secondary"
          size="sm"
          onClick={onDryRun}
          disabled={isLoading}
          title={t("workflowControl.buttons.dryRun")}
        >
          <PlayCircle className="h-4 w-4 mr-1" />
          {t("workflowControl.buttons.dryRun")}
        </Button>
      </div>
    </div>
  );
}
