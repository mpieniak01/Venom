"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { CheckCircle, AlertCircle, XCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n";
import type { ApplyResults, AppliedChange } from "@/types/workflow-control";

interface ApplyResultsModalProps {
  results: ApplyResults;
  onClose: () => void;
}

export function ApplyResultsModal({
  results,
  onClose,
}: Readonly<ApplyResultsModalProps>) {
  const t = useTranslation();
  const applyMode = results?.apply_mode;
  const appliedChanges = results?.applied_changes || [];
  const pendingRestart = results?.pending_restart || [];
  const failedChanges = results?.failed_changes || [];

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("workflowControl.apply.title")}</DialogTitle>
          <DialogDescription>
            {t("workflowControl.apply.description")}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-4">
          {/* Overall Status */}
          <div className="p-4 rounded-lg border">
            <div className="flex items-center gap-2 mb-2">
              {applyMode === "hot_swap" && (
                <CheckCircle className="h-5 w-5 text-green-500" />
              )}
              {applyMode === "restart_required" && (
                <AlertCircle className="h-5 w-5 text-yellow-500" />
              )}
              {applyMode === "rejected" && (
                <XCircle className="h-5 w-5 text-red-500" />
              )}
              <span className="font-semibold">
                {applyMode === "hot_swap" && t("workflowControl.apply.hotSwap")}
                {applyMode === "restart_required" && t("workflowControl.apply.restartRequired")}
                {applyMode === "rejected" && t("workflowControl.apply.rejected")}
              </span>
            </div>
            <p className="text-sm text-muted-foreground">{results?.message}</p>
          </div>

          {/* Applied Changes (Hot Swap) */}
          {appliedChanges.length > 0 && (
            <div className="space-y-2">
              <h3 className="font-semibold text-sm flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                {t("workflowControl.apply.appliedChanges", { count: appliedChanges.length })}
              </h3>
              <div className="space-y-1">
                {appliedChanges.map((change: AppliedChange) => (
                  <div
                    key={`${change.resource_type}:${change.resource_id}:${change.message}`}
                    className="p-2 rounded bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 text-sm"
                  >
                    <div className="font-mono text-xs">
                      {change.resource_type}: {change.resource_id}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {change.message}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Pending Restart */}
          {pendingRestart.length > 0 && (
            <div className="space-y-2">
              <h3 className="font-semibold text-sm flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-yellow-500" />
                {t("workflowControl.apply.pendingRestart", { count: pendingRestart.length })}
              </h3>
              <div className="space-y-1">
                {pendingRestart.map((service: string) => (
                  <div
                    key={service}
                    className="p-2 rounded bg-yellow-50 dark:bg-yellow-950 border border-yellow-200 dark:border-yellow-800 text-sm"
                  >
                    <div className="font-mono text-xs">{service}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Failed Changes */}
          {failedChanges.length > 0 && (
            <div className="space-y-2">
              <h3 className="font-semibold text-sm flex items-center gap-2">
                <XCircle className="h-4 w-4 text-red-500" />
                {t("workflowControl.apply.failedChanges", { count: failedChanges.length })}
              </h3>
              <div className="space-y-1">
                {failedChanges.map((error: string) => (
                  <div
                    key={error}
                    className="p-2 rounded bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-sm"
                  >
                    <div className="text-xs">{error}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Rollback Info */}
          {results?.rollback_available && (
            <div className="p-3 rounded bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 text-sm">
              {t("workflowControl.apply.rollback")}
            </div>
          )}
        </div>

        <div className="mt-6 flex justify-end">
          <Button onClick={onClose}>{t("workflowControl.apply.close")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
