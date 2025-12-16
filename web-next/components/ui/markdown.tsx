"use client";

import DOMPurify from "dompurify";
import { marked } from "marked";
import { useEffect, useState } from "react";

type MarkdownPreviewProps = {
  content?: string | null;
  emptyState?: string;
};

export function MarkdownPreview({ content, emptyState }: MarkdownPreviewProps) {
  const [html, setHtml] = useState<string>("");

  useEffect(() => {
    if (!content || content.trim().length === 0) {
      setHtml("");
      return;
    }

    try {
      const rendered = marked(content, { async: false });
      const sanitized = DOMPurify.sanitize(rendered);
      setHtml(sanitized);
    } catch (err) {
      console.error("Markdown render error:", err);
      setHtml(DOMPurify.sanitize(content));
    }
  }, [content]);

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
