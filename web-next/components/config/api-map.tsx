"use client";

import { useCallback, useEffect, useState } from "react";
import {
    Network,
    Globe,
    Lock,
    Shield,
    ArrowRight,
    RefreshCw,
    Server,
    Cloud,
    Code,
    CheckCircle2,
    AlertCircle,
    XCircle,
    HelpCircle,
} from "lucide-react";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { components } from "@/lib/generated/api-types";

type ApiMapResponse = components["schemas"]["ApiMapResponse"];
export type ApiConnection = components["schemas"]["ApiConnection"] & { methods?: string[] };

export function shouldShowConnection(
    conn: ApiConnection,
    filters: {
        source: string;
        status: string;
        protocol: string;
    }
) {
    if (filters.source !== "all" && conn.source_type !== filters.source) return false;
    if (filters.status !== "all" && conn.status !== filters.status) return false;
    if (filters.protocol !== "all" && conn.protocol !== filters.protocol) return false;
    return true;
}

export function ApiMap() {
    const t = useTranslation();
    const [data, setData] = useState<ApiMapResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedConnection, setSelectedConnection] = useState<ApiConnection | null>(null);
    const [filterType, setFilterType] = useState<"all" | "internal" | "external">("all");
    const [filterSource, setFilterSource] = useState<string>("all");
    const [filterStatus, setFilterStatus] = useState<string>("all");
    const [filterProtocol, setFilterProtocol] = useState<string>("all");

    const fetchData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch("/api/v1/system/api-map");
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const jsonData = await response.json();
            setData(jsonData);
            // Auto-select first connection if available
            if (jsonData.internal_connections?.length > 0) {
                setSelectedConnection(jsonData.internal_connections[0]);
            } else if (jsonData.external_connections?.length > 0) {
                setSelectedConnection(jsonData.external_connections[0]);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unknown error");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    const getProtocolBadge = (protocol: string) => {
        const colors: Record<string, string> = {
            http: "bg-blue-500/10 text-blue-400 border-blue-500/20",
            https: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
            ws: "bg-purple-500/10 text-purple-400 border-purple-500/20",
            sse: "bg-amber-500/10 text-amber-400 border-amber-500/20",
        };
        return (
            <span
                className={cn(
                    "rounded-md border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
                    colors[protocol.toLowerCase()] || "bg-zinc-800 text-zinc-400"
                )}
            >
                {protocol}
            </span>
        );
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case "ok":
                return <CheckCircle2 className="h-4 w-4 text-emerald-400" />;
            case "degraded":
                return <AlertCircle className="h-4 w-4 text-yellow-400" />;
            case "down":
                return <XCircle className="h-4 w-4 text-red-400" />;
            default:
                return <HelpCircle className="h-4 w-4 text-zinc-500" />;
        }
    };

    const ConnectionCard = ({
        connection,
        isSelected,
        onClick
    }: {
        connection: ApiConnection;
        isSelected: boolean;
        onClick: () => void;
    }) => {
        const isCloud = connection.source_type === "cloud";
        const TargetIcon = isCloud ? Cloud : Server;

        return (
            <button
                onClick={onClick}
                className={cn(
                    "w-full text-left relative overflow-hidden rounded-xl border p-4 transition-all hover:bg-white/5",
                    isSelected
                        ? "border-emerald-500/50 bg-emerald-500/10 ring-1 ring-emerald-500/20"
                        : "border-white/5 bg-white/5"
                )}
            >
                <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                        <div className={cn(
                            "flex h-8 w-8 items-center justify-center rounded-lg border",
                            isSelected ? "border-emerald-500/30 bg-emerald-500/20" : "border-white/10 bg-white/10"
                        )}>
                            <TargetIcon className={cn("h-4 w-4", isSelected ? "text-emerald-300" : "text-zinc-400")} />
                        </div>
                        <div>
                            <div className="flex items-center gap-2">
                                <span className={cn("font-medium", isSelected ? "text-emerald-300" : "text-zinc-200")}>
                                    {connection.target_component}
                                </span>
                                {connection.is_critical && (
                                    <Shield className="h-3 w-3 text-red-400" aria-label="Critical" />
                                )}
                            </div>
                            <p className="text-xs text-zinc-500 line-clamp-1">{connection.description}</p>
                        </div>
                    </div>
                    {getStatusIcon(connection.status)}
                </div>
            </button>
        );
    };

    // --- Filtering Logic ---
    const filterConnection = (conn: ApiConnection) => {
        return shouldShowConnection(conn, {
            source: filterSource,
            status: filterStatus,
            protocol: filterProtocol
        });
    };

    const filteredInternal = data?.internal_connections.filter(filterConnection) || [];
    const filteredExternal = data?.external_connections.filter(filterConnection) || [];

    const showInternal = filterType === "all" || filterType === "internal";
    const showExternal = filterType === "all" || filterType === "external";


    if (loading && !data) {
        return (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                <div className="h-[400px] rounded-xl bg-white/5 animate-pulse" />
                <div className="space-y-4">
                    {[1, 2, 3].map((i) => (
                        <div key={i} className="h-24 rounded-xl bg-white/5 animate-pulse" />
                    ))}
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-6 text-center text-red-400">
                <p>{t("config.apiMap.errorLoading")}: {error}</p>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={fetchData}
                    className="mt-4 border-red-500/30 hover:bg-red-500/20"
                >
                    {t("config.apiMap.refresh")}
                </Button>
            </div>
        );
    }

    return (
        <div className="flex flex-col gap-6 lg:h-[calc(100vh-220px)] lg:flex-row">
            {/* Left Column: List of Providers */}
            <div className="flex-1 lg:overflow-hidden flex flex-col gap-4">
                <div className="flex items-center justify-between">
                    <h3 className="heading-h3 text-zinc-400 uppercase tracking-widest text-xs font-semibold">
                        {t("config.apiMap.description")}
                    </h3>
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={fetchData}
                        className="h-8 text-zinc-400 hover:text-white"
                    >
                        <RefreshCw className={cn("h-3.5 w-3.5 mr-1.5", loading && "animate-spin")} />
                        {t("config.apiMap.refresh")}
                    </Button>
                </div>

                {/* Filters Toolbar */}
                <div className="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-none">
                    <Select value={filterType} onValueChange={(v: string) => setFilterType(v as "all" | "internal" | "external")}>
                        <SelectTrigger className="w-[130px] h-8 text-xs bg-black/20 border-white/10 text-zinc-300">
                            <SelectValue placeholder={t("config.apiMap.filters.type.label")} />
                        </SelectTrigger>
                        <SelectContent className="bg-zinc-950 border-white/10 text-zinc-300">
                            <SelectItem value="all">{t("config.apiMap.filters.type.all")}</SelectItem>
                            <SelectItem value="internal">{t("config.apiMap.filters.type.internal")}</SelectItem>
                            <SelectItem value="external">{t("config.apiMap.filters.type.external")}</SelectItem>
                        </SelectContent>
                    </Select>

                    <Select value={filterSource} onValueChange={setFilterSource}>
                        <SelectTrigger className="w-[130px] h-8 text-xs bg-black/20 border-white/10 text-zinc-300">
                            <SelectValue placeholder={t("config.apiMap.filters.source.label")} />
                        </SelectTrigger>
                        <SelectContent className="bg-zinc-950 border-white/10 text-zinc-300">
                            <SelectItem value="all">{t("config.apiMap.filters.source.all")}</SelectItem>
                            <SelectItem value="local">{t("config.apiMap.filters.source.local")}</SelectItem>
                            <SelectItem value="cloud">{t("config.apiMap.filters.source.cloud")}</SelectItem>
                            <SelectItem value="hybrid">{t("config.apiMap.filters.source.hybrid")}</SelectItem>
                        </SelectContent>
                    </Select>

                    <Select value={filterStatus} onValueChange={setFilterStatus}>
                        <SelectTrigger className="w-[130px] h-8 text-xs bg-black/20 border-white/10 text-zinc-300">
                            <SelectValue placeholder={t("config.apiMap.filters.status.label")} />
                        </SelectTrigger>
                        <SelectContent className="bg-zinc-950 border-white/10 text-zinc-300">
                            <SelectItem value="all">{t("config.apiMap.filters.status.all")}</SelectItem>
                            <SelectItem value="ok">{t("config.apiMap.filters.status.ok")}</SelectItem>
                            <SelectItem value="degraded">{t("config.apiMap.filters.status.degraded")}</SelectItem>
                            <SelectItem value="down">{t("config.apiMap.filters.status.down")}</SelectItem>
                            <SelectItem value="unknown">{t("config.apiMap.filters.status.unknown")}</SelectItem>
                        </SelectContent>
                    </Select>

                    <Select value={filterProtocol} onValueChange={setFilterProtocol}>
                        <SelectTrigger className="w-[130px] h-8 text-xs bg-black/20 border-white/10 text-zinc-300">
                            <SelectValue placeholder={t("config.apiMap.filters.protocol.label")} />
                        </SelectTrigger>
                        <SelectContent className="bg-zinc-950 border-white/10 text-zinc-300">
                            <SelectItem value="all">{t("config.apiMap.filters.protocol.all")}</SelectItem>
                            <SelectItem value="http">HTTP</SelectItem>
                            <SelectItem value="https">HTTPS</SelectItem>
                            <SelectItem value="ws">WS</SelectItem>
                            <SelectItem value="sse">SSE</SelectItem>
                        </SelectContent>
                    </Select>
                </div>

                {/* Lists */}
                <div className="flex-1 overflow-y-auto pr-4 -mr-4">
                    <div className="space-y-8 pb-4">
                        {/* Internal Section */}
                        {showInternal && filteredInternal.length > 0 && (
                            <section className="space-y-3">
                                <div className="flex items-center gap-2 px-1">
                                    <Network className="h-4 w-4 text-emerald-400" />
                                    <h3 className="text-sm font-medium text-zinc-200">{t("config.apiMap.internal")}</h3>
                                    <span className="text-xs text-zinc-500">({filteredInternal.length})</span>
                                </div>
                                <div className="space-y-2">
                                    {filteredInternal.map((conn, idx) => (
                                        <ConnectionCard
                                            key={`internal-${idx}`}
                                            connection={conn}
                                            isSelected={selectedConnection === conn}
                                            onClick={() => setSelectedConnection(conn)}
                                        />
                                    ))}
                                </div>
                            </section>
                        )}

                        {/* External Section */}
                        {showExternal && filteredExternal.length > 0 && (
                            <section className="space-y-3">
                                <div className="flex items-center gap-2 px-1">
                                    <Globe className="h-4 w-4 text-blue-400" />
                                    <h3 className="text-sm font-medium text-zinc-200">{t("config.apiMap.external")}</h3>
                                    <span className="text-xs text-zinc-500">({filteredExternal.length})</span>
                                </div>
                                <div className="space-y-2">
                                    {filteredExternal.map((conn, idx) => (
                                        <ConnectionCard
                                            key={`external-${idx}`}
                                            connection={conn}
                                            isSelected={selectedConnection === conn}
                                            onClick={() => setSelectedConnection(conn)}
                                        />
                                    ))}
                                </div>
                            </section>
                        )}

                        {filteredInternal.length === 0 && filteredExternal.length === 0 && (
                            <div className="text-center py-12 text-zinc-500">
                                {t("config.apiMap.no_methods") /* Reusing no_methods or add no_results */}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Right Column: Details */}
            <div className="flex-1 lg:overflow-hidden flex flex-col gap-4">
                <div className="glass-panel rounded-2xl box-subtle p-6 h-full flex flex-col">
                    {selectedConnection ? (
                        <div className="space-y-6 flex-1 flex flex-col overflow-hidden">
                            {/* Header */}
                            <div className="flex items-start justify-between border-b border-white/5 pb-6">
                                <div className="space-y-1">
                                    <h2 className="heading-h2 text-2xl">{selectedConnection.target_component}</h2>
                                    <p className="text-zinc-400">{selectedConnection.description}</p>
                                    <div className="flex items-center gap-2 mt-2">
                                        <span className="text-xs text-zinc-500 flex items-center gap-1">
                                            <ArrowRight className="h-3 w-3" />
                                            {selectedConnection.source_component}
                                        </span>
                                    </div>
                                </div>
                                <div className="flex flex-col items-end gap-2">
                                    <span className={cn(
                                        "flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium border",
                                        selectedConnection.status === "ok" && "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
                                        selectedConnection.status === "degraded" && "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
                                        selectedConnection.status === "down" && "bg-red-500/10 text-red-400 border-red-500/20",
                                        selectedConnection.status === "unknown" && "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
                                    )}>
                                        {getStatusIcon(selectedConnection.status)}
                                        <span className="uppercase">{selectedConnection.status}</span>
                                    </span>
                                    {selectedConnection.is_critical && (
                                        <span className="flex items-center gap-1 text-[10px] text-red-400 font-medium uppercase tracking-wider bg-red-500/10 px-2 py-0.5 rounded border border-red-500/20">
                                            <Shield className="h-3 w-3" /> {t("config.apiMap.legend.critical")}
                                        </span>
                                    )}
                                </div>
                            </div>

                            {/* Metadata Grid */}
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-1">
                                    <p className="text-xs text-zinc-500">{t("config.apiMap.connection.protocol")}</p>
                                    <div className="flex items-center">
                                        {getProtocolBadge(selectedConnection.protocol)}
                                    </div>
                                </div>
                                <div className="space-y-1">
                                    <p className="text-xs text-zinc-500">{t("config.apiMap.connection.auth")}</p>
                                    <div className="flex items-center gap-2">
                                        {selectedConnection.auth_type !== "none" ? (
                                            <span className="flex items-center gap-1.5 text-sm text-zinc-300">
                                                <Lock className="h-3.5 w-3.5 text-zinc-500" />
                                                <span className="uppercase">{selectedConnection.auth_type}</span>
                                            </span>
                                        ) : (
                                            <span className="text-sm text-zinc-500">-</span>
                                        )}
                                    </div>
                                </div>
                                <div className="space-y-1">
                                    <p className="text-xs text-zinc-500">{t("config.apiMap.connection.source")}</p>
                                    <p className="text-sm text-zinc-300 uppercase">{selectedConnection.source_type}</p>
                                </div>
                                <div className="space-y-1">
                                    <p className="text-xs text-zinc-500">{t("config.apiMap.legend.outbound")}</p>
                                    <p className="text-sm text-zinc-300 uppercase">{selectedConnection.direction}</p>
                                </div>
                            </div>

                            {/* Methods List */}
                            <div className="flex-1 flex flex-col overflow-hidden pt-4 border-t border-white/5">
                                <div className="flex items-center gap-2 mb-4">
                                    <Code className="h-4 w-4 text-emerald-400" />
                                    <h3 className="text-sm font-medium text-white">{t("config.apiMap.methods")}</h3>
                                </div>

                                <div className="flex-1 overflow-y-auto -mr-4 pr-4">
                                    {selectedConnection.methods && selectedConnection.methods.length > 0 ? (
                                        <div className="space-y-2">
                                            {selectedConnection.methods.map((method, idx) => (
                                                <div key={idx} className="font-mono text-xs bg-black/40 border border-white/5 rounded-lg px-3 py-2 text-zinc-300 hover:border-emerald-500/30 hover:bg-emerald-500/5 transition-colors cursor-default">
                                                    {method}
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="text-center py-8 text-zinc-500 text-sm italic">
                                            {t("config.apiMap.no_methods")}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
                            <Network className="h-12 w-12 text-zinc-600 mb-4 opacity-50" />
                            <p className="text-zinc-500">{t("config.apiMap.select")}</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
