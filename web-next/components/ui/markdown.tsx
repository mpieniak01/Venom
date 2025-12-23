"use client";

import DOMPurify from "dompurify";
import katex from "katex";
import { marked } from "marked";
import { useEffect, useState } from "react";

type MarkdownPreviewProps = {
  content?: string | null;
  emptyState?: string;
  mode?: "final" | "stream";
};

export function MarkdownPreview({ content, emptyState, mode = "final" }: MarkdownPreviewProps) {
  const [html, setHtml] = useState<string>("");

  useEffect(() => {
    if (!content || content.trim().length === 0) {
      setHtml("");
      return;
    }

    try {
      const formatted =
        mode === "final" ? formatComputationContent(content) : content;
      const { text: tokenized, tokens } =
        mode === "final" ? tokenizeMath(formatted) : { text: formatted, tokens: [] };
      const rendered = marked(tokenized, { async: false });
      const withMath = tokens.length > 0 ? renderMathTokens(rendered, tokens) : rendered;
      const sanitized = DOMPurify.sanitize(withMath);
      setHtml(sanitized);
    } catch (err) {
      console.error("Markdown render error:", err);
      setHtml(DOMPurify.sanitize(content));
    }
  }, [content, mode]);

  if (!html) {
    return (
      <p className="text-sm text-[--color-muted]">
        {emptyState || "Brak treści do wyświetlenia."}
      </p>
    );
  }

  return (
    <div
      className="prose prose-invert max-w-none text-sm leading-relaxed"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

type MathToken = {
  id: string;
  expression: string;
  display: boolean;
};

const CODE_FENCE_REGEX = /```[\s\S]*?```/g;
const MATH_BLOCK_REGEX = /\$\$([\s\S]+?)\$\$/g;
const MATH_DISPLAY_REGEX = /\\\[((?:.|\n)+?)\\\]/g;
const MATH_INLINE_REGEX = /\\\(((?:.|\n)+?)\\\)/g;

function tokenizeMath(input: string): { text: string; tokens: MathToken[] } {
  const tokens: MathToken[] = [];
  let output = "";
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = CODE_FENCE_REGEX.exec(input))) {
    const segment = input.slice(lastIndex, match.index);
    output += replaceMathTokens(segment, tokens);
    output += match[0];
    lastIndex = match.index + match[0].length;
  }
  output += replaceMathTokens(input.slice(lastIndex), tokens);

  return { text: output, tokens };
}

function replaceMathTokens(segment: string, tokens: MathToken[]) {
  let next = segment.replace(MATH_BLOCK_REGEX, (_, expr: string) => {
    const id = `__MATH_BLOCK_${tokens.length}__`;
    tokens.push({ id, expression: expr.trim(), display: true });
    return id;
  });
  next = next.replace(MATH_DISPLAY_REGEX, (_, expr: string) => {
    const id = `__MATH_DISPLAY_${tokens.length}__`;
    tokens.push({ id, expression: expr.trim(), display: true });
    return id;
  });
  next = next.replace(MATH_INLINE_REGEX, (_, expr: string) => {
    const id = `__MATH_INLINE_${tokens.length}__`;
    tokens.push({ id, expression: expr.trim(), display: false });
    return id;
  });
  return next;
}

function renderMathTokens(html: string, tokens: MathToken[]) {
  let output = html;
  for (const token of tokens) {
    let rendered = "";
    try {
      rendered = katex.renderToString(token.expression, {
        displayMode: token.display,
        throwOnError: false,
      });
    } catch (err) {
      console.warn("KaTeX render error:", err);
      rendered = `<code>${escapeHtml(token.expression)}</code>`;
    }
    output = output.split(token.id).join(rendered);
  }
  return output;
}

function formatComputationContent(content: string) {
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

function extractJsonCandidate(content: string) {
  const trimmed = content.trim();
  if (trimmed.startsWith("```") && trimmed.endsWith("```")) {
    const match = trimmed.match(/```[a-zA-Z]*\n([\s\S]*?)```/);
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
      return formatObjectTable(value as Record<string, unknown>[]);
    }
    return value.map((item) => `- ${formatCell(item)}`).join("\n");
  }
  if (isPlainObject(value)) {
    return formatObjectTable([value as Record<string, unknown>]);
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
  const keys = Array.from(
    new Set(objects.flatMap((obj) => Object.keys(obj))),
  );
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

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
