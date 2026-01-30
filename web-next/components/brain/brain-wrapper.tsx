import { BrainHome } from "./brain-home";
import { fetchBrainInitialData } from "@/lib/server-data";

export async function BrainWrapper() {
    const initialData = await fetchBrainInitialData();
    return <BrainHome initialData={initialData} />;
}

export function BrainSkeleton() {
    return (
        <div className="space-y-6 animate-pulse">
            <div className="h-10 w-1/4 rounded bg-white/5" />
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
                <div className="lg:col-span-3 h-[700px] rounded border border-white/10 bg-black/20" />
                <div className="space-y-6">
                    <div className="h-[340px] rounded border border-white/10 bg-black/20" />
                    <div className="h-[340px] rounded border border-white/10 bg-black/20" />
                </div>
            </div>
        </div>
    );
}
