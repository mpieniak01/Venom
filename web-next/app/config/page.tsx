import { Suspense } from "react";
import { ConfigHome } from "@/components/config/config-home";

export const metadata = {
  title: "Konfiguracja - Venom Cockpit",
  description: "Panel konfiguracji i sterowania stosem Venom",
};

export default function ConfigPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[400px] items-center justify-center">
          <div className="text-zinc-400">Ładowanie konfiguracji...</div>
        </div>
      }
    >
      <ConfigHome />
    </Suspense>
  );
}
