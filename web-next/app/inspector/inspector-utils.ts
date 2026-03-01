import type {
  FlowTrace,
  HistoryRequest,
  HistoryStep as HistoryStepType,
  Task,
} from "@/lib/types";

export type HistoryStep = HistoryStepType;

const CONTRACT_ERROR_TERMS = [
  "execution_contract_violation",
  "kernel_required",
  "kernel is required",
  "requirements_missing",
  "capability_required",
  "execution_precheck",
  "execution.precheck.failed",
  "missing=kernel",
];

export function sanitizeMermaidDiagram(value: string) {
  const cleaned = value.replaceAll(/\r?\n/g, "\n");
  const safeChars = new Set(
    Array.from(
      String.raw`abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,:/_-[]()>{}|#;\=+*"'"`,
    ),
  );
  let output = "";
  for (const char of cleaned) {
    if (char === "\n") {
      output += "\n";
      continue;
    }
    output += safeChars.has(char) ? char : " ";
  }
  return output;
}

export function decorateExecutionFailed(container: HTMLDivElement) {
  const svg = container.querySelector("svg");
  if (!svg) return;
  const textNodes = svg.querySelectorAll("text");
  textNodes.forEach((node) => {
    if (!node.textContent?.includes("execution.failed")) return;
    if (node.querySelector(".execution-failed-marker")) return;
    const marker = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "tspan",
    );
    marker.setAttribute("class", "execution-failed-marker");
    marker.setAttribute("dx", "6");
    marker.textContent = "✖";
    node.appendChild(marker);
  });
}

export function adjustMermaidSizing(container: HTMLDivElement) {
  const svg = container.querySelector("svg");
  if (!svg) return;
  const width = svg.getAttribute("width");
  const height = svg.getAttribute("height");
  if (width && height && !svg.getAttribute("viewBox")) {
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  }
  svg.removeAttribute("width");
  svg.removeAttribute("height");
  svg.style.width = "100%";
  svg.style.height = "100%";
  svg.style.display = "block";
  svg.style.maxWidth = "none";
  svg.style.maxHeight = "none";
}

export function autoFitDiagram(
  container: HTMLDivElement | null,
  setTransform: (
    x: number,
    y: number,
    scale: number,
    duration?: number,
    easing?: string,
  ) => void,
) {
  if (!container) return;
  const svg = container.querySelector("svg");
  if (!svg) return;
  const nodes = svg.querySelectorAll(".node");
  if (nodes.length === 0) return;
  let bbox: DOMRect | SVGRect;
  try {
    bbox = svg.getBBox();
  } catch {
    return;
  }
  if (!bbox.width || !bbox.height) return;
  const padding = 96;
  const availableWidth = Math.max(container.clientWidth - padding, 100);
  const availableHeight = Math.max(container.clientHeight - padding, 100);
  const scale = Math.min(availableWidth / bbox.width, availableHeight / bbox.height);
  const targetScale = Math.max(Math.min(scale, 3), 0.2);
  const offsetX =
    -bbox.x * targetScale + (container.clientWidth - bbox.width * targetScale) / 2;
  const offsetY =
    -bbox.y * targetScale + (container.clientHeight - bbox.height * targetScale) / 2;
  setTransform(offsetX, offsetY, targetScale, 200, "easeOut");
}

const isExecutionContractStep = (step: HistoryStep) => {
  const content = `${step.action ?? ""} ${step.details ?? ""}`.toLowerCase();
  if (content.includes("execution_contract_violation")) return true;
  return CONTRACT_ERROR_TERMS.some((term) => content.includes(term));
};

export const filterSteps = (
  steps: HistoryStep[],
  query: string,
  contractOnly: boolean,
) => {
  const normalizedQuery = query.trim().toLowerCase();
  const textMatch = (step: HistoryStep) =>
    `${step.component ?? ""} ${step.action ?? ""} ${step.details ?? ""}`
      .toLowerCase()
      .includes(normalizedQuery);
  const contractMatch = (step: HistoryStep) => isExecutionContractStep(step);

  return steps.filter((step) => {
    if (contractOnly && !contractMatch(step)) return false;
    if (!normalizedQuery) return true;
    return textMatch(step);
  });
};

export function buildSequenceDiagram(flow?: FlowTrace | null) {
  if (!flow) {
    return [
      "sequenceDiagram",
      "    autonumber",
      "    Note over User: Brak danych requestu",
    ].join("\n");
  }

  const steps = flow.steps || [];
  const lines: string[] = ["sequenceDiagram", "    autonumber"];
  const participants = new Set<string>(["User", "Orchestrator"]);

  steps.forEach((step) => {
    const component = sanitizeSequenceText(step.component || "");
    if (component && component !== "User") {
      participants.add(component);
    }
  });

  const participantAliases = new Map<string, string>();
  let participantIndex = 0;
  participants.forEach((participant) => {
    const alias = createParticipantAlias(participant, participantIndex++);
    participantAliases.set(participant, alias);
    if (participant === "User" || participant === "Orchestrator") {
      lines.push(`    participant ${alias} as ${participant}`);
    } else {
      const display = participant.replaceAll('"', "'");
      lines.push(`    participant ${alias} as "${display}"`);
    }
  });

  lines.push("");
  const prompt = truncateText(sanitizeSequenceText(flow.prompt || "Zapytanie"), 70);
  const userAlias = participantAliases.get("User") ?? "User";
  const orchestratorAlias = participantAliases.get("Orchestrator") ?? "Orchestrator";
  lines.push(`    ${userAlias}->>${orchestratorAlias}: ${prompt || "Zapytanie"}`);

  let lastComponent = orchestratorAlias;
  steps.forEach((step) => {
    const componentName = sanitizeSequenceText(step.component || "");
    const componentAlias = componentName
      ? participantAliases.get(componentName) || participantAliases.get("Orchestrator")
      : lastComponent;
    const component = componentAlias ?? lastComponent;
    const action = truncateText(
      sanitizeSequenceText(step.action || step.details || "Krok"),
      80,
    );
    const details = truncateText(sanitizeSequenceText(step.details || ""), 80);

    if (step.is_decision_gate || component.toLowerCase() === "decisiongate") {
      const message = details ? `${action}: ${details}` : action;
      lines.push(`    Note over ${component}: 🔀 ${message || "Decision Gate"}`);
      return;
    }

    const message = details ? `${action}: ${details}` : action;
    const arrow = statusToArrow(step.status);
    if (component === lastComponent) {
      lines.push(`    Note right of ${component}: ${message}`);
    } else {
      lines.push(`    ${lastComponent}${arrow}${component}: ${message}`);
      lastComponent = component;
    }
  });

  if (flow.status === "COMPLETED") {
    lines.push(`    ${lastComponent}->>${userAlias}: ✅ Task completed`);
  } else if (flow.status === "FAILED") {
    lines.push(`    ${lastComponent}--x${userAlias}: ❌ Task failed`);
  } else if (flow.status === "PROCESSING") {
    lines.push(`    Note over ${lastComponent}: ⏳ Processing...`);
  }

  return lines.join("\n");
}

function createParticipantAlias(participant: string, index: number) {
  const base = participant.replaceAll(/[^a-zA-Z0-9]/g, "_") || `P${index + 1}`;
  return `${base}_${index + 1}`;
}

function sanitizeSequenceText(value?: string | null) {
  if (!value) return "";
  return value
    .replaceAll(/[<>]/g, "")
    .replaceAll(/[\r\n]/g, " ")
    .replaceAll("|", "‖")
    .replaceAll("--", "–")
    .replaceAll('"', "'")
    .trim();
}

function truncateText(value: string, limit: number) {
  if (!value) return "";
  return value.length > limit ? `${value.slice(0, limit)}...` : value;
}

function statusToArrow(status?: string) {
  if (!status) return "->>";
  const normalized = status.toLowerCase();
  if (normalized.includes("fail") || normalized.includes("error")) {
    return "--x";
  }
  return "->>";
}

export function buildFlowchartDiagram(steps: HistoryStep[]) {
  if (!steps.length) {
    return "graph TD\nA[Brak kroków]";
  }
  const lines = [
    "graph TD",
    "classDef success fill:#052e1a,stroke:#22c55e,color:#d1fae5",
    "classDef failed fill:#331010,stroke:#f87171,color:#fee2e2",
    "classDef running fill:#0f172a,stroke:#38bdf8,color:#e0f2fe",
    "classDef default fill:#111827,stroke:#475569,color:#f8fafc",
    "classDef decision fill:#1f2937,stroke:#facc15,color:#fde68a,stroke-dasharray:5 5",
    "classDef note fill:#1c1917,stroke:#fbbf24,color:#fef3c7",
    "classDef contract fill:#2a1116,stroke:#fb7185,color:#ffe4e6",
  ];
  steps.forEach((step, idx) => {
    const nodeId = `S${idx}`;
    const safeComponent = sanitizeMermaidText(step.component || `Step ${idx + 1}`);
    const safeAction = sanitizeMermaidText(step.action || step.details || "");
    const label = safeAction
      ? String.raw`${safeComponent}\n${safeAction}`
      : safeComponent;
    const statusClass = isExecutionContractStep(step)
      ? "contract"
      : statusToMermaidClass(step.status);
    const isDecision = (step.details || step.action || "")
      .toLowerCase()
      .includes("decision");
    lines.push(`${nodeId}["${label}"]:::${isDecision ? "decision" : statusClass}`);
    if (idx > 0) {
      const edgeLabel = sanitizeMermaidText(steps[idx - 1]?.status || "");
      const edgeText = edgeLabel ? `|${edgeLabel}|` : "";
      lines.push(`S${idx - 1} -->${edgeText} ${nodeId}`);
    }
    if (step.details && step.details.length > 80) {
      const noteId = `${nodeId}_note`;
      lines.push(
        `${noteId}["${sanitizeMermaidText(step.details, 90)}"]:::note`,
        `${nodeId} -.-> ${noteId}`,
      );
    }
  });
  return lines.join("\n");
}

function sanitizeMermaidText(value: string, limit = 60) {
  return value.replaceAll(/[\n\r"]/g, " ").trim().slice(0, limit);
}

function statusToMermaidClass(status?: string) {
  if (!status) return "default";
  const normalized = status.toLowerCase();
  if (normalized.includes("success") || normalized.includes("complete"))
    return "success";
  if (normalized.includes("fail") || normalized.includes("error")) return "failed";
  if (normalized.includes("process") || normalized.includes("run")) return "running";
  return "default";
}

export function formatErrorDetails(details: Record<string, unknown>): string[] {
  const entries: string[] = [];
  Object.entries(details).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    if (Array.isArray(value)) {
      if (value.length === 0) return;
      entries.push(`${key}: ${value.join(", ")}`);
      return;
    }
    if (typeof value === "object") {
      try {
        entries.push(`${key}: ${JSON.stringify(value)}`);
      } catch (err) {
        console.warn(`Failed to stringify object for key "${key}":`, err);
        entries.push(`${key}: [object]`);
      }
      return;
    }
    if (
      typeof value === "string" ||
      typeof value === "number" ||
      typeof value === "boolean" ||
      typeof value === "bigint"
    ) {
      entries.push(`${key}: ${String(value)}`);
      return;
    }
    entries.push(`${key}: [unserializable]`);
  });
  return entries.slice(0, 6);
}

export function buildInspectorStats(
  history: HistoryRequest[] | null | undefined,
  tasks?: Task[] | null,
) {
  const requests = history || [];
  const total = requests.length;
  const completed = requests.filter((req) => req.status === "COMPLETED").length;
  const failed = requests.filter((req) => req.status === "FAILED").length;
  const processing = requests.filter((req) => req.status === "PROCESSING").length;
  const durations = requests
    .map((req) => req.duration_seconds ?? 0)
    .filter((value) => value > 0);
  const avgDuration = durations.length
    ? durations.reduce((sum, value) => sum + value, 0) / durations.length
    : 0;
  const successRate = total ? Math.round((completed / Math.max(total, 1)) * 100) : 0;
  return {
    total,
    completed,
    failed,
    processing,
    avgDuration,
    successRate,
    activeTasks: tasks?.length ?? 0,
  };
}

export function buildTaskBreakdown(tasks?: Task[] | null) {
  if (!tasks || tasks.length === 0) return [];
  const summary: Record<string, number> = {};
  tasks.forEach((task) => {
    const key = task.status || "UNKNOWN";
    summary[key] = (summary[key] || 0) + 1;
  });
  return Object.entries(summary).map(([status, count]) => ({ status, count }));
}

export function formatDuration(durationSeconds: number | null | undefined) {
  if (!durationSeconds || durationSeconds <= 0) return "—";
  const minutes = Math.floor(durationSeconds / 60);
  const seconds = Math.floor(durationSeconds % 60);
  if (minutes === 0) {
    return `${seconds}s`;
  }
  return `${minutes}m ${seconds.toString().padStart(2, "0")}s`;
}

export function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
