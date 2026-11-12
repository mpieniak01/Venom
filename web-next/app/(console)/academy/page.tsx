import { AcademyDashboard } from "@/components/academy/academy-dashboard";

export default async function AcademyPage({
  searchParams,
}: {
  searchParams: Promise<{ campaign?: string | string[] }>;
}) {
  const { campaign } = await searchParams;
  const campaignId = typeof campaign === "string" && /^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$/.test(campaign)
    ? campaign
    : undefined;

  return <AcademyDashboard initialCampaignId={campaignId} />;
}
