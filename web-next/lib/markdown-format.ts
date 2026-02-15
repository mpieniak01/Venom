const CODE_FENCE_REGEX = /```[\s\S]*?```/g;
const MATH_BLOCK_REGEX = /\$\$([\s\S]+?)\$\$/g;
const MATH_DISPLAY_REGEX = /\\\[((?:.|\n)+?)\\\]/g;
const MATH_INLINE_REGEX = /\\\(((?:.|\n)+?)\\\)/g;
const MATH_HINT_REGEX = /(?:=|\^|\\frac|\\sqrt|sqrt\(|≤|≥|<|>)/;
const MATH_ALLOWED_REGEX = /^[-0-9a-zA-Z\s+*/=^_().,:√π∑∫<>≤≥\\]+$/;

export function formatComputationContent(content: string) {
  let replaced = false;
  const withBlocks = content.replaceAll(/```(?:json)?\n([\s\S]*?)```/g, (match, block) => {
    const candidate = block.trim();
    if (!candidate) return match;
    try {
      const parsed = JSON.parse(candidate) as unknown;
      replaced = true;
      return formatJsonValue(parsed);
    } catch {
      return match;
    }
  });
  if (replaced) {
    return withBlocks;
  }
  const candidate = extractJsonCandidate(content);
  if (!candidate) {
    return content;
  }
  try {
    const parsed = JSON.parse(candidate) as unknown;
    return formatJsonValue(parsed);
  } catch {
    return content;
  }
}

export function isComputationContent(content: string) {
  const fenceMatch = /```(?:json)?\n([\s\S]*?)```/.exec(content);
  if (fenceMatch?.[1]) {
    try {
      JSON.parse(fenceMatch[1].trim());
      return true;
    } catch {
      return false;
    }
  }
  const candidate = extractJsonCandidate(content);
  if (!candidate) {
    return false;
  }
  try {
    JSON.parse(candidate);
    return true;
  } catch {
    return false;
  }
}

export function softlyWrapMathLines(content: string) {
  let output = "";
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  // Resetuj globalny regex przed użyciem
  CODE_FENCE_REGEX.lastIndex = 0;
  while ((match = CODE_FENCE_REGEX.exec(content))) {
    const segment = content.slice(lastIndex, match.index);
    output += wrapMathInSegment(segment);
    output += match[0];
    lastIndex = match.index + match[0].length;
  }
  output += wrapMathInSegment(content.slice(lastIndex));
  return output;
}

export function looksLikeMathLine(value: string) {
  if (/[.!?]/.test(value)) return false;
  if (/[ąćęłńóśźż]/i.test(value)) return false;
  if (!MATH_HINT_REGEX.test(value)) return false;
  if (!MATH_ALLOWED_REGEX.test(value)) return false;
  const wordCount = value.split(/\s+/).filter(Boolean).length;
  if (wordCount > 8) return false;
  return true;
}

export function tokenizeMath(input: string): { text: string; tokens: MathToken[] } {
  const tokens: MathToken[] = [];
  let output = "";
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  // Resetuj globalny regex przed użyciem
  CODE_FENCE_REGEX.lastIndex = 0;
  while ((match = CODE_FENCE_REGEX.exec(input))) {
    const segment = input.slice(lastIndex, match.index);
    output += replaceMathTokens(segment, tokens);
    output += match[0];
    lastIndex = match.index + match[0].length;
  }
  output += replaceMathTokens(input.slice(lastIndex), tokens);

  return { text: output, tokens };
}

type MathToken = {
  id: string;
  expression: string;
  display: boolean;
};

function wrapMathInSegment(segment: string) {
  // Resetuj globalny regex przed użyciem w metodach testowych
  MATH_BLOCK_REGEX.lastIndex = 0;
  MATH_DISPLAY_REGEX.lastIndex = 0;
  MATH_INLINE_REGEX.lastIndex = 0;

  return segment
    .split("\n")
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) return line;
      if (MATH_BLOCK_REGEX.test(trimmed)) return line;
      if (MATH_DISPLAY_REGEX.test(trimmed)) return line;
      if (MATH_INLINE_REGEX.test(trimmed)) return line;
      if (!looksLikeMathLine(trimmed)) return line;
      return `$$${trimmed}$$`;
    })
    .join("\n");
}

function replaceMathTokens(segment: string, tokens: MathToken[]) {
  let next = segment.replaceAll(MATH_BLOCK_REGEX, (_, expr: string) => {
    const id = `__MATH_BLOCK_${tokens.length}__`;
    tokens.push({ id, expression: expr.trim(), display: true });
    return id;
  });
  next = next.replaceAll(MATH_DISPLAY_REGEX, (_, expr: string) => {
    const id = `__MATH_DISPLAY_${tokens.length}__`;
    tokens.push({ id, expression: expr.trim(), display: true });
    return id;
  });
  next = next.replaceAll(MATH_INLINE_REGEX, (_, expr: string) => {
    const id = `__MATH_INLINE_${tokens.length}__`;
    tokens.push({ id, expression: expr.trim(), display: false });
    return id;
  });
  return next;
}

function extractJsonCandidate(content: string) {
  const trimmed = content.trim();
  if (trimmed.startsWith("```") && trimmed.endsWith("```")) {
    const match = /```[a-zA-Z]*\n([\s\S]*?)```/.exec(trimmed);
    if (match?.[1]) {
      return match[1].trim();
    }
  }
  if (
    (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
    (trimmed.startsWith("[") && trimmed.endsWith("]"))
  ) {
    return trimmed;
  }
  return null;
}

function formatJsonValue(value: unknown): string {
  if (Array.isArray(value)) {
    if (value.length === 0) return "Brak danych.";
    if (value.every((entry) => Array.isArray(entry))) {
      return formatTable(
        value.map((row) =>
          Array.isArray(row) ? row.map((cell) => formatCell(cell)) : [formatCell(row)],
        ),
      );
    }
    if (value.every((entry) => isPlainObject(entry))) {
      return formatObjectTable(value);
    }
    return value.map((item) => `- ${formatCell(item)}`).join("\n");
  }
  if (isPlainObject(value)) {
    return formatObjectTable([value]);
  }
  return String(value);
}

function formatTable(rows: string[][]): string {
  const maxCols = Math.max(...rows.map((row) => row.length));
  const headers = Array.from({ length: maxCols }, (_, idx) => `Col ${idx + 1}`);
  const normalized = rows.map((row) => {
    const next = [...row];
    while (next.length < maxCols) next.push("—");
    return next;
  });
  const headerLine = `| ${headers.join(" | ")} |`;
  const separator = `| ${headers.map(() => "---").join(" | ")} |`;
  const body = normalized.map((row) => `| ${row.join(" | ")} |`).join("\n");
  return [headerLine, separator, body].join("\n");
}

function formatObjectTable(objects: Record<string, unknown>[]): string {
  const keys = Array.from(new Set(objects.flatMap((obj) => Object.keys(obj))));
  const headerLine = `| ${keys.join(" | ")} |`;
  const separator = `| ${keys.map(() => "---").join(" | ")} |`;
  const body = objects
    .map((obj) => `| ${keys.map((key) => formatCell(obj[key])).join(" | ")} |`)
    .join("\n");
  return [headerLine, separator, body].join("\n");
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value.trim() || "—";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map((entry) => formatCell(entry)).join(", ");
  if (isPlainObject(value)) return JSON.stringify(value);
  return String(value);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
