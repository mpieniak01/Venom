import { CockpitHome } from "@/components/cockpit/cockpit-home";
import { fetchCockpitInitialData } from "@/lib/server-data";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const initialData = await fetchCockpitInitialData();
  return <CockpitHome initialData={initialData} />;
}
