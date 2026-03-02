import { TopBar } from "./top-bar";
import { fetchLayoutInitialData } from "@/lib/server-data";

export async function TopBarWrapper() {
    const layoutData = await fetchLayoutInitialData();

    const initialStatusData = {
        queue: layoutData.queue,
        metrics: layoutData.metrics,
        tasks: layoutData.tasks,
    };

    return <TopBar initialStatusData={initialStatusData} />;
}

export function TopBarSkeleton() {
    return (
        <div className="glass-panel sticky top-0 z-30 h-[73px] border-b border-[color:var(--ui-border)] bg-[color:var(--topbar-bg)] px-4 py-4 backdrop-blur-2xl sm:px-6">
            <div className="flex w-full items-center justify-between gap-6">
                <div className="h-8 w-8 animate-pulse rounded bg-[color:var(--ui-surface-hover)] lg:hidden" />
                <div className="flex flex-1 items-center justify-end gap-4">
                    <div className="hidden h-8 w-48 animate-pulse rounded bg-[color:var(--ui-surface-hover)] md:block" />
                    <div className="h-8 w-8 animate-pulse rounded bg-[color:var(--ui-surface-hover)]" />
                    <div className="h-8 w-8 animate-pulse rounded bg-[color:var(--ui-surface-hover)]" />
                    <div className="h-8 w-32 animate-pulse rounded bg-[color:var(--ui-surface-hover)]" />
                </div>
            </div>
        </div>
    );
}
