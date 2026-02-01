"use client";

export const PROMPT_PRESETS = [
  {
    id: "preset-creative",
    categoryKey: "cockpit.presets.creative.category",
    descriptionKey: "cockpit.presets.creative.description",
    promptKey: "cockpit.presets.creative.prompt",
    icon: "🎨",
  },
  {
    id: "preset-devops",
    categoryKey: "cockpit.presets.devops.category",
    descriptionKey: "cockpit.presets.devops.description",
    promptKey: "cockpit.presets.devops.prompt",
    icon: "☁️",
  },
  {
    id: "preset-project",
    categoryKey: "cockpit.presets.project.category",
    descriptionKey: "cockpit.presets.project.description",
    promptKey: "cockpit.presets.project.prompt",
    icon: "📊",
  },
  {
    id: "preset-research",
    categoryKey: "cockpit.presets.research.category",
    descriptionKey: "cockpit.presets.research.description",
    promptKey: "cockpit.presets.research.prompt",
    icon: "🧠",
  },
  {
    id: "preset-code",
    categoryKey: "cockpit.presets.code.category",
    descriptionKey: "cockpit.presets.code.description",
    promptKey: "cockpit.presets.code.prompt",
    icon: "🛠️",
  },
  {
    id: "preset-help",
    categoryKey: "cockpit.presets.help.category",
    descriptionKey: "cockpit.presets.help.description",
    promptKey: "cockpit.presets.help.prompt",
    icon: "❓",
  },
] as const;
