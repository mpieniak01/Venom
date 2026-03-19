import type { SystemState, WorkflowControlOptions } from "@/types/workflow-control";

type SourceType = "local" | "cloud";

export type PropertyPanelOptions = {
	strategies: string[];
	intentModes: string[];
	kernels: string[];
	providers: string[];
	models: string[];
	providersBySource: { local: string[]; cloud: string[] };
	modelsBySource: { local: string[]; cloud: string[] };
	kernelRuntimes: Record<string, string[]>;
	intentRequirements: Record<string, { requires_embedding?: boolean; min_model_size?: string }>;
	providerEmbeddings: Record<string, string[]>;
	embeddingProviders: Record<string, string[]>;
};

function mergeUnique(values: Array<string | undefined | null>): string[] {
	const normalized = values
		.map((value) => (typeof value === "string" ? value.trim() : ""))
		.filter((value) => value.length > 0);
	return [...new Set(normalized)];
}

function normalizeSourceType(value: unknown): SourceType {
	if (typeof value !== "string") return "local";
	const normalized = value.trim().toLowerCase();
	if (normalized === "cloud") return "cloud";
	return "local";
}

function withCurrent(options: string[], current: unknown): string[] {
	if (typeof current !== "string" || current.trim().length === 0) return options;
	const currentValue = current.trim();
	if (options.includes(currentValue)) return options;
	return [currentValue, ...options];
}

function flattenBySource(catalog: { local?: string[]; cloud?: string[] }): string[] {
	return mergeUnique([...(catalog.local ?? []), ...(catalog.cloud ?? [])]);
}

export function buildPropertyPanelOptions(
	controlOptions: WorkflowControlOptions | null,
	systemState: SystemState | null,
	draftState: SystemState | null
): PropertyPanelOptions {
	const providerActive = draftState?.provider?.active ?? systemState?.provider?.active;
	const providerSource =
		draftState?.provider?.sourceType ??
		draftState?.provider_source ??
		systemState?.provider?.sourceType ??
		systemState?.provider_source;
	const embeddingActive = draftState?.embedding_model ?? systemState?.embedding_model;
	const embeddingSource =
		draftState?.embedding_source ??
		systemState?.embedding_source;

	const providersBySource = {
		local: [...(controlOptions?.providers?.local ?? [])],
		cloud: [...(controlOptions?.providers?.cloud ?? [])],
	};
	const modelsBySource = {
		local: [...(controlOptions?.embeddings?.local ?? [])],
		cloud: [...(controlOptions?.embeddings?.cloud ?? [])],
	};

	if (providerActive) {
		const key = normalizeSourceType(providerSource);
		providersBySource[key] = withCurrent(providersBySource[key], providerActive);
	}
	if (embeddingActive) {
		const key = normalizeSourceType(embeddingSource);
		modelsBySource[key] = withCurrent(modelsBySource[key], embeddingActive);
	}

	const strategies = mergeUnique([
		...(controlOptions?.decision_strategies ?? []),
		draftState?.decision_strategy,
		systemState?.decision_strategy,
	]);
	const intentModes = mergeUnique([
		...(controlOptions?.intent_modes ?? []),
		draftState?.intent_mode,
		systemState?.intent_mode,
	]);
	const kernels = mergeUnique([
		...(controlOptions?.kernels ?? []),
		draftState?.kernel,
		systemState?.kernel,
	]);

	return {
		strategies,
		intentModes,
		kernels,
		providersBySource,
		modelsBySource,
		providers: flattenBySource(providersBySource),
		models: flattenBySource(modelsBySource),
		kernelRuntimes: controlOptions?.kernel_runtimes ?? {},
		intentRequirements: controlOptions?.intent_requirements ?? {},
		providerEmbeddings: controlOptions?.provider_embeddings ?? {},
		embeddingProviders: controlOptions?.embedding_providers ?? {},
	};
}

export function getCompatibleKernels(
	options: PropertyPanelOptions,
	runtime: string | null | undefined
): string[] {
	if (!runtime) return options.kernels;
	return options.kernels.filter((kernel) => {
		const compatibleRuntimes = options.kernelRuntimes[kernel];
		if (!compatibleRuntimes || compatibleRuntimes.length === 0) return true;
		return compatibleRuntimes.includes(runtime);
	});
}

export function getCompatibleIntentModes(
	options: PropertyPanelOptions,
	hasEmbedding: boolean
): string[] {
	return options.intentModes.filter((intentMode) => {
		const requirements = options.intentRequirements[intentMode];
		if (!requirements) return true;
		if (requirements.requires_embedding && !hasEmbedding) return false;
		return true;
	});
}

export function getCompatibleProviders(
	options: PropertyPanelOptions,
	source: SourceType,
	embeddingModel: string | null | undefined
): string[] {
	const candidates = options.providersBySource[source] ?? [];
	if (!embeddingModel) return candidates;
	const compatibleProviders = options.embeddingProviders[embeddingModel];
	if (!compatibleProviders || compatibleProviders.length === 0) return candidates;
	return candidates.filter((provider) => compatibleProviders.includes(provider));
}

export function getCompatibleEmbeddings(
	options: PropertyPanelOptions,
	source: SourceType,
	provider: string | null | undefined
): string[] {
	const candidates = options.modelsBySource[source] ?? [];
	if (!provider) return candidates;
	const compatibleEmbeddings = options.providerEmbeddings[provider];
	if (!compatibleEmbeddings || compatibleEmbeddings.length === 0) return candidates;
	return candidates.filter((embedding) => compatibleEmbeddings.includes(embedding));
}
