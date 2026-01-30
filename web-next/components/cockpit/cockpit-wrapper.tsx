import { CockpitHome } from "./cockpit-home";
import { fetchCockpitInitialData } from "@/lib/server-data";

export async function CockpitWrapper({ variant = "home" }: { variant?: "reference" | "home" }) {
    const initialData = await fetchCockpitInitialData();
    return <CockpitHome initialData={initialData} variant={variant} />;
}

export function CockpitSkeleton() {
    return (
        <div className="space-y-6 animate-pulse">
            <div className="h-10 w-1/4 rounded bg-white/5" />
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div className="lg:col-span-2 h-[600px] rounded border border-white/10 bg-black/20" />
                <div className="h-[600px] rounded border border-white/10 bg-black/20" />
            </div>
        </div>
    );
}
