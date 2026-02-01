import { Suspense } from "react";
import { ConfigHome } from "@/components/config/config-home";

export const metadata = {
  title: "Configuration - Venom Cockpit",
  description: "Venom stack configuration and control panel",
};

export default function ConfigPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[400px] items-center justify-center">
          <div className="text-zinc-400">Loading configuration...</div>
        </div>
      }
    >
      <ConfigHome />
    </Suspense>
  );
}
