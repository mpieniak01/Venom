"use client";

import { Panel } from "@/components/ui/panel";
import { SectionHeading } from "@/components/ui/section-heading";
import { useTranslation } from "@/lib/i18n";

export default function LlmModelsDocsPage() {
  const t = useTranslation();

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow={t("docs.models.eyebrow")}
        title={t("docs.models.title")}
        description={t("docs.models.description")}
        as="h1"
        size="lg"
      />
      <Panel
        title={t("docs.models.ollama.title")}
        description={t("docs.models.ollama.description")}
      >
        <ol className="list-decimal space-y-2 pl-4 text-sm text-zinc-300">
          <li>{t("docs.models.ollama.step1")}</li>
          <li>
            {t("docs.models.ollama.step2")} <code>ollama pull gemma:2b</code>.
          </li>
          <li>{t("docs.models.ollama.step3")}</li>
        </ol>
      </Panel>
      <Panel
        title={t("docs.models.vllm.title")}
        description={t("docs.models.vllm.description")}
      >
        <ol className="list-decimal space-y-2 pl-4 text-sm text-zinc-300">
          <li>{t("docs.models.vllm.step1")}</li>
          <li>{t("docs.models.vllm.step2")}</li>
          <li>{t("docs.models.vllm.step3")}</li>
        </ol>
      </Panel>
      <Panel
        title={t("docs.models.diagnostic.title")}
        description={t("docs.models.diagnostic.description")}
      >
        <ul className="list-disc space-y-2 pl-4 text-sm text-zinc-300">
          <li>{t("docs.models.diagnostic.tip1")}</li>
          <li>{t("docs.models.diagnostic.tip2")}</li>
          <li>{t("docs.models.diagnostic.tip3")}</li>
        </ul>
      </Panel>
    </div>
  );
}
