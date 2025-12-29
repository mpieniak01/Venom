"use client";

import DOMPurify from "dompurify";
import katex from "katex";
import { marked } from "marked";
import { useEffect, useState } from "react";
import {
  formatComputationContent,
  softlyWrapMathLines,
  tokenizeMath,
} from "@/lib/markdown-format";

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
      const wrappedMath =
        mode === "final" ? softlyWrapMathLines(formatted) : formatted;
      const { text: tokenized, tokens } =
        mode === "final" ? tokenizeMath(wrappedMath) : { text: formatted, tokens: [] };
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
    // Use replace with escaped regex special characters for safe replacement
    const escapedId = token.id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    output = output.replace(new RegExp(escapedId, 'g'), rendered);
  }
  return output;
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
