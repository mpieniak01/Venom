import { Suspense } from "react";
import { BrainWrapper, BrainSkeleton } from "@/components/brain/brain-wrapper";

export const dynamic = "force-dynamic";

export default function BrainPage() {
  return (
    <Suspense fallback={<BrainSkeleton />}>
      <BrainWrapper />
    </Suspense>
  );
}
