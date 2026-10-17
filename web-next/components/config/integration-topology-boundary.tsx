"use client";

import { Component, type ReactNode } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n";
import { configHref, type useConfigNavigation } from "@/lib/config-navigation";

const Canvas = dynamic(() => import("./integration-topology").then((module) => module.IntegrationTopology), { ssr: false });
/** Isolate canvas loading and rendering failures from the rest of configuration. */
export class TopologyErrorBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  /** Switch only this boundary to its navigation-safe fallback after a child failure. */
  static getDerivedStateFromError() { return { failed: true }; }
  /** Keep working children visible unless the canvas has failed. */
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}
/** Load the canvas only when topology is visited and retain a link to the integration list on failure. */
export function IntegrationTopologyBoundary({ navigation }: Readonly<{ navigation: ReturnType<typeof useConfigNavigation> }>) {
  const t = useTranslation();
  return <TopologyErrorBoundary fallback={<p role="alert">{t("config.topology.unavailable")} <Link href={configHref({ tab: "integrations" }, navigation.search)}>{t("config.apiMap.title")}</Link></p>}><Canvas navigation={navigation} /></TopologyErrorBoundary>;
}
