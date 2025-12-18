"use client";

import { useState } from "react";
import { Settings, Server, FileCode } from "lucide-react";
import { ServicesPanel } from "./services-panel";
import { ParametersPanel } from "./parameters-panel";

export function ConfigHome() {
  const [activeTab, setActiveTab] = useState<"services" | "parameters">("services");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white">
            Konfiguracja
          </h1>
          <p className="mt-2 text-sm text-zinc-400">
            Panel sterowania stosem Venom: uruchamianie/zatrzymywanie usług i
            konfiguracja parametrów
          </p>
        </div>
        <Settings className="h-8 w-8 text-emerald-400" />
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-white/10">
        <button
          onClick={() => setActiveTab("services")}
          className={`flex items-center gap-2 rounded-t-xl px-4 py-3 text-sm font-medium transition ${
            activeTab === "services"
              ? "border-b-2 border-emerald-400 bg-emerald-500/10 text-emerald-300"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          }`}
        >
          <Server className="h-4 w-4" />
          Usługi
        </button>
        <button
          onClick={() => setActiveTab("parameters")}
          className={`flex items-center gap-2 rounded-t-xl px-4 py-3 text-sm font-medium transition ${
            activeTab === "parameters"
              ? "border-b-2 border-emerald-400 bg-emerald-500/10 text-emerald-300"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          }`}
        >
          <FileCode className="h-4 w-4" />
          Parametry
        </button>
      </div>

      {/* Content */}
      <div className="min-h-[500px]">
        {activeTab === "services" && <ServicesPanel />}
        {activeTab === "parameters" && <ParametersPanel />}
      </div>
    </div>
  );
}
