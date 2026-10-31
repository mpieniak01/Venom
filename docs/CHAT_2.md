# Venom Chat 2.0

Chat 2.0 is the shared conversation experience for text, materials and voice.
It is available as the optional `/chat2` shell inside Venom and as the focused
standalone Studio application. Both use the same conversation controller,
provider adapters and environment-owned history. Studio has its own Next app
and a smaller FastAPI entry point: [Venom/Studio instructions](STUDIO.md).

## Enable and return

For the standalone application, use `make start-studio` and the matching
`make stop-studio`. Return with `make start-venom` after stopping Studio.
Explicit variants select their own frontend/API composition. Studio contains
only the conversation routes and has no classic `/chat` link.

The optional route inside the existing `web-next` still uses
`NEXT_PUBLIC_FEATURE_CHAT2`, default `false`. Set the exact string `true` for
that UI. This public flag is embedded in the Next build: restart development
UI or rebuild a stopped prepared UI with the same flag. Changing only the
runtime environment of a built server does not enable the client link.
For the configured, stopped legacy launch path:

```bash
NEXT_PUBLIC_FEATURE_CHAT2=true make start PROFILE=full ENVIRONMENT=dev
```

Explicit `start-venom` sets that entry to `false`; use `start-studio` for the
standalone experience. Examples remain in `.env.dev.example`,
`.env.preprod.example` and `web-next/.env.local.example`. Use the owning instance
launcher and preserve environment-specific settings. Do not copy private
configuration or rebuild an active UI's artifact.

In Full, disabled `/chat2` returns 404 and its menu entry is hidden; `/chat`
remains available, and **Existing Venom** returns there. Disabling that entry,
or stopping Studio and returning to Venom, does not delete server history,
materials or provider selection. Browser drafts use shared keys on the same
origin. No history migration is required. See [launch profiles](STACK_PROFILES.md)
and the [UI build lifecycle](PL/WEB_LIFECYCLE.md).

## Conversation and runtime

Use the conversation list to return to a thread or create a new one. Both shells
use the same session identity and draft. Successful Direct turns are saved to
the host SessionStore before completion is reported; original user text and
material IDs are retained, not expanded documents or base64 images. Stopped
partial turns can retain a `CANCELLED` status. Browser draft recovery is a
convenience, not a backup of the server history.

Choose an engine and model, then **Apply model**. The shell uses the existing
catalog, runtime admission and budget rules. A model choice preserves the draft
and files; an incompatible choice blocks sending with an explanation.

| Mode | Scope |
| --- | --- |
| Direct | Conversation with the selected adapter; supported materials use this mode. |
| Normal | Existing orchestration, only where the runtime supports it. |
| MAF | Existing complex-task path, subject to backend availability and policy. |

The current OpenRouter and Vast adapters are Direct-only. Normal/MAF do not
accept material references; attaching files does not silently activate another
mode or provider. The same host still owns one active runtime/generation flow.
**Stop response** targets this conversation's work, not a global queue emergency.

The cost panel shows known prices and accounting from the existing provider
contract. **Unknown price does not mean free.** Quotes, reservations and usage
remain server-controlled; stopping an uncertain paid request does not turn its
pending charge into zero. Opening the shell or selecting a model does not run
a paid provider test or enable account monitoring.

## Materials

Drop files into Materials or use **Add files**. Uploading creates a session-owned
reference; select at most **four material IDs per turn**. Preview, deselect or
delete a file explicitly. A missing/deleted reference blocks sending rather
than being dropped silently. New conversations have their own materials.

| Input | Implemented path |
| --- | --- |
| TXT, MD, CSV, JSON | UTF-8 reference text included in the message context; no automatic RAG or active document execution. |
| PNG, JPEG, WebP | Images through the supported local Ollama adapter, only after metadata verifies vision support for the selected model. |
| PDF, Office, SVG/HTML, audio/video files | Unavailable in this material adapter. |
| Images through OpenRouter, Vast or other remote adapters | Unavailable; text support or advertised model multimodality does not enable an image transport or image billing contract. |

Each file is limited to **8 MiB**; a document must also decode as UTF-8 and stay
within **64,000 characters**. The executed turn, including expanded reference
text, is limited to **50,000 characters**, and the included text history plus
current turn to **64,000 characters**. Aggregate referenced material bytes are
limited to **16 MiB**. The selected runtime/model may impose a lower context
limit. Upload acceptance therefore does not guarantee that every combination
fits a turn; shorten the input or deselect files when the context limit is hit.
Images are decoded/validated and limited to 20 megapixels. Per-session storage
is limited to 32 files and 64 MiB. Preprod read-only policy still applies.

Changing a model does not delete materials. Returning to `/chat` or disabling
Chat 2.0 does not delete them either. Deleting a file does remove that material;
old history references can then be unavailable. This is separate from rollback.

## Dictation and voice

Voice uses the existing **STT → the same conversation controller → TTS** path.
It is not native model audio, so a text model can still be used with configured
speech recognition and synthesis. Browser microphone permission and a secure
browser context are required. Service readiness and errors remain visible.

- **Dictate a draft**: explicitly record a segment, then finish it. Its transcript
  becomes editable text; dictation never sends the message automatically.
- **Voice conversation**: explicitly choose **Record a turn**, then **Finish turn**.
  The transcript is sent through the same conversation controller, and an eligible
  completed answer is read aloud. Record the next turn explicitly; the microphone
  does not restart automatically after playback.
- **Mute microphone**, **Stop response** and **End voice** have separate effects.
  Ending voice releases capture/playback and invalidates pending callbacks. Stop
  prevents a late transcript, answer or audio response from reviving an old turn.

Opening a page or voice panel does not request the microphone, record speech,
or start an always-on listener. Native audio input/output and uploaded audio or
video are not implied by STT/TTS availability.

## Qualification

Unit, component and fake-API browser tests verify these contracts. They do not
qualify a real microphone, provider response quality, model vision accuracy or
paid execution. Real provider Test Zero requires a separate operator instruction
for each run; see [the provider test policy](PROVIDER_TEST_ZERO_POLICY.md).
This guide does not declare final B07 performance or release acceptance.

[Polish guide](PL/CHAT_2.md)

[Local acceptance and measured limitations](CHAT_2_ACCEPTANCE.md).
