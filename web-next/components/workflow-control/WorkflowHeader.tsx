
import { useTranslation } from "@/lib/i18n";
import { SectionHeading } from "@/components/ui/section-heading";
import { Button } from "@/components/ui/button";

interface WorkflowHeaderProps {
    hasChanges: boolean;
    onPlanRequest: () => void;
    onReset: () => void;
    isLoading?: boolean;
}

export function WorkflowHeader({
    hasChanges,
    onPlanRequest,
    onReset,
    isLoading
}: Readonly<WorkflowHeaderProps>) {
    const t = useTranslation();

    return (
        <div className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 px-6 py-3">
            <div className="flex items-start justify-between gap-4">
                <SectionHeading
                    title={t("workflowControl.title")}
                    description={t("workflowControl.description")}
                />
                <div className="flex items-center gap-2">
                    <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={onReset}
                        disabled={isLoading}
                    >
                        {t("workflowControl.actions.reset")}
                    </Button>
                    <Button
                        type="button"
                        size="sm"
                        onClick={onPlanRequest}
                        disabled={isLoading || !hasChanges}
                    >
                        {t("workflowControl.actions.planChanges")}
                    </Button>
                </div>
            </div>
        </div>
    );
}
