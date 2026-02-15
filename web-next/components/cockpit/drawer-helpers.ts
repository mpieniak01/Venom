import type { HistoryRequestDetail, Task } from "@/lib/types";

export type FeedbackState = {
    rating?: "up" | "down" | null;
    comment?: string;
    message?: string | null;
};

export type SimpleResponse = {
    text: string;
    truncated: boolean;
};

export type ContextPreviewMeta = {
    preview?: string | null;
    truncated?: boolean | null;
    hiddenPrompts?: number | null;
    mode?: string | null;
};

export type RuntimeError = string | Record<string, unknown> | null;

export type RuntimeContext = {
    status: string | null;
    error: RuntimeError;
};

export type RuntimeErrorMeta = {
    errorClass: string | null;
    details: string[];
    promptPreview: string | null;
    promptContext: string | null;
    promptContextTruncated: boolean;
};

export const RUNTIME_ERROR_CLASSES = [
    "routing_mismatch",
    "execution_contract_violation",
    "provider_unreachable",
    "timeout",
    "rate_limited",
    "runtime_error",
    "agent_error",
    "validation_error",
    "cancelled",
] as const;

export function extractRuntimeContext(selectedTask: Task | null): RuntimeContext | null {
    const runtime = selectedTask?.context_history?.["llm_runtime"];
    if (!runtime || typeof runtime !== "object") return null;

    const ctx = runtime as Record<string, unknown>;
    const statusValue = ctx["status"];
    const errorValue = ctx["error"];

    return {
        status: typeof statusValue === "string" ? statusValue : null,
        error:
            typeof errorValue === "string" || (typeof errorValue === "object" && errorValue)
                ? (errorValue as string | Record<string, unknown>)
                : null,
    };
}

export function parseRuntimeErrorDetails(errorDetails: Record<string, unknown>): string[] {
    const details: string[] = [];
    const missing = errorDetails["missing"];
    if (Array.isArray(missing) && missing.length > 0) {
        details.push(`missing: ${missing[0]}`);
    }

    const expectedHash = errorDetails["expected_hash"];
    const actualHash = errorDetails["actual_hash"];
    if (typeof expectedHash === "string") details.push(`expected_hash: ${expectedHash.slice(0, 8)}`);
    if (typeof actualHash === "string") details.push(`actual_hash: ${actualHash.slice(0, 8)}`);

    const expectedRuntime = errorDetails["expected_runtime"];
    const actualRuntime = errorDetails["actual_runtime"];
    if (typeof expectedRuntime === "string") details.push(`expected_runtime: ${expectedRuntime}`);
    if (typeof actualRuntime === "string") details.push(`actual_runtime: ${actualRuntime}`);

    return details;
}

export function parseRuntimeTokenInfo(errorDetails: Record<string, unknown>): string | null {
    const tokenInfo: { max?: number; input?: number; requested?: number } = {};
    if (typeof errorDetails.max_context_tokens === "number") tokenInfo.max = errorDetails.max_context_tokens;
    if (typeof errorDetails.input_tokens === "number") tokenInfo.input = errorDetails.input_tokens;
    if (typeof errorDetails.requested_max_tokens === "number") tokenInfo.requested = errorDetails.requested_max_tokens;

    if (!tokenInfo.max && !tokenInfo.input && !tokenInfo.requested) return null;
    const parts: string[] = [];
    if (tokenInfo.max) parts.push(`max_ctx=${tokenInfo.max}`);
    if (tokenInfo.input) parts.push(`input=${tokenInfo.input}`);
    if (tokenInfo.requested) parts.push(`requested=${tokenInfo.requested}`);
    return `tokens: ${parts.join(" / ")}`;
}

export function parseRuntimeErrorMeta(error: RuntimeContext["error"]): RuntimeErrorMeta | null {
    if (!error) return null;

    if (typeof error === "string") {
        const errorClass = RUNTIME_ERROR_CLASSES.find((entry) => error.includes(entry)) ?? null;
        return {
            errorClass,
            details: [],
            promptPreview: null,
            promptContext: null,
            promptContextTruncated: false,
        };
    }

    const errorObj = error;
    const errorDetails =
        typeof errorObj.error_details === "object" && errorObj.error_details
            ? (errorObj.error_details as Record<string, unknown>)
            : {};
    const details = parseRuntimeErrorDetails(errorDetails);
    const tokenInfo = parseRuntimeTokenInfo(errorDetails);
    if (tokenInfo) details.push(tokenInfo);

    const stage = errorObj.stage;
    if (typeof stage === "string") details.push(`stage: ${stage}`);

    return {
        errorClass:
            (typeof errorObj.error_class === "string" && errorObj.error_class) ||
            (typeof errorObj.error_code === "string" && errorObj.error_code) ||
            null,
        details,
        promptPreview: typeof errorDetails.prompt_preview === "string" ? errorDetails.prompt_preview : null,
        promptContext: typeof errorDetails.prompt_context === "string" ? errorDetails.prompt_context : null,
        promptContextTruncated:
            typeof errorDetails.prompt_context_truncated === "boolean"
                ? errorDetails.prompt_context_truncated
                : false,
    };
}

export function parseSimpleResponse(historyDetail: HistoryRequestDetail | null) {
    if (!historyDetail) return null;
    if (historyDetail.result) return { text: historyDetail.result, truncated: false };
    if (!historyDetail.steps || historyDetail.steps.length === 0) return null;

    const responseStep = [...historyDetail.steps]
        .reverse()
        .find((step) => step.component === "SimpleMode" && step.action === "response");
    if (!responseStep?.details) return null;

    const raw = responseStep.details.trim();
    if (raw.startsWith("{")) {
        try {
            const parsed = JSON.parse(raw) as { response?: string; truncated?: boolean };
            if (typeof parsed.response === "string") {
                return { text: parsed.response, truncated: !!parsed.truncated };
            }
        } catch {
            return null;
        }
    }

    const responseMatch = /response=([\s\S]*)$/.exec(raw);
    if (responseMatch?.[1]) return { text: responseMatch[1].trim(), truncated: false };

    const previewMatch = /preview=([\s\S]*)$/.exec(raw);
    if (previewMatch?.[1]) return { text: previewMatch[1].trim(), truncated: true };

    return null;
}

export function resolveRequestModeLabel(
    contextPreviewMeta: ContextPreviewMeta | null | undefined,
    historyDetail: HistoryRequestDetail | null,
) {
    if (contextPreviewMeta?.mode === "direct") return "direct";
    if (contextPreviewMeta?.mode === "normal") return "normal";
    const hasSimple = historyDetail?.steps?.some(
        (step) => step.component === "SimpleMode",
    );
    return hasSimple ? "direct" : "normal";
}

export function formatDateTime(value?: string | null) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
}

export function formatDurationSeconds(value?: number | null) {
    if (!value || value <= 0) return "—";
    if (value < 60) return `${value.toFixed(1)}s`;
    const minutes = Math.floor(value / 60);
    const seconds = Math.floor(value % 60);
    return `${minutes}m ${seconds}s`;
}
