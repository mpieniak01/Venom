import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { useTranslation } from "@/lib/i18n";
import { getStatusTone } from "@/lib/workflow-control-screen";

interface WorkflowHeaderProps {
  hasChanges: boolean;
  hasPendingPlan: boolean;
  changedDomainCount?: number;
  compatibilityIssues?: string[];
  onPlanRequest: () => void;
  onApplyRequest: () => void;
  onDiscardPlan: () => void;
  onReset: () => void;
  isLoading?: boolean;
  activeRequestId?: string | null;
  activeTaskStatus?: string | null;
  workflowStatus?: string | null;
  llmRuntimeId?: string | null;
  llmProvider?: string | null;
  llmModel?: string | null;
}

type StatusRailItemProps = {
  label: string;
  value: string;
  tone: "success" | "warning" | "danger" | "neutral";
};

type ContextChipProps = {
  label: string;
  value: string | null | undefined;
  tone?: "success" | "warning" | "danger" | "neutral";
};

function ContextChip({ label, value, tone = "neutral" }: Readonly<ContextChipProps>) {
  if (!value) return null;
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/70 px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
        {label}
      </div>
      <div className="mt-1 flex items-center gap-2">
        <Badge tone={tone} className="px-2 py-0.5 text-[10px]">
          {value}
        </Badge>
      </div>
    </div>
  );
}

function StatusRailItem({ label, value, tone }: Readonly<StatusRailItemProps>) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/60 px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
        {label}
      </div>
      <div className="mt-2">
        <Badge tone={tone}>{value}</Badge>
      </div>
    </div>
  );
}

export function WorkflowHeader({
  hasChanges,
  hasPendingPlan,
  changedDomainCount = 0,
  compatibilityIssues = [],
  onPlanRequest,
  onApplyRequest,
  onDiscardPlan,
  onReset,
  isLoading,
  activeRequestId,
  activeTaskStatus,
  workflowStatus,
  llmRuntimeId,
  llmProvider,
  llmModel,
}: Readonly<WorkflowHeaderProps>) {
  const t = useTranslation();
  const statusTone = getStatusTone(workflowStatus);
  const showStatusRail = hasChanges || hasPendingPlan || compatibilityIssues.length > 0;
  let draftStateValue = t("workflowControl.status.idle");
  let draftStateTone: StatusRailItemProps["tone"] = "neutral";
  if (hasPendingPlan) {
    draftStateValue = t("workflowControl.status.planReady");
    draftStateTone = "success";
  } else if (hasChanges) {
    draftStateValue = t("workflowControl.status.draft");
    draftStateTone = "warning";
  }

  return (
    <div className="border-b border-white/10 bg-[linear-gradient(90deg,rgba(15,23,42,0.98),rgba(8,47,73,0.95),rgba(15,23,42,0.98))] px-6 py-5">
      <div className="flex flex-col gap-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <SectionHeading
            eyebrow={t("workflowControl.eyebrow")}
            title={t("workflowControl.title")}
            description={t("workflowControl.description")}
            size="lg"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onReset}
              disabled={isLoading || (!hasChanges && !hasPendingPlan)}
            >
              {t("workflowControl.actions.reset")}
            </Button>
            {hasPendingPlan ? (
              <>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={onDiscardPlan}
                  disabled={isLoading}
                >
                  {t("workflowControl.actions.discard")}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  onClick={onApplyRequest}
                  disabled={isLoading}
                >
                  {t("workflowControl.actions.apply")}
                </Button>
              </>
            ) : (
              <Button
                type="button"
                size="sm"
                onClick={onPlanRequest}
                disabled={isLoading || !hasChanges || compatibilityIssues.length > 0}
              >
                {t("workflowControl.actions.planChanges")}
              </Button>
            )}
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
          <ContextChip
            label={t("workflowControl.labels.requestId")}
            value={activeRequestId}
          />
          <ContextChip
            label={t("workflowControl.labels.taskStatus")}
            value={activeTaskStatus}
            tone={getStatusTone(activeTaskStatus)}
          />
          <ContextChip
            label={t("workflowControl.labels.systemStatus")}
            value={workflowStatus}
            tone={statusTone}
          />
          <ContextChip
            label={t("workflowControl.labels.runtimeId")}
            value={llmRuntimeId}
          />
          <ContextChip
            label={t("workflowControl.labels.provider")}
            value={llmProvider}
          />
          <ContextChip
            label={t("workflowControl.labels.model")}
            value={llmModel}
          />
        </div>

        {showStatusRail && (
          <div className="grid gap-3 lg:grid-cols-3">
            <StatusRailItem
              label={t("workflowControl.labels.draftState")}
              value={draftStateValue}
              tone={draftStateTone}
            />
            <StatusRailItem
              label={t("workflowControl.labels.changedDomains")}
              value={String(changedDomainCount)}
              tone={changedDomainCount > 0 ? "warning" : "neutral"}
            />
            <StatusRailItem
              label={t("workflowControl.labels.compatibilityState")}
              value={
                compatibilityIssues.length > 0
                  ? t("workflowControl.status.blocked")
                  : t("workflowControl.status.aligned")
              }
              tone={compatibilityIssues.length > 0 ? "danger" : "success"}
            />
          </div>
        )}

        {hasPendingPlan && (
          <div className="flex items-start justify-between gap-4 rounded-2xl border border-emerald-400/30 bg-emerald-500/10 px-4 py-3">
            <div>
              <div className="text-sm font-semibold text-emerald-100">
                {t("workflowControl.actions.planReady")}
              </div>
              <div className="text-xs text-emerald-200/80">
                {t("workflowControl.actions.planReadyHint")}
              </div>
            </div>
            <Badge tone="success" className="shrink-0">
              {t("workflowControl.status.planReady")}
            </Badge>
          </div>
        )}

        {compatibilityIssues.length > 0 && (
          <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-sm font-semibold text-amber-100">
                  {t("workflowControl.messages.compatibilityWarningTitle")}
                </div>
                <div className="mt-1 text-xs text-amber-200/80">
                  {t("workflowControl.messages.compatibilityWarningHint")}
                </div>
              </div>
              <Badge tone="warning" className="shrink-0">
                {compatibilityIssues.length}
              </Badge>
            </div>
            <div className="mt-3 space-y-1 text-sm text-amber-100">
              {compatibilityIssues.slice(0, 3).map((issue) => (
                <div key={issue} className="rounded-xl border border-amber-400/15 bg-slate-950/30 px-3 py-2">
                  {issue}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
