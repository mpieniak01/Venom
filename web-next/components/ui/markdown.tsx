"use client";

import DOMPurify from "dompurify";
import { marked } from "marked";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "@/lib/i18n";
import {
  formatComputationContent, isOnlyMarkdownFenceMarkers, normalizeModelTextArtifacts,
  softlyWrapMathLines, tokenizeMath,
} from "@/lib/markdown-format";

type MathRenderer = Pick<typeof import("katex"), "renderToString">;
let mathModule: Promise<MathRenderer> | null = null;
const loadMathRenderer = () => {
  mathModule ??= import("katex").then((module) => module.default).catch((error: unknown) => {
    mathModule = null;
    throw error;
  });
  return mathModule;
};

type MarkdownPreviewProps = Readonly<{
  content?: string | null;
  emptyState?: string;
  mode?: "final" | "stream";
  loadMath?: () => Promise<MathRenderer>;
}>;

export function MarkdownPreview({
  content, emptyState, mode = "final", loadMath = loadMathRenderer,
}: MarkdownPreviewProps) {
  const t = useTranslation();
  const [mathRenderer, setMathRenderer] = useState<MathRenderer | null>(null);
  const hasSources = Boolean(content && SOURCES_LABEL_TEST.test(content));
  const prepared = useMemo(() => {
    if (!content?.trim()) return { rendered: "", tokens: [] };
    try {
      const normalizedInput = normalizeModelTextArtifacts(content);
      if (isOnlyMarkdownFenceMarkers(normalizedInput)) return { rendered: "", tokens: [] };
      const formatted = mode === "final" ? formatComputationContent(normalizedInput) : normalizedInput;
      const wrapped = mode === "final" ? softlyWrapMathLines(formatted) : formatted;
      const { text, tokens } = mode === "final" ? tokenizeMath(wrapped) : { text: formatted, tokens: [] };
      // Keep underscore-based token IDs literal through Markdown parsing.
      // Otherwise marked interprets them as emphasis and replacement cannot find them.
      const literalTokens = tokens.reduce((input, token) =>
        input.replaceAll(token.id, token.id.replaceAll("_", "\\_")), text);
      const sourceText = mode === "final" && hasSources ? decorateSourcesLabel(literalTokens) : literalTokens;
      return { rendered: marked(sourceText, { async: false }), tokens };
    } catch (error) {
      console.error("Markdown render error:", error);
      return { rendered: escapeHtml(content), tokens: [] };
    }
  }, [content, mode, hasSources]);
  const needsMath = prepared.tokens.length > 0;

  useEffect(() => {
    if (!needsMath) return;
    let active = true;
    void loadMath().then((renderer) => {
      if (active) setMathRenderer(renderer);
    }).catch((error: unknown) => {
      // The expressions remain readable and sanitized when a chunk is unavailable.
      if (active) console.warn("KaTeX could not be loaded", error);
    });
    return () => { active = false; };
  }, [needsMath, loadMath]);

  const html = useMemo(() => DOMPurify.sanitize(
    renderMathTokens(prepared.rendered, prepared.tokens, mathRenderer),
  ), [prepared, mathRenderer]);

  if (!html) return <p className="text-sm text-[--color-muted]">{emptyState || t("cockpit.chatLabels.emptyContent")}</p>;

  return <div
    className={`prose prose-invert max-w-none break-words text-sm leading-relaxed [&_a]:break-all [&_code]:break-words [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_pre]:whitespace-pre-wrap [&_pre]:break-words [&_pre_code]:whitespace-pre-wrap [&_.chat-sources-label]:text-xs ${hasSources ? "[&_a]:text-xs [&_a]:italic" : ""}`}
    dangerouslySetInnerHTML={{ __html: html }}
  />;
}

type MathToken = { id: string; expression: string; display: boolean };

function renderMathTokens(html: string, tokens: MathToken[], renderer: MathRenderer | null) {
  let output = html;
  for (const token of tokens) {
    let rendered = `<code>${escapeHtml(token.expression)}</code>`;
    if (renderer) {
      try {
        rendered = renderer.renderToString(token.expression, {
          displayMode: token.display, throwOnError: false,
        });
      } catch (error) { console.warn("KaTeX render error:", error); }
    }
    output = output.split(token.id).join(rendered);
  }
  return output;
}

function escapeHtml(value: string) {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function decorateSourcesLabel(value: string) {
  return value.replaceAll(SOURCES_LABEL_REGEX, (match) =>
    `<small class="chat-sources-label"><em>${match.trim()}</em></small>`,
  );
}
const SOURCES_LABEL_REGEX = /^(Źródła|Zrodla|Sources?)\s*:\s*$/gim;
const SOURCES_LABEL_TEST = /^(Źródła|Zrodla|Sources?)\s*:\s*$/im;
