import { SystemStatusBar } from "./system-status-bar";
import { fetchLayoutInitialData } from "@/lib/server-data";

export async function SystemStatusBarWrapper() {
    const layoutData = await fetchLayoutInitialData();

    const initialSystemStatus = {
        modelsUsage: layoutData.modelsUsage,
        tokenMetrics: layoutData.tokenMetrics,
        gitStatus: layoutData.gitStatus,
    };

    return <SystemStatusBar initialData={initialSystemStatus} />;
}

export function SystemStatusBarSkeleton() {
    return (
        <div className="pointer-events-none absolute inset-x-0 bottom-6 z-30 px-4 sm:px-8 lg:px-10 lg:pl-[calc(var(--sidebar-width)+2.5rem)] xl:px-12 xl:pl-[calc(var(--sidebar-width)+3rem)]">
            <div className="mr-auto w-full max-w-[1320px] xl:max-w-[1536px] 2xl:max-w-[85vw] border border-white/15 bg-black/75 px-5 py-4 h-[58px] shadow-2xl backdrop-blur-2xl animate-pulse">
                <div className="flex items-center justify-between">
                    <div className="h-4 w-1/2 rounded bg-white/5" />
                    <div className="h-4 w-1/4 rounded bg-white/5" />
                </div>
            </div>
        </div>
    );
}
