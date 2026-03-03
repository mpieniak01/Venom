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
                    className="rounded border border-[color:var(--tone-success-border)] bg-[color:var(--tone-success-bg)] p-2 text-sm text-[color:var(--tone-success-text)]"
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
                    className="rounded border border-[color:var(--tone-warning-border)] bg-[color:var(--tone-warning-bg)] p-2 text-sm text-[color:var(--tone-warning-text)]"
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
                    className="rounded border border-[color:var(--tone-danger-border)] bg-[color:var(--tone-danger-bg)] p-2 text-sm text-[color:var(--tone-danger-text)]"
                  >
                    <div className="text-xs">{error}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Rollback Info */}
          {results?.rollback_available && (
            <div className="rounded border border-[color:var(--tone-info-border)] bg-[color:var(--tone-info-bg)] p-3 text-sm text-[color:var(--tone-info-text)]">
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
