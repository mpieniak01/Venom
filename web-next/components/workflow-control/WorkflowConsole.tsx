
import { useTranslation } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
    Save,
    RotateCcw,
    Play,
    Pause,
    Square,
    RefreshCw,
    Bug,
    Settings2,
    Activity
} from "lucide-react";

interface WorkflowConsoleProps {
    hasChanges: boolean;
    onPlanRequest: () => void;
    onReset: () => void;
    status: string;
    onPause: () => void;
    onResume: () => void;
    onCancel: () => void;
    onRetry: () => void;
    onDryRun: () => void;
    isLoading?: boolean;
}

export function WorkflowConsole({
    hasChanges,
    onPlanRequest,
    onReset,
    status,
    onPause,
    onResume,
    onCancel,
    onRetry,
    onDryRun,
    isLoading
}: Readonly<WorkflowConsoleProps>) {
    const t = useTranslation();

    const isRunning = status === "running";
    const isPaused = status === "paused";
    const isFailed = status === "failed";
    const showResume = isRunning === false;
    let statusColorClass = "text-slate-400";
    if (isRunning) {
        statusColorClass = "text-green-500";
    } else if (isFailed) {
        statusColorClass = "text-red-500";
    }

    return (
        <div className="border border-white/10 bg-slate-900/50 backdrop-blur-xl p-6 flex flex-col gap-6 rounded-xl shadow-2xl">
            {/* Console Header */}
            <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-bold text-slate-300 uppercase tracking-widest flex items-center gap-2">
                    <Settings2 className="w-4 h-4" />
                    {t("workflowControl.panels.console")}
                </h3>
                <div className="flex items-center gap-2">
                    <Activity className={`w-3.5 h-3.5 ${isRunning ? "text-green-500 animate-pulse" : "text-slate-500"}`} />
                    <span className={`text-[10px] font-mono uppercase font-bold tracking-tight ${statusColorClass}`}>
                        {status}
                    </span>
                </div>
            </div>
            <div className="h-px w-full bg-white/5 -mt-4 mb-2" />

            {/* Setup Actions (Draft Mode) */}
            <div className="space-y-3">
                <div className="flex items-center justify-between">
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">{t("workflowControl.labels.draftSetup")}</span>
                    {hasChanges && (
                        <Badge tone="warning" className="px-1.5 py-0 text-[9px] h-4 border-amber-500/50 text-amber-500 uppercase font-bold">
                            {t("workflowControl.status.draft")}
                        </Badge>
                    )}
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <Button
                        id="workflow-action-reset"
                        variant="ghost"
                        size="sm"
                        className="w-full text-xs h-10 border border-white/5 hover:bg-white/10 transition-colors"
                        onClick={onReset}
                        disabled={!hasChanges || isLoading}
                    >
                        <RotateCcw className="w-3.5 h-3.5 mr-2" />
                        {t("workflowControl.actions.reset")}
                    </Button>
                    <Button
                        id="workflow-action-plan"
                        variant="primary"
                        size="sm"
                        className="w-full text-xs h-10 shadow-[0_4px_20px_rgba(59,130,246,0.4)] hover:shadow-[0_6px_25px_rgba(59,130,246,0.5)] transition-all"
                        onClick={onPlanRequest}
                        disabled={!hasChanges || isLoading}
                    >
                        <Save className="w-3.5 h-3.5 mr-2" />
                        {t("workflowControl.actions.planChanges")}
                    </Button>
                </div>
            </div>

            {/* Runtime Actions (Execution) */}
            <div className="space-y-3">
                <span className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">{t("workflowControl.labels.runtimeControl")}</span>
                <div className="grid grid-cols-2 gap-3">
                    {showResume ? (
                        <Button
                            id="workflow-action-resume"
                            variant="secondary"
                            size="sm"
                            className="w-full text-xs h-10"
                            onClick={onResume}
                            disabled={isLoading || isRunning}
                        >
                            <Play className="w-3.5 h-3.5 mr-2" />
                            {t("workflowControl.actions.resume")}
                        </Button>
                    ) : (
                        <Button
                            id="workflow-action-pause"
                            variant="outline"
                            size="sm"
                            className="w-full text-xs h-10 border-amber-500/30 text-amber-500 hover:bg-amber-500/10"
                            onClick={onPause}
                            disabled={isLoading || isPaused}
                        >
                            <Pause className="w-3.5 h-3.5 mr-2" />
                            {t("workflowControl.actions.pause")}
                        </Button>
                    )}

                    <Button
                        id="workflow-action-stop"
                        variant="danger"
                        size="sm"
                        className="w-full text-xs h-10"
                        onClick={onCancel}
                        disabled={isLoading || (!isRunning && !isPaused)}
                    >
                        <Square className="w-3.5 h-3.5 mr-2" />
                        {t("workflowControl.actions.stop")}
                    </Button>

                    {isFailed && (
                        <Button
                            id="workflow-action-retry"
                            variant="primary"
                            size="sm"
                            className="w-full text-xs h-10 col-span-2"
                            onClick={onRetry}
                            disabled={isLoading}
                        >
                            <RefreshCw className="w-3.5 h-3.5 mr-2" />
                            {t("workflowControl.actions.retry")}
                        </Button>
                    )}

                    <Button
                        id="workflow-action-dryrun"
                        variant="ghost"
                        size="sm"
                        className="w-full text-xs h-10 border border-white/5 hover:bg-white/5 col-span-2 mt-1"
                        onClick={onDryRun}
                        disabled={isLoading}
                    >
                        <Bug className="w-3.5 h-3.5 mr-2" />
                        {t("workflowControl.actions.dryRun")}
                    </Button>
                </div>
            </div>
        </div>
    );
}
