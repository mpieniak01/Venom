import { Suspense } from "react";
import { CockpitWrapper, CockpitSkeleton } from "@/components/cockpit/cockpit-wrapper";

export const dynamic = "force-dynamic";

export default function HomePage() {
  return (
    <Suspense fallback={<CockpitSkeleton />}>
      <CockpitWrapper variant="home" />
    </Suspense>
  );
}
