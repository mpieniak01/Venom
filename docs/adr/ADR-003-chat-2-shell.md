# ADR-003: Chat 2.0 as an isolated shell in the existing web application

> Deployment decision partially superseded by [ADR-004](ADR-004-studio-runtime-composition.md) on 2026-10-31: Studio also has a standalone web/API composition. The shared conversation, material, voice and qualification contracts below remain in force.

Date: 2026-10-30. Status: Accepted for implementation; functional and visual acceptance is B07.
Baseline: Group A merged through e01e7b08 (PRs 571, 570 and 572).

## Context

The operator needs one responsive application for text, materials and voice. The Studio prototype provides the implementation baseline; it is not evidence of provider capabilities. A theme alone cannot remove the cockpit layout, polling or loaded features. A second deployed Next.js/API instance would duplicate operational work.

## Decision

1. Keep the existing Next.js, FastAPI, session store and provider adapters. Introduce an opt-in `/chat2` route gated by `NEXT_PUBLIC_FEATURE_CHAT2=true`; `/chat` remains the existing application. This is a shell choice, independent of Full/Light, dev/preprod, bundler and theme.
2. Root layout owns fonts, theme bootstrap, locale, session and toast only. A route-group layout owns the existing sidebar, top bar, status bar and cockpit-specific providers. Chat 2.0 must not mount that layout or its telemetry. Existing URLs remain unchanged.
3. Use Studio: narrow navigation rail, compact conversation picker, central thread/composer and contextual materials panel. On small screens panels become explicitly opened sections. Do not copy other application screens or their menus.
4. Both chat views consume the same conversation controller and transport implementation: session/history, optimistic state, streaming, identity, cancellation and errors. Drafts use a common session-scoped key and survive navigation. A route mounts one conversation owner. The controller does not fetch Git, graph, metrics or learning logs.
5. Model choices come from the current runtime/catalog, with unknown capabilities and prices shown as unknown. Direct/Normal/MAF availability follows the server. Changing an option never sends a prompt, loads a second runtime, clears a draft or selects a more expensive model implicitly.
6. Materials have persistent, opaque session-scoped IDs. Initial document formats are UTF-8 text/Markdown/CSV/JSON, bounded before provider submission and cost quotation. Images are enabled only for a verified local Ollama vision model and an adapter tested with fake transport. Remote image accounting, PDF extraction, native audio and video remain unavailable until their complete adapters exist. No unsupported feature is presented as working.
7. Dictation creates an editable draft. Explicit voice conversation uses the same text controller and existing STT/TTS services; it does not start a second LLM path. Stop response, mute capture and end voice are distinct. Opening the page grants no microphone access. Navigation/session change cancels stale work and releases microphone, playback, sockets and object URLs.
8. Automated acceptance uses fake providers/audio. Real paid-provider test zero, live microphone and robot tests are separate operator actions. Preserve the current Full/dev/Turbopack profile and audio quality. Rider initialization is explicitly deferred and excluded from this work.

## State and acceptance contract

- Thread: loading, empty, ready, generating, disconnected/retrying, error, cancelled; partial output stays visible after Stop.
- Materials: choosing, uploading, ready, unsupported, failed and removing; abort uploads on session change, preserve a draft when a new model cannot consume its materials, reject stale/cross-session references before generation.
- Voice: permission request, listening, muted, transcription, waiting, speaking, error and ended. Dictation never auto-sends; only the explicitly active conversation mode may submit a completed turn.
- Keyboard: labelled controls, visible focus, submit versus newline, Escape closes contextual UI, no focus loss during streaming, announcements for status/errors.
- Languages: PL/EN/DE with the current locale loader; never load all dictionaries for this shell.
- B07 records baseline and candidate SHA/conditions, same Turbo mode, startup requests/JS, process PSS separately from browser heap, long-history/Stop/reconnect/reload and repeated voice/material cleanup. Report observations without inventing savings or provider qualification.

## Consequences and rollback

The existing application remains available and shares history. Disabling the feature entry restores the existing UI without migrations or deleting materials/history. Route isolation and the shared controller add regression coverage; they do not create another dependency or deployment profile. No other screen is redesigned by this ADR.
