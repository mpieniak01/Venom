export const voice = {
  page: {
    eyebrow: "// voice chat",
    title: "Voice Command Center",
    description: "Dedicated screen for push-to-talk, transcription, responses, and analysis modes. The text chat stays light.",
    backToChat: "Back to text chat",
  },
  modes: {
    title: "Voice modes",
    description: "Choose how the next utterance should be handled.",
    hint: "The active mode is sent to the backend as part of the voice session and changes the agent response style.",
    standard: {
      title: "Standard",
      description: "Short and direct response.",
    },
    deepAnalysis: {
      title: "Deep analysis",
      description: "More insights, risks, and recommendations.",
    },
    summary: {
      title: "Summary",
      description: "Shortest answer in 1-2 sentences.",
    },
    actionItems: {
      title: "Action items",
      description: "Concrete next steps.",
    },
  },
  sections: {
    workflow: {
      eyebrow: "Scope",
      title: "Separated workflow",
      description: "Voice does not compete with the written chat history.",
      pushToTalk: "Push-to-talk and playback are handled in a dedicated view.",
      advancedModes: "Deep analysis, summary, and action items are exposed directly to the user.",
    },
    note: {
      eyebrow: "Note",
      title: "Text chat stays stable",
      description: "History, composer, and written-chat actions no longer share space with the large voice panel.",
      body: "This creates room for the next PR with voice visualization without degrading the cockpit layout.",
    },
  },
};
