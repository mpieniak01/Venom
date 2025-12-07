"""Moduł: audio_stream - WebSocket endpoint dla streamingu audio."""

import asyncio
import base64
from typing import Optional

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

from venom_core.perception.audio_engine import AudioEngine
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class AudioStreamHandler:
    """
    Handler do obsługi streaming audio przez WebSocket.
    Obsługuje VAD (Voice Activity Detection) i dwukierunkowy przepływ audio.
    """

    def __init__(
        self,
        audio_engine: Optional[AudioEngine] = None,
        vad_threshold: float = 0.5,
        silence_duration: float = 1.5,
    ):
        """
        Inicjalizacja handlera.

        Args:
            audio_engine: Silnik audio (STT/TTS)
            vad_threshold: Próg dla Voice Activity Detection (0-1)
            silence_duration: Ile sekund ciszy oznacza koniec wypowiedzi
        """
        self.audio_engine = audio_engine
        self.vad_threshold = vad_threshold
        self.silence_duration = silence_duration
        self.active_connections = {}
        logger.info("AudioStreamHandler zainicjalizowany")

    async def handle_websocket(
        self,
        websocket: WebSocket,
        operator_agent=None,
    ):
        """
        Obsługuje połączenie WebSocket dla audio.

        Args:
            websocket: Połączenie WebSocket
            operator_agent: Agent do przetwarzania komend głosowych (opcjonalny)
        """
        await websocket.accept()
        connection_id = id(websocket)
        self.active_connections[connection_id] = {
            "websocket": websocket,
            "audio_buffer": [],
            "is_speaking": False,
        }

        logger.info(f"Nowe połączenie audio WebSocket: {connection_id}")

        try:
            while True:
                # Odbierz wiadomość
                data = await websocket.receive()

                if "text" in data:
                    # Komenda sterująca (JSON)
                    await self._handle_control_message(
                        connection_id, data["text"], operator_agent
                    )

                elif "bytes" in data:
                    # Audio blob
                    await self._handle_audio_data(
                        connection_id, data["bytes"], operator_agent
                    )

        except WebSocketDisconnect:
            logger.info(f"Rozłączono WebSocket audio: {connection_id}")
        except Exception as e:
            logger.error(f"Błąd w WebSocket audio: {e}")
        finally:
            if connection_id in self.active_connections:
                del self.active_connections[connection_id]

    async def _handle_control_message(
        self, connection_id: int, message: str, operator_agent
    ):
        """
        Obsługuje wiadomości sterujące (JSON).

        Args:
            connection_id: ID połączenia
            message: Wiadomość JSON
            operator_agent: Agent operatora
        """
        import json

        try:
            data = json.loads(message)
            command = data.get("command")

            if command == "start_recording":
                # Rozpocznij nagrywanie
                conn = self.active_connections[connection_id]
                conn["audio_buffer"] = []
                conn["is_speaking"] = True
                logger.info(f"Rozpoczęto nagrywanie: {connection_id}")

                # Wyślij potwierdzenie
                await self._send_json(
                    connection_id, {"type": "recording_started", "status": "ok"}
                )

            elif command == "stop_recording":
                # Zakończ nagrywanie i przetwórz
                conn = self.active_connections[connection_id]
                conn["is_speaking"] = False

                # Przetwórz audio
                if conn["audio_buffer"]:
                    await self._process_audio_buffer(
                        connection_id, conn["audio_buffer"], operator_agent
                    )
                    conn["audio_buffer"] = []

            elif command == "ping":
                # Keep-alive
                await self._send_json(connection_id, {"type": "pong"})

        except json.JSONDecodeError:
            logger.error(f"Nieprawidłowy JSON: {message}")
        except Exception as e:
            logger.error(f"Błąd podczas obsługi wiadomości sterującej: {e}")

    async def _handle_audio_data(
        self, connection_id: int, audio_bytes: bytes, operator_agent
    ):
        """
        Obsługuje dane audio (blob).

        Args:
            connection_id: ID połączenia
            audio_bytes: Surowe dane audio
            operator_agent: Agent operatora
        """
        try:
            conn = self.active_connections[connection_id]

            # Konwertuj bytes na numpy array
            # Zakładamy: 16-bit PCM, mono, 16kHz
            audio_data = np.frombuffer(audio_bytes, dtype=np.int16)

            # Dodaj do bufora
            conn["audio_buffer"].append(audio_data)

            # Sprawdź VAD (czy użytkownik nadal mówi)
            is_voice = self._detect_voice_activity(audio_data)

            if not is_voice and conn["is_speaking"]:
                # Cisza wykryta - może koniec wypowiedzi
                # Czekaj chwilę i sprawdź czy cisza trwa
                await asyncio.sleep(0.5)

                # Jeśli nadal cisza, przetwórz bufor
                if not conn["is_speaking"]:
                    if conn["audio_buffer"]:
                        await self._process_audio_buffer(
                            connection_id, conn["audio_buffer"], operator_agent
                        )
                        conn["audio_buffer"] = []

        except Exception as e:
            logger.error(f"Błąd podczas obsługi audio data: {e}")

    def _detect_voice_activity(self, audio_data: np.ndarray) -> bool:
        """
        Prosta detekcja aktywności głosowej na podstawie RMS.

        Args:
            audio_data: Fragment audio

        Returns:
            True jeśli wykryto głos
        """
        try:
            # Oblicz RMS (Root Mean Square)
            rms = np.sqrt(np.mean(audio_data.astype(float) ** 2))

            # Normalizuj do 0-1
            normalized_rms = rms / 32768.0  # 16-bit audio max

            # Porównaj z progiem
            is_voice = normalized_rms > self.vad_threshold

            return is_voice

        except Exception:
            return False

    async def _process_audio_buffer(
        self, connection_id: int, audio_buffer: list, operator_agent
    ):
        """
        Przetwarza bufor audio (STT -> Agent -> TTS).

        Args:
            connection_id: ID połączenia
            audio_buffer: Lista fragmentów audio
            operator_agent: Agent do przetwarzania
        """
        try:
            # Wyślij status
            await self._send_json(
                connection_id, {"type": "processing", "status": "stt"}
            )

            # Połącz wszystkie fragmenty
            full_audio = np.concatenate(audio_buffer)

            # STT
            if not self.audio_engine:
                logger.warning("AudioEngine nie jest dostępny")
                await self._send_json(
                    connection_id,
                    {
                        "type": "error",
                        "message": "Audio engine not available",
                    },
                )
                return

            transcription = await self.audio_engine.listen(full_audio, language="pl")

            if not transcription:
                await self._send_json(
                    connection_id,
                    {"type": "transcription", "text": "", "confidence": 0.0},
                )
                return

            # Wyślij transkrypcję do klienta
            await self._send_json(
                connection_id,
                {"type": "transcription", "text": transcription, "confidence": 1.0},
            )

            # Przetwórz komendę przez agenta
            if operator_agent:
                await self._send_json(
                    connection_id, {"type": "processing", "status": "thinking"}
                )

                response_text = await operator_agent.process(transcription)

                # Wyślij tekst odpowiedzi
                await self._send_json(
                    connection_id, {"type": "response_text", "text": response_text}
                )

                # TTS
                await self._send_json(
                    connection_id, {"type": "processing", "status": "tts"}
                )

                audio_response = await self.audio_engine.speak(response_text)

                if audio_response is not None:
                    # Wyślij audio do odtworzenia
                    await self._send_audio(connection_id, audio_response)

            # Gotowe
            await self._send_json(connection_id, {"type": "complete"})

        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania bufora audio: {e}")
            await self._send_json(connection_id, {"type": "error", "message": str(e)})

    async def _send_json(self, connection_id: int, data: dict):
        """
        Wysyła JSON przez WebSocket.

        Args:
            connection_id: ID połączenia
            data: Dane do wysłania
        """
        import json

        try:
            conn = self.active_connections.get(connection_id)
            if conn:
                await conn["websocket"].send_text(json.dumps(data))
        except Exception as e:
            logger.error(f"Błąd podczas wysyłania JSON: {e}")

    async def _send_audio(self, connection_id: int, audio_data: np.ndarray):
        """
        Wysyła audio przez WebSocket.

        Args:
            connection_id: ID połączenia
            audio_data: Dane audio (numpy array)
        """
        try:
            conn = self.active_connections.get(connection_id)
            if conn:
                # Konwertuj do bytes
                audio_bytes = audio_data.tobytes()

                # Zakoduj jako base64 (dla JSON) lub wyślij bezpośrednio jako bytes
                # Tutaj używamy JSON dla prostoty
                import json

                message = {
                    "type": "audio_response",
                    "audio": base64.b64encode(audio_bytes).decode("utf-8"),
                    "sample_rate": 22050,
                    "format": "int16",
                }

                await conn["websocket"].send_text(json.dumps(message))

        except Exception as e:
            logger.error(f"Błąd podczas wysyłania audio: {e}")


# Singleton instance
audio_stream_handler: Optional[AudioStreamHandler] = None


def get_audio_stream_handler() -> AudioStreamHandler:
    """
    Pobiera globalną instancję AudioStreamHandler.

    Returns:
        AudioStreamHandler instance
    """
    global audio_stream_handler
    if audio_stream_handler is None:
        audio_stream_handler = AudioStreamHandler()
    return audio_stream_handler
