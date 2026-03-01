"use client";

type HistoryEntryLike = {
  role?: string;
  content?: string;
  request_id?: string;
  timestamp?: string;
  pending?: boolean;
  status?: string | null;
  contextUsed?: { lessons?: string[]; memory_entries?: string[] } | null;
  session_id?: string;
  policy_blocked?: boolean;
  reason_code?: string | null;
  user_message?: string | null;
};

type StreamLike = {
  result?: string;
  status?: string;
  contextUsed?: { lessons?: string[]; memory_entries?: string[] } | null;
};

type HistoryTaskLike = {
  request_id: string;
  status?: string | null;
  session_id?: string | null;
};

type TaskDetailLike = {
  result?: string | null;
  created_at?: string | null;
  context_history?: { session?: { session_id?: string } };
};

type FeedbackValue = { rating?: "up" | "down" | null; comment?: string };
type ContextPreviewMeta = {
  preview: string | null;
  truncated: boolean;
  hiddenPrompts: number | null;
  mode: string | null;
};
type TaskDetailStep = {
  component?: string;
  action?: string;
  details?: string | null;
};

const mapRole = (role: string | undefined): "user" | "assistant" => {
  if (role === "assistant") return "assistant";
  return "user";
};

const execPattern = (pattern: RegExp, value: string) => pattern.exec(value);

const resolvePreviewFromContext = (ctx: Record<string, unknown>) => {
  if (typeof ctx.preview === "string") return ctx.preview;
  if (typeof ctx.prompt_context_preview === "string")
    return ctx.prompt_context_preview;
  return null;
};

const parseContextStepDetails = (details: string): ContextPreviewMeta | null => {
  if (details.startsWith("{")) {
    try {
      const parsed = JSON.parse(details) as Record<string, unknown>;
      return {
        preview:
          (parsed.preview as string) ||
          (parsed.context as string) ||
          (parsed.prompt as string) ||
          (parsed.prompt_context_preview as string) ||
          null,
        truncated: !!parsed.truncated || !!parsed.prompt_context_truncated,
        hiddenPrompts:
          typeof parsed.hidden_prompts_count === "number"
            ? parsed.hidden_prompts_count
            : null,
        mode: typeof parsed.mode === "string" ? parsed.mode : null,
      };
    } catch {
      return null;
    }
  }
  const previewMatch = execPattern(
    /(?:preview|prompt|context|prompt_context_preview)=([\s\S]*?)(?:$|\s\w+=)/,
    details
  );
  const hiddenMatch = execPattern(/hidden_prompts_count=(\d+)/, details);
  const modeMatch = execPattern(/mode=(\w+)/, details);
  if (!previewMatch && !hiddenMatch) return null;
  return {
    preview: previewMatch ? previewMatch[1].trim() : null,
    truncated:
      details.includes("truncated=true") || details.includes('truncated":true'),
    hiddenPrompts: hiddenMatch ? Number.parseInt(hiddenMatch[1], 10) : null,
    mode: modeMatch ? modeMatch[1] : null,
  };
};

const parseLlmStepDetails = (details: string): ContextPreviewMeta | null => {
  if (details.startsWith("{")) {
    try {
      const parsed = JSON.parse(details) as Record<string, unknown>;
      return {
        preview:
          (parsed.prompt as string) ||
          (parsed.payload as string) ||
          (parsed.input as string) ||
          null,
        truncated: false,
        hiddenPrompts: null,
        mode: null,
      };
    } catch {
      return null;
    }
  }
  const promptMatch = execPattern(
    /(?:prompt|payload|input)=([\s\S]*?)(?:$|\s\w+=)/,
    details
  );
  if (!promptMatch) return null;
  return {
    preview: promptMatch[1].trim(),
    truncated: false,
    hiddenPrompts: null,
    mode: null,
  };
};

const isContextStep = (step: TaskDetailStep) =>
  step.component === "ContextBuilder" ||
  step.action === "context_preview" ||
  step.details?.includes("preview=") ||
  step.details?.includes('preview"') ||
  step.details?.includes("prompt_context_preview");

const isHiddenPromptsStep = (step: TaskDetailStep) =>
  step.action === "hidden_prompts" ||
  step.details?.includes("hidden_prompts") ||
  step.details?.includes("hiddenPrompts");

const isLlmStep = (step: TaskDetailStep) =>
  (step.component === "LLM" && step.action === "start") ||
  (step.component === "ChatAgent" && step.action === "process_task") ||
  step.details?.includes("prompt=") ||
  step.details?.includes("payload=") ||
  step.details?.includes("input=");

const extractHiddenPrompts = (details: string) => {
  const hiddenMatch =
    execPattern(/hidden_prompts:?\s*(\d+)/i, details) ||
    execPattern(/hidden_prompts_count=(\d+)/, details);
  if (!hiddenMatch) return null;
  return Number.parseInt(hiddenMatch[1], 10);
};

const parseContextPreviewFromSteps = (steps: TaskDetailStep[]) => {
  const contextStep = steps.find(isContextStep);
  const hiddenStep = steps.find(isHiddenPromptsStep);
  let meta = contextStep?.details
    ? parseContextStepDetails(contextStep.details.trim())
    : null;

  if (!meta && contextStep === undefined) {
    const llmStep = steps.find(isLlmStep);
    if (llmStep?.details) {
      meta = parseLlmStepDetails(llmStep.details.trim());
    }
  }

  if (!hiddenStep?.details) return meta;
  const hiddenPrompts = extractHiddenPrompts(hiddenStep.details);
  if (hiddenPrompts === null) return meta;

  return {
    ...(meta ?? {
      preview: null,
      truncated: false,
      mode: null,
      hiddenPrompts: null,
    }),
    hiddenPrompts,
  };
};

export function mergeStreamsIntoHistory(
  deduped: HistoryEntryLike[],
  taskStreams: Record<string, StreamLike>
) {
  Object.entries(taskStreams).forEach(([taskId, stream]) => {
    const content = stream.result || "";
    const isPending =
      stream.status === "PROCESSING" || stream.status === "PENDING";
    const index = deduped.findIndex(
      (entry) => entry.request_id === taskId && entry.role === "assistant"
    );

    if (index !== -1) {
      if (content && content.length > (deduped[index].content?.length || 0)) {
        deduped[index] = {
          ...deduped[index],
          content,
          pending: isPending,
          status: stream.status,
          contextUsed: stream.contextUsed ?? deduped[index].contextUsed,
        };
      } else if (isPending && !deduped[index].pending) {
        deduped[index] = {
          ...deduped[index],
          pending: true,
          status: stream.status,
          contextUsed: stream.contextUsed ?? deduped[index].contextUsed,
        };
      }
      return;
    }

    if (content || isPending) {
      deduped.push({
        role: "assistant",
        content,
        request_id: taskId,
        timestamp: new Date().toISOString(),
        pending: isPending,
        status: stream.status,
        contextUsed: stream.contextUsed ?? undefined,
      });
    }
  });
}

export function toHistoryMessages(entries: HistoryEntryLike[]) {
  return entries.map((entry, index) => {
    const fallbackId = `msg-${index}-${entry.timestamp}`;
    const uniqueId = entry.request_id
      ? `${entry.request_id}-${entry.role}`
      : fallbackId;
    return {
      bubbleId: uniqueId,
      role: mapRole(entry.role),
      text: entry.content || "",
      requestId: entry.request_id ?? null,
      timestamp: entry.timestamp ?? "",
      pending: entry.pending || false,
      status: entry.status || null,
      contextUsed: entry.contextUsed ?? null,
      policyBlocked: entry.policy_blocked ?? false,
      reasonCode: entry.reason_code ?? null,
      userMessage: entry.user_message ?? null,
    };
  });
}

export function parseContextPreviewMeta(
  selectedTask: { context_history?: Record<string, unknown> } | null,
  detail: { steps?: TaskDetailStep[] } | null
) {
  const ctx = selectedTask?.context_history;
  const preview = ctx ? resolvePreviewFromContext(ctx) : null;
  if (preview) {
    return {
      preview,
      truncated: !!ctx?.truncated || !!ctx?.prompt_context_truncated,
      hiddenPrompts:
        typeof ctx?.hidden_prompts_count === "number"
          ? ctx.hidden_prompts_count
          : null,
      mode: typeof ctx?.mode === "string" ? ctx.mode : null,
    };
  }

  const steps = detail?.steps;
  if (!steps) return null;
  return parseContextPreviewFromSteps(steps);
}

export function shouldHydrateCompletedTask(
  task: HistoryTaskLike,
  sessionId: string | null,
  hydratedIds: Set<string>,
  localSessionHistory: HistoryEntryLike[],
  taskStreams: Record<string, StreamLike>
): boolean {
  if (task.status !== "COMPLETED") return false;
  if (!sessionId || task.session_id !== sessionId) return false;
  if (hydratedIds.has(task.request_id)) return false;
  const hasAssistantMessage = localSessionHistory.some(
    (msg) =>
      msg.request_id === task.request_id && msg.role === "assistant" && msg.content
  );
  if (hasAssistantMessage) return false;
  const stream = taskStreams[task.request_id];
  return !stream?.result;
}

function upsertHydratedAssistantMessage(
  prev: HistoryEntryLike[],
  requestId: string,
  content: string,
  timestamp: string
): HistoryEntryLike[] {
  if (prev.some((entry) => entry.request_id === requestId && entry.role === "assistant")) {
    return prev;
  }
  return [
    ...prev,
    {
      role: "assistant",
      content,
      request_id: requestId,
      timestamp,
    },
  ].sort(
    (a, b) =>
      new Date(a.timestamp || 0).getTime() - new Date(b.timestamp || 0).getTime()
  );
}

export async function hydrateCompletedTask(input: {
  requestId: string;
  sessionId: string;
  setLocalSessionHistory: (
    updater: (prev: HistoryEntryLike[]) => HistoryEntryLike[]
  ) => void;
  fetchTaskDetailFn: (requestId: string) => Promise<unknown>;
}) {
  const { requestId, sessionId, setLocalSessionHistory, fetchTaskDetailFn } = input;
  try {
    const taskDetail = await fetchTaskDetailFn(requestId);
    const detail = taskDetail as TaskDetailLike;
    const detailSession = detail.context_history?.session?.session_id ?? null;
    if (detailSession && detailSession !== sessionId) return;
    if (!detail.result) return;
    setLocalSessionHistory((prev) =>
      upsertHydratedAssistantMessage(
        prev,
        requestId,
        detail.result || "",
        detail.created_at || new Date().toISOString()
      )
    );
  } catch (err: unknown) {
    if (
      (err as { status?: number })?.status !== 404 &&
      !(err as { message?: string })?.message?.includes("404")
    ) {
      console.error("Failed to hydrate task", requestId, err);
    }
  }
}

export function extractFeedbackUpdates(
  history:
    | Array<{
        request_id?: string;
        feedback?: { rating?: string; comment?: string | null } | null;
      }>
    | null
    | undefined,
  detail:
    | {
        request_id?: string;
        feedback?: { rating?: string; comment?: string | null } | null;
      }
    | null
    | undefined
): Record<string, FeedbackValue> {
  const updates: Record<string, FeedbackValue> = {};
  if (history) {
    history.forEach((item) => {
      if (item.feedback && item.request_id) {
        updates[item.request_id] = {
          rating: item.feedback.rating as "up" | "down",
          comment: item.feedback.comment ?? undefined,
        };
      }
    });
  }
  if (detail?.feedback && detail.request_id) {
    updates[detail.request_id] = {
      rating: detail.feedback.rating as "up" | "down",
      comment: detail.feedback.comment ?? undefined,
    };
  }
  return updates;
}

export function mergeFeedbackUpdates(
  prev: Record<string, FeedbackValue>,
  updates: Record<string, FeedbackValue>
): Record<string, FeedbackValue> {
  const copy = { ...prev };
  let changed = false;
  for (const [id, value] of Object.entries(updates)) {
    if (prev[id]?.rating !== value.rating || prev[id]?.comment !== value.comment) {
      copy[id] = value;
      changed = true;
    }
  }
  return changed ? copy : prev;
}

export type {
  ContextPreviewMeta,
  FeedbackValue,
  HistoryEntryLike,
  HistoryTaskLike,
  StreamLike,
  TaskDetailLike,
  TaskDetailStep,
};
