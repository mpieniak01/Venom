
import { useTranslation } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import {
    Play,
    Pause,
    Square,
    RefreshCw,
    Bug
} from "lucide-react";

interface WorkflowFooterProps {
    status: string;
    onPause: () => void;
    onResume: () => void;
    onCancel: () => void;
    onRetry: () => void;
    onDryRun: () => void;
    isLoading?: boolean;
}

export function WorkflowFooter({
    status,
    onPause,
    onResume,
    onCancel,
    onRetry,
    onDryRun,
    isLoading
}: WorkflowFooterProps) {
    const t = useTranslation();

    const isRunning = status === "running";
    const isPaused = status === "paused";
    const isFailed = status === "failed";
    let statusTextClass = "text-foreground";
    if (isRunning) {
        statusTextClass = "text-green-500";
    } else if (isFailed) {
        statusTextClass = "text-destructive";
    }

    return (
        <div className="border-t bg-muted/40 p-1 flex items-center justify-between gap-4 h-10">
            <div className="flex items-center gap-2 px-2">
                <span className="text-xs font-semibold text-muted-foreground uppercase">
                    {t("workflowControl.labels.systemStatus")}:
                </span>
                <span className={`text-sm font-mono ${statusTextClass}`}>
                    {status || "UNKNOWN"}
                </span>
            </div>

            <div className="flex items-center gap-1">
                {/* Operational Controls - Always visible for UX, disabled based on state */}

                {!isRunning && (
                    <Button variant="outline" size="sm" onClick={onResume} disabled={isLoading || isRunning}>
                        <Play className="w-3 h-3 mr-2" />
                        {t("workflowControl.actions.resume")}
                    </Button>
                )}

                {isRunning && (
                    <Button variant="outline" size="sm" onClick={onPause} disabled={isLoading || isPaused}>
                        <Pause className="w-3 h-3 mr-2" />
                        {t("workflowControl.actions.pause")}
                    </Button>
                )}

                <Button variant="danger" size="sm" onClick={onCancel} disabled={isLoading || (!isRunning && !isPaused)}>
                    <Square className="w-3 h-3 mr-2" />
                    {t("workflowControl.actions.stop")}
                </Button>

                {isFailed && (
                    <Button variant="primary" size="sm" onClick={onRetry} disabled={isLoading}>
                        <RefreshCw className="w-3 h-3 mr-2" />
                        {t("workflowControl.actions.retry")}
                    </Button>
                )}

                <div className="h-6 mx-2 border-l border-white/10" />

                <Button variant="secondary" size="sm" onClick={onDryRun} disabled={isLoading}>
                    <Bug className="w-3 h-3 mr-2" />
                    {t("workflowControl.actions.dryRun")}
                </Button>
            </div>
        </div>
    );
}
