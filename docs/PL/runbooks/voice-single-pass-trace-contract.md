# Kontrakt Single-pass Trace Dla Voice

## Zakres
Kontrakt definiuje rekord dowodowy E2E dla żądań voice obsługiwanych przez `multi_runtime / google/gemma-4-E2B-it`.

## Wymagane pola na sesję
1. `request_id`: unikalny identyfikator żądania zwrócony przez `/v1/respond`.
2. `trace_id`: ta sama wartość co `request_id` (alias zgodności).
3. `audio_hash`: SHA-256 payloadu WAV wysłanego do runtime.
4. `transcription`: transkrypcja z tego samego wywołania `/v1/respond`.
5. `transcription_used_for_generation`: tekst transkrypcji użyty do generacji odpowiedzi.
6. `response_text`: końcowa odpowiedź tekstowa z tego samego wywołania `/v1/respond`.
7. `decoder_selected`: pierwszy dekoder wybrany z profilu/łańcucha.
8. `decoder_effective`: dekoder, który faktycznie obsłużył żądanie.
9. `decoder_fallback_reason`: powód fallbacku, gdy `decoder_effective != decoder_selected`.
10. `trace_inconsistent`: flaga rozjazdu między transkrypcją a transkrypcją użytą do generacji.

## Inwariant single-pass
Dla jednego żądania voice istnieje dokładnie jedno wywołanie `/v1/respond` będące źródłem prawdy dla:
1. transkrypcji,
2. odpowiedzi końcowej.

W torze `gemma4` nie dopuszczamy dodatkowego `/audio/transcribe` dla tego samego żądania.

## Profile torów
1. `gemma4`: wymaga `gemma_native` jako pierwszego dekodera.
2. `runtime_lokalny`: wymusza tor `faster_whisper`.
3. `venom-agent`: wymusza tor `faster_whisper` + wykonanie agentowe.
4. `chat_tekstowy`: wyłącza voice audio pipeline.
5. `auto`: wybór zależny od aktywnego runtime.

## Sterowanie operatorskie
Przełączanie profili bez zmian kodu przez:
1. `GET/POST /api/v1/audio/routes/profile`,
2. kontrolki w panelu Voice (`web-next`),
3. `make voice-route-profile-show` i `make voice-route-profile-set`.
