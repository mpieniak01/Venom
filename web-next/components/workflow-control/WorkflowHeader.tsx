
import { useTranslation } from "@/lib/i18n";
import { SectionHeading } from "@/components/ui/section-heading";

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
}: WorkflowHeaderProps) {
    const t = useTranslation();
    void hasChanges;
    void onPlanRequest;
    void onReset;
    void isLoading;

    return (
        <div className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 px-6 py-1.5">
            <SectionHeading
                title={t("workflowControl.title")}
                description={t("workflowControl.description")}
            />
        </div>
    );
}
