import { useTranslation } from "@/lib/i18n";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Node } from "@xyflow/react";
import { GitFork, Compass, Cpu, Server, Cloud, Database, Settings2 } from "lucide-react";

interface PropertyPanelProps {
    selectedNode: Node | null;
    onUpdateNode: (nodeId: string, data: unknown) => void;
    availableOptions?: {
        strategies?: string[];
        kernels?: string[];
        providers?: string[];
        models?: string[];
    };
}

type RuntimeService = string | { name?: string; id?: string; [key: string]: unknown };

function formatRuntimeService(service: RuntimeService): string {
    if (typeof service === "string") return service;
    if (service.name) return service.name;
    if (service.id) return service.id;
    return JSON.stringify(service);
}

export function PropertyPanel({
    selectedNode,
    onUpdateNode,
    availableOptions = {
        strategies: ["standard", "advanced", "heuristic"],
        kernels: ["default", "optimized", "legacy"],
        providers: ["openai", "google", "anthropic", "ollama"],
        models: ["gpt-4", "gemini-pro", "claude-3-opus", "llama3"]
    } // Mock defaults, should come from API props
}: PropertyPanelProps) {
    const t = useTranslation();

    if (!selectedNode) {
        return (
            <div className="h-full flex items-center justify-center text-muted-foreground p-4 text-center text-sm">
                {t("workflowControl.messages.selectNode")}
            </div>
        );
    }

    const { type, data } = selectedNode;

    const handleUpdate = (key: string, value: unknown) => {
        onUpdateNode(selectedNode.id, {
            ...(data as Record<string, unknown>),
            [key]: value
        });
    };

    // Icon Mapping
    const IconComponent =
        type === 'decision' ? GitFork :
            type === 'intent' ? Compass :
                type === 'kernel' ? Cpu :
                    type === 'runtime' ? Server :
                        type === 'provider' ? Cloud :
                            type === 'embedding' ? Database :
                                Compass;

    const iconColorClass =
        type === 'decision' ? 'text-blue-400' :
            type === 'intent' ? 'text-yellow-400' :
                type === 'kernel' ? 'text-green-400' :
                    type === 'runtime' ? 'text-purple-400' :
                        type === 'provider' ? 'text-orange-400' :
                            type === 'embedding' ? 'text-pink-400' :
                                'text-slate-400';

    const headerBgClass =
        type === 'decision' ? 'bg-blue-500/20 border-blue-500 shadow-blue-500/20' :
            type === 'intent' ? 'bg-yellow-500/20 border-yellow-500 shadow-yellow-500/20' :
                type === 'kernel' ? 'bg-green-500/20 border-green-500 shadow-green-500/20' :
                    type === 'runtime' ? 'bg-purple-500/20 border-purple-500 shadow-purple-500/20' :
                        type === 'provider' ? 'bg-orange-500/20 border-orange-500 shadow-orange-500/20' :
                            type === 'embedding' ? 'bg-pink-500/20 border-pink-500 shadow-pink-500/20' :
                                'bg-slate-500/20 border-slate-500 shadow-slate-500/20';

    return (
        <div className="h-full border border-white/10 bg-slate-950/95 backdrop-blur-xl pt-0 p-4 relative overflow-hidden flex flex-col gap-4 rounded-xl shadow-2xl">
            {/* Ambient Background Glow */}
            <div className="absolute top-0 right-0 w-64 h-64 bg-cyan-500/10 blur-[100px] rounded-full pointer-events-none" />
            <div className="absolute bottom-0 left-0 w-64 h-64 bg-violet-500/10 blur-[100px] rounded-full pointer-events-none" />

            <div className="relative z-10 px-2 py-4">
                <h2 className="text-xs font-bold text-slate-300 uppercase tracking-widest flex items-center gap-2 mb-3">
                    <Settings2 className="w-3.5 h-3.5" />
                    {t("workflowControl.panels.propertyInspector")}
                </h2>
                <div className="h-px w-full bg-white/5 mb-6" />

                <div className="flex items-center gap-4 mb-5 px-1">
                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center border shadow-[0_4px_20px_rgba(0,0,0,0.4)] ${headerBgClass} ${iconColorClass}`}>
                        <IconComponent className="w-6 h-6" />
                    </div>
                    <div>
                        <div className="text-[10px] text-slate-500 font-mono tracking-tight mb-0.5">{selectedNode.id}</div>
                        <div className="text-sm font-bold uppercase tracking-wider text-slate-400">{type} {t("workflowControl.labels.node")}</div>
                    </div>
                </div>

                {/* Form Content */}
                <div className="space-y-2 relative z-10">

                    {/* Decision Node Form */}
                    {type === "decision" && (
                        <div className="p-4 rounded-2xl border border-cyan-500/20 bg-cyan-500/5 shadow-[0_4px_25px_rgba(6,182,212,0.05)]">
                            <div className="flex items-center gap-3 mb-3 border-b border-cyan-500/10 pb-2">
                                <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400">
                                    <GitFork className="w-4 h-4" />
                                </div>
                                <div>
                                    <h3 className="text-[10px] font-bold text-cyan-400 uppercase tracking-widest">{t("workflowControl.sections.decision")}</h3>
                                    <p className="text-[9px] text-cyan-400/50 uppercase tracking-tight mt-0.5">{t("workflowControl.descriptions.decision")}</p>
                                </div>
                            </div>
                            <Label htmlFor="strategy" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">{t("workflowControl.labels.strategy")}</Label>
                            <Select
                                value={(data as Record<string, unknown>).strategy as string}
                                onValueChange={(val) => handleUpdate("strategy", val)}
                            >
                                <SelectTrigger id="strategy" className="bg-slate-900/80 border-cyan-500/30 text-cyan-100 focus:ring-cyan-500/50">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-cyan-500/30 text-cyan-100">
                                    {availableOptions.strategies?.map(opt => (
                                        <SelectItem key={opt} value={opt} className="focus:bg-cyan-500/20 focus:text-cyan-100">
                                            {t(`workflowControl.strategies.${opt}`) || opt}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    )}

                    {/* Intent Node Form */}
                    {type === "intent" && (
                        <div className="p-4 rounded-2xl border border-yellow-500/20 bg-yellow-500/5 shadow-[0_4px_25px_rgba(234,179,8,0.05)]">
                            <div className="flex items-center gap-3 mb-3 border-b border-yellow-500/10 pb-2">
                                <div className="p-2 rounded-lg bg-yellow-500/10 text-yellow-400">
                                    <Compass className="w-4 h-4" />
                                </div>
                                <div>
                                    <h3 className="text-[10px] font-bold text-yellow-400 uppercase tracking-widest">{t("workflowControl.sections.intent")}</h3>
                                    <p className="text-[9px] text-yellow-400/50 uppercase tracking-tight mt-0.5">{t("workflowControl.descriptions.intent")}</p>
                                </div>
                            </div>
                            <Label htmlFor="intentMode" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">{t("workflowControl.labels.intentMode")}</Label>
                            <Select
                                value={(data as Record<string, unknown>).intentMode as string}
                                onValueChange={(val) => handleUpdate("intentMode", val)}
                            >
                                <SelectTrigger id="intentMode" className="bg-slate-900/80 border-yellow-500/30 text-yellow-100 focus:ring-yellow-500/50">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-yellow-500/30 text-yellow-100">
                                    <SelectItem value="strict" className="focus:bg-yellow-500/20">{t("workflowControl.intentModes.strict")}</SelectItem>
                                    <SelectItem value="flexible" className="focus:bg-yellow-500/20">{t("workflowControl.intentModes.flexible")}</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    )}

                    {/* Kernel Node Form */}
                    {type === "kernel" && (
                        <div className="p-4 rounded-2xl border border-green-500/20 bg-green-500/5 shadow-[0_4px_25px_rgba(34,197,94,0.05)]">
                            <div className="flex items-center gap-3 mb-3 border-b border-green-500/10 pb-2">
                                <div className="p-2 rounded-lg bg-green-500/10 text-green-400">
                                    <Cpu className="w-4 h-4" />
                                </div>
                                <div>
                                    <h3 className="text-[10px] font-bold text-green-400 uppercase tracking-widest">{t("workflowControl.sections.kernel")}</h3>
                                    <p className="text-[9px] text-green-400/50 uppercase tracking-tight mt-0.5">{t("workflowControl.descriptions.kernel")}</p>
                                </div>
                            </div>
                            <Label htmlFor="kernel" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">{t("workflowControl.labels.currentKernel")}</Label>
                            <Select
                                value={(data as Record<string, unknown>).kernel as string}
                                onValueChange={(val) => handleUpdate("kernel", val)}
                            >
                                <SelectTrigger id="kernel" className="bg-slate-900/80 border-green-500/30 text-green-100 focus:ring-green-500/50">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-green-500/30 text-green-100">
                                    {availableOptions.kernels?.map(opt => (
                                        <SelectItem key={opt} value={opt} className="focus:bg-green-500/20">
                                            {t(`workflowControl.kernelTypes.${opt}`) || opt}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    )}

                    {/* Runtime Node Form */}
                    {type === "runtime" && (
                        <div className="p-4 rounded-2xl border border-purple-500/20 bg-purple-500/5 shadow-[0_4px_25px_rgba(168,85,247,0.05)]">
                            <div className="flex items-center gap-3 mb-3 border-b border-purple-500/10 pb-2">
                                <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400">
                                    <Server className="w-4 h-4" />
                                </div>
                                <div>
                                    <h3 className="text-[10px] font-bold text-purple-400 uppercase tracking-widest">{t("workflowControl.sections.runtime")}</h3>
                                    <p className="text-[9px] text-purple-400/50 uppercase tracking-tight mt-0.5">{t("workflowControl.descriptions.runtime")}</p>
                                </div>
                            </div>
                            <Label htmlFor="runtime-services" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3.5 block px-0.5">{t("workflowControl.labels.runtimeServices")}</Label>
                            <div id="runtime-services" className="flex flex-wrap gap-2">
                                {((data as { runtime?: { services?: RuntimeService[] } })?.runtime?.services || []).map((svc: RuntimeService, idx: number) => (
                                    <span key={`svc-${idx}-${typeof svc === "object" ? idx : svc}`} className="text-xs font-mono bg-purple-500/20 text-purple-200 px-2 py-1.5 rounded border border-purple-500/40 shadow-[0_0_5px_rgba(168,85,247,0.2)]">
                                        {formatRuntimeService(svc)}
                                    </span>
                                ))}
                                {(!((data as { runtime?: { services?: string[] } })?.runtime?.services) || ((data as { runtime?: { services?: string[] } })?.runtime?.services?.length === 0)) && (
                                    <span className="text-xs text-muted-foreground">-</span>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Provider Node Form */}
                    {type === "provider" && (
                        <div className="p-4 rounded-2xl border border-orange-500/20 bg-orange-500/5 shadow-[0_4px_25px_rgba(249,115,22,0.05)]">
                            <div className="flex items-center gap-3 mb-3 border-b border-orange-500/10 pb-2">
                                <div className="p-2 rounded-lg bg-orange-500/10 text-orange-400">
                                    <Cloud className="w-4 h-4" />
                                </div>
                                <div>
                                    <h3 className="text-[10px] font-bold text-orange-400 uppercase tracking-widest">{t("workflowControl.sections.provider")}</h3>
                                    <p className="text-[9px] text-orange-400/50 uppercase tracking-tight mt-0.5">{t("workflowControl.descriptions.provider")}</p>
                                </div>
                            </div>
                            <Label htmlFor="provider" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">{t("workflowControl.labels.activeProvider")}</Label>
                            <Select
                                value={(data as { provider?: { active?: string } })?.provider?.active as string}
                                onValueChange={(val) => handleUpdate("provider", { active: val })}
                            >
                                <SelectTrigger id="provider" className="bg-slate-900/80 border-orange-500/30 text-orange-100 focus:ring-orange-500/50">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-orange-500/30 text-orange-100">
                                    {availableOptions.providers?.map(opt => (
                                        <SelectItem key={opt} value={opt} className="focus:bg-orange-500/20">
                                            {t(`workflowControl.providers.${opt}`) || opt}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    )}

                    {/* Embedding Node Form */}
                    {type === "embedding" && (
                        <div className="p-4 rounded-2xl border border-pink-500/20 bg-pink-500/5 shadow-[0_4px_25px_rgba(236,72,153,0.05)]">
                            <div className="flex items-center gap-3 mb-3 border-b border-pink-500/10 pb-2">
                                <div className="p-2 rounded-lg bg-pink-500/10 text-pink-400">
                                    <Database className="w-4 h-4" />
                                </div>
                                <div>
                                    <h3 className="text-[10px] font-bold text-pink-400 uppercase tracking-widest">{t("workflowControl.sections.embedding")}</h3>
                                    <p className="text-[9px] text-pink-400/50 uppercase tracking-tight mt-0.5">{t("workflowControl.descriptions.embedding")}</p>
                                </div>
                            </div>
                            <Label htmlFor="model" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">{t("workflowControl.labels.currentEmbedding")}</Label>
                            <Select
                                value={(data as Record<string, unknown>).model as string}
                                onValueChange={(val) => handleUpdate("model", val)}
                            >
                                <SelectTrigger id="model" className="bg-slate-900/80 border-pink-500/30 text-pink-100 focus:ring-pink-500/50">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-pink-500/30 text-pink-100">
                                    {availableOptions.models?.map(opt => (
                                        <SelectItem key={opt} value={opt} className="focus:bg-pink-500/20">
                                            {t(`workflowControl.embeddingModels.${opt}`) || opt}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    )}

                    {/* Generic / Raw Data Fallback */}
                    {!["decision", "intent", "provider", "kernel", "runtime", "embedding"].includes(type || "") && (
                        <div className="p-4 rounded-xl border border-slate-700 bg-slate-800/30">
                            <Label htmlFor="raw-data" className="text-slate-400 mb-2 block">{t("workflowControl.labels.rawData")}</Label>
                            <pre id="raw-data" className="text-xs bg-slate-950/80 p-3 rounded-lg border border-white/5 overflow-auto max-h-60 font-mono text-slate-300 shadow-inner">
                                {JSON.stringify(data, null, 2)}
                            </pre>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
