"use client";

export const PROMPT_PRESETS = [
  {
    id: "preset-creative",
    category: "Kreacja",
    description: "Stwórz logo dla fintechu używając DALL-E",
    prompt: "Stwórz logo dla fintechu używając DALL-E",
    icon: "🎨",
  },
  {
    id: "preset-devops",
    category: "DevOps",
    description: "Sprawdź status serwerów w infrastrukturze",
    prompt: "Sprawdź status serwerów w infrastrukturze",
    icon: "☁️",
  },
  {
    id: "preset-project",
    category: "Status projektu",
    description: "Pokaż status projektu i roadmapy",
    prompt: "Pokaż status projektu",
    icon: "📊",
  },
  {
    id: "preset-research",
    category: "Research",
    description: "Zrób research o trendach AI w 2024",
    prompt: "Zrób research o trendach AI w 2024",
    icon: "🧠",
  },
  {
    id: "preset-code",
    category: "Kod",
    description: "Napisz testy jednostkowe dla modułu API",
    prompt: "Napisz testy jednostkowe dla modułu API",
    icon: "🛠️",
  },
  {
    id: "preset-help",
    category: "Pomoc",
    description: "Co potrafisz? Pokaż dostępne funkcje systemu",
    prompt: "Co potrafisz?",
    icon: "❓",
  },
] as const;
