"use client";

import DOMPurify from "dompurify";
import katex from "katex";
import { marked } from "marked";
import { useMemo } from "react";
import {
  formatComputationContent,
  isOnlyMarkdownFenceMarkers,
  normalizeModelTextArtifacts,
  softlyWrapMathLines,
  tokenizeMath,
} from "@/lib/markdown-format";

type MarkdownPreviewProps = Readonly<{
  content?: string | null;
  emptyState?: string;
  mode?: "final" | "stream";
}>;

export function MarkdownPreview({ content, emptyState, mode = "final" }: MarkdownPreviewProps) {
  const hasSources = Boolean(content && SOURCES_LABEL_TEST.test(content));
  const html = useMemo(() => {
    if (!content || content.trim().length === 0) {
      return "";
    }
    try {
      const normalizedInput = normalizeModelTextArtifacts(content);
      if (isOnlyMarkdownFenceMarkers(normalizedInput)) {
        return "";
      }
      const formatted =
        mode === "final" ? formatComputationContent(normalizedInput) : normalizedInput;
      const wrappedMath =
        mode === "final" ? softlyWrapMathLines(formatted) : formatted;
      const { text: tokenized, tokens } =
        mode === "final" ? tokenizeMath(wrappedMath) : { text: formatted, tokens: [] };
      const withSources =
        mode === "final" && hasSources ? decorateSourcesLabel(tokenized) : tokenized;
      const rendered = marked(withSources, { async: false });
      const withMath = tokens.length > 0 ? renderMathTokens(rendered, tokens) : rendered;
      return DOMPurify.sanitize(withMath);
    } catch (err) {
      console.error("Markdown render error:", err);
      return DOMPurify.sanitize(content);
    }
  }, [content, mode, hasSources]);

  if (!html) {
    return (
      <p className="text-sm text-[--color-muted]">
        {emptyState || "Brak treści do wyświetlenia."}
      </p>
    );
  }

  return (
    <div
      className={`prose prose-invert max-w-none break-words text-sm leading-relaxed [&_a]:break-all [&_code]:break-words [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_pre]:whitespace-pre-wrap [&_pre]:break-words [&_pre_code]:whitespace-pre-wrap [&_.chat-sources-label]:text-xs ${hasSources ? "[&_a]:text-xs [&_a]:italic" : ""
        }`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

type MathToken = {
  id: string;
  expression: string;
  display: boolean;
};

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
    // Escape special regex characters for safe replacement
    const escapedId = token.id.replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`);
    const idRegex = new RegExp(escapedId, "g");
    output = output.replaceAll(idRegex, rendered);
  }
  return output;
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function decorateSourcesLabel(value: string) {
  return value.replaceAll(SOURCES_LABEL_REGEX, (match) => {
    const label = match.trim();
    return `<small class="chat-sources-label"><em>${label}</em></small>`;
  });
}

const SOURCES_LABEL_REGEX = /^(Źródła|Zrodla|Sources?)\s*:\s*$/gim;
const SOURCES_LABEL_TEST = /^(Źródła|Zrodla|Sources?)\s*:\s*$/im;
