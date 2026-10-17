"use client";

import { Component, type ReactNode } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n";
import { configHref, type useConfigNavigation } from "@/lib/config-navigation";

const Canvas = dynamic(() => import("./integration-topology").then((module) => module.IntegrationTopology), { ssr: false });
export class TopologyErrorBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}
export function IntegrationTopologyBoundary({ navigation }: Readonly<{ navigation: ReturnType<typeof useConfigNavigation> }>) {
  const t = useTranslation();
  return <TopologyErrorBoundary fallback={<p role="alert">{t("config.topology.unavailable")} <Link href={configHref({ tab: "integrations" }, navigation.search)}>{t("config.apiMap.title")}</Link></p>}><Canvas navigation={navigation} /></TopologyErrorBoundary>;
}
