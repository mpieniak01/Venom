import { CockpitHome } from "./cockpit-home";
import { EMPTY_COCKPIT_INITIAL_DATA } from "@/lib/server-data";

export function CockpitWrapper({ variant = "home" }: Readonly<{ variant?: "reference" | "home" }>) {
    return <CockpitHome initialData={EMPTY_COCKPIT_INITIAL_DATA} variant={variant} />;
}

export function CockpitSkeleton() {
    return (
        <div className="space-y-6 animate-pulse">
            <div className="h-10 w-1/4 rounded bg-[color:var(--ui-border)]" />
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div className="lg:col-span-2 h-[600px] rounded border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)]" />
                <div className="h-[600px] rounded border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)]" />
            </div>
        </div>
    );
}
