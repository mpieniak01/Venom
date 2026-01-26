"use client";

import {
    useMetrics,
    useTasks,
    useQueueStatus,
    useServiceStatus,
    useLlmServers,
    useActiveLlmServer,
    useGraphSummary,
    useModels,
    useGitStatus,
    useTokenMetrics,
    useHistory,
    useLearningLogs,
    useFeedbackLogs,
    useModelsUsage,
} from "@/hooks/use-api";
import type { CockpitInitialData } from "@/lib/server-data";

export function useCockpitData(initialData: CockpitInitialData) {
    // Metrics
    const {
        data: liveMetrics,
        loading: metricsLoading,
        refresh: refreshMetrics,
    } = useMetrics(30000);
    const metrics = liveMetrics ?? initialData.metrics ?? null;

    // Tasks
    const { data: liveTasks, refresh: refreshTasks } = useTasks(30000);
    const tasks = liveTasks ?? initialData.tasks ?? null;

    // Queue
    const {
        data: liveQueue,
        loading: queueLoading,
        refresh: refreshQueue,
    } = useQueueStatus(10000);
    const queue = liveQueue ?? initialData.queue ?? null;

    // Services
    const { data: liveServices, refresh: refreshServices } = useServiceStatus(30000);
    const services = liveServices ?? initialData.services ?? null;

    // LLM Servers
    const {
        data: liveLlmServers,
        loading: llmServersLoading,
        refresh: refreshLlmServers,
    } = useLlmServers();
    const llmServers = liveLlmServers ?? [];

    const { data: liveActiveServer, refresh: refreshActiveServer } =
        useActiveLlmServer(30000);
    const activeServerInfo = liveActiveServer ?? null;

    // Graph
    const { data: liveGraph } = useGraphSummary();
    const graph = liveGraph ?? initialData.graphSummary ?? null;

    // Models
    const { data: liveModels, refresh: refreshModels } = useModels();
    const models = liveModels ?? initialData.models ?? null;

    // Git
    const { data: liveGit, refresh: refreshGit } = useGitStatus(30000);
    const git = liveGit ?? initialData.gitStatus ?? null;

    // Token Metrics
    const {
        data: liveTokenMetrics,
        loading: tokenMetricsLoading,
        refresh: refreshTokenMetrics,
    } = useTokenMetrics(30000);
    const tokenMetrics = liveTokenMetrics ?? initialData.tokenMetrics ?? null;

    // History
    const {
        data: liveHistory,
        loading: historyLoading,
        refresh: refreshHistory,
    } = useHistory(6, 30000);
    const history = liveHistory ?? initialData.history ?? null;

    // Learning Logs
    const {
        data: learningLogs,
        loading: learningLoading,
        error: learningError,
    } = useLearningLogs(6);

    // Feedback Logs
    const {
        data: feedbackLogs,
        loading: feedbackLoading,
        error: feedbackError,
    } = useFeedbackLogs(6);

    // Models Usage
    const { data: liveModelsUsageResponse, refresh: refreshModelsUsage } =
        useModelsUsage(30000);
    const modelsUsageResponse =
        liveModelsUsageResponse ?? initialData.modelsUsage ?? null;

    const findTaskMatch = (requestId?: string, prompt?: string | null) => {
        if (!tasks) return null;
        if (requestId) {
            const found = tasks.find((t) => t.task_id === requestId || t.id === requestId);
            if (found) return found;
        }
        if (prompt) {
            return tasks.find((t) => t.content === prompt) || null;
        }
        return null;
    };

    return {
        metrics,
        tasks,
        queue,
        services,
        llmServers,
        activeServerInfo,
        graph,
        models,
        git,
        tokenMetrics,
        history,
        learningLogs,
        feedbackLogs,
        modelsUsageResponse,
        findTaskMatch,
        loading: {
            metrics: metricsLoading,
            queue: queueLoading,
            llmServers: llmServersLoading,
            tokenMetrics: tokenMetricsLoading,
            history: historyLoading,
            learning: learningLoading,
            feedback: feedbackLoading,
        },
        refresh: {
            metrics: refreshMetrics,
            tasks: refreshTasks,
            queue: refreshQueue,
            services: refreshServices,
            llmServers: refreshLlmServers,
            activeServer: refreshActiveServer,
            models: refreshModels,
            git: refreshGit,
            tokenMetrics: refreshTokenMetrics,
            history: refreshHistory,
            modelsUsage: refreshModelsUsage,
        },
    };
}
