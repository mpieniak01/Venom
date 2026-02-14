"use client";

import { Button } from "@/components/ui/button";
import {
  Pause,
  Play,
  XCircle,
  RotateCcw,
  PlayCircle,
} from "lucide-react";

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
  const canPause = workflowStatus === "running";
  const canResume = workflowStatus === "paused";
  const canCancel = ["running", "paused"].includes(workflowStatus || "");
  const canRetry = ["failed", "cancelled"].includes(workflowStatus || "");

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1">
        <div className="text-sm font-medium">Workflow Status:</div>
        <div className="text-xs text-muted-foreground">
          <span
            className={`inline-block px-2 py-1 rounded ${
              workflowStatus === "running"
                ? "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-100"
                : workflowStatus === "paused"
                  ? "bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-100"
                  : workflowStatus === "failed"
                    ? "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-100"
                    : "bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-100"
            }`}
          >
            {workflowStatus || "idle"}
          </span>
        </div>
      </div>

      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={onPause}
          disabled={!canPause || isLoading}
          title="Pause workflow"
        >
          <Pause className="h-4 w-4 mr-1" />
          Pause
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={onResume}
          disabled={!canResume || isLoading}
          title="Resume workflow"
        >
          <Play className="h-4 w-4 mr-1" />
          Resume
        </Button>

        <Button
          variant="destructive"
          size="sm"
          onClick={onCancel}
          disabled={!canCancel || isLoading}
          title="Cancel workflow"
        >
          <XCircle className="h-4 w-4 mr-1" />
          Cancel
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={onRetry}
          disabled={!canRetry || isLoading}
          title="Retry workflow"
        >
          <RotateCcw className="h-4 w-4 mr-1" />
          Retry
        </Button>

        <Button
          variant="secondary"
          size="sm"
          onClick={onDryRun}
          disabled={isLoading}
          title="Dry run (simulation)"
        >
          <PlayCircle className="h-4 w-4 mr-1" />
          Dry Run
        </Button>
      </div>
    </div>
  );
}
