export const voice = {
  page: {
    eyebrow: "// voice chat",
    title: "Voice Command Center",
    description: "Osobny ekran dla push-to-talk, transkrypcji, odpowiedzi i trybów analizy. Tekstowy chat zostaje lekki.",
    backToChat: "Wróć do chatu pisanego",
  },
  modes: {
    title: "Tryby voice",
    description: "Wybierz jak ma być traktowana kolejna wypowiedź.",
    hint: "Aktywny tryb jest wysyłany do backendu jako część sesji voice i zmienia styl odpowiedzi agenta.",
    standard: {
      title: "Standard",
      description: "Krótka i bezpośrednia odpowiedź.",
    },
    deepAnalysis: {
      title: "Głęboka analiza",
      description: "Więcej wniosków, ryzyk i rekomendacji.",
    },
    summary: {
      title: "Podsumowanie",
      description: "Najkrótsza odpowiedź w 1-2 zdaniach.",
    },
    actionItems: {
      title: "Action items",
      description: "Konkretny plan dalszych kroków.",
    },
  },
  sections: {
    workflow: {
      eyebrow: "Zakres",
      title: "Rozdzielony workflow",
      description: "Voice nie konkuruje z historia chatu pisanego.",
      pushToTalk: "Push-to-talk i playback sa obsługiwane w osobnym widoku.",
      advancedModes: "Tryb deep analysis, summary i action items są dostępne wprost dla użytkownika.",
    },
    note: {
      eyebrow: "Uwaga",
      title: "Text chat pozostaje stabilny",
      description: "Historia, composer i akcje chatu pisanego nie dziela juz miejsca z duzym panelem voice.",
      body: "To rozwiazanie przygotowuje grunt pod kolejny PR z wizualizacja glosu bez degradacji layoutu cockpit.",
    },
  },
};
