import { BrainHome } from "@/components/brain/brain-home";
import { fetchBrainInitialData } from "@/lib/server-data";

export const dynamic = "force-dynamic";

export default async function BrainPage() {
  const initialData = await fetchBrainInitialData();
  return <BrainHome initialData={initialData} />;
}
