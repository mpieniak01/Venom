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
        <div className="glass-panel sticky top-0 z-30 border-b border-white/5 bg-black/40 px-4 py-4 backdrop-blur-2xl sm:px-6 h-[73px]">
            <div className="flex w-full items-center justify-between gap-6">
                <div className="h-8 w-8 rounded bg-white/5 animate-pulse lg:hidden" />
                <div className="flex flex-1 items-center justify-end gap-4">
                    <div className="h-8 w-48 rounded bg-white/5 animate-pulse hidden md:block" />
                    <div className="h-8 w-8 rounded bg-white/5 animate-pulse" />
                    <div className="h-8 w-8 rounded bg-white/5 animate-pulse" />
                    <div className="h-8 w-32 rounded bg-white/5 animate-pulse" />
                </div>
            </div>
        </div>
    );
}
