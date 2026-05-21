"""
shared/tts.py
─────────────
Text-to-Speech con Azure Speech Services REST API.
Convierte texto de squawk en MP3 y lo sube a Azure Blob Storage.

Fase 6.14: calcula audio_duration del MP3 generado.

Uso:
    from shared.tts import generate_audio
    audio_url, audio_duration = generate_audio(squawk_id, text, locale="es")

Requiere env vars:
    AZURE_SPEECH_KEY         — Key del recurso Azure Speech
    AZURE_SPEECH_REGION      — Region (spaincentral)
    AZURE_STORAGE_CONN_STR   — Connection string del Storage Account
"""

from __future__ import annotations

import io
import logging
import os
import uuid

import requests

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "")
SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "spaincentral")
STORAGE_CONN_STR = os.getenv("AZURE_STORAGE_CONN_STR", "")
STORAGE_CONTAINER = "squawks-audio"
STORAGE_ACCOUNT = "squawksmlstorage"

# Voces por locale
VOICES = {
    "es": "es-ES-AlvaroNeural",
    "en": "en-US-GuyNeural",
}

# Audio format: 16khz, 128kbps mono MP3
_OUTPUT_FORMAT = "audio-16khz-128kbitrate-mono-mp3"
_BITRATE_KBPS = 128


def generate_audio(
    squawk_id: str, text: str, locale: str = "es",
) -> tuple[str | None, float | None]:
    """
    Genera audio MP3 desde texto y lo sube a Blob Storage.

    Args:
        squawk_id: ID del squawk (para nombrar el archivo)
        text:      texto a convertir en audio
        locale:    idioma (es, en)

    Returns:
        (URL pública del MP3 o None, duración en segundos o None)
    """
    if not SPEECH_KEY:
        log.warning("AZURE_SPEECH_KEY no configurado — TTS desactivado")
        return None, None

    if not STORAGE_CONN_STR:
        log.warning("AZURE_STORAGE_CONN_STR no configurado — TTS desactivado")
        return None, None

    try:
        # 1. Generar audio con Azure Speech REST API
        audio_data = _synthesize_speech(text, locale)
        if not audio_data:
            return None, None

        # 2. Calcular duración del audio
        audio_duration = _calculate_duration(audio_data)

        # 3. Subir a Blob Storage
        blob_name = f"{squawk_id}_{uuid.uuid4().hex[:8]}.mp3"
        audio_url = _upload_to_blob(audio_data, blob_name)

        log.info(
            "  TTS: audio generado (%d bytes, %.1fs) → %s",
            len(audio_data),
            audio_duration or 0,
            blob_name,
        )
        return audio_url, audio_duration

    except Exception as e:
        log.error("Error en TTS: %s", e)
        return None, None


def _calculate_duration(audio_data: bytes) -> float | None:
    """
    Calcula la duración de un MP3 en segundos.

    Intenta usar mutagen si está disponible (preciso).
    Fallback: estimación por tamaño y bitrate.
    """
    # Método 1: mutagen (preciso)
    try:
        from mutagen.mp3 import MP3

        mp3 = MP3(io.BytesIO(audio_data))
        return round(mp3.info.length, 2)
    except ImportError:
        pass
    except Exception as e:
        log.debug("mutagen falló, usando estimación: %s", e)

    # Método 2: estimación por tamaño
    # bitrate = 128 kbps → 16000 bytes/s
    bytes_per_second = _BITRATE_KBPS * 1000 / 8
    duration = len(audio_data) / bytes_per_second
    return round(duration, 2)


def _synthesize_speech(text: str, locale: str) -> bytes | None:
    """Llama a Azure Speech REST API para generar audio."""
    voice = VOICES.get(locale, VOICES["es"])
    lang = "es-ES" if locale.startswith("es") else "en-US"

    ssml = f"""
    <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{lang}'>
        <voice name='{voice}'>
            <prosody rate='+10%'>{_escape_xml(text)}</prosody>
        </voice>
    </speak>
    """.strip()

    url = f"https://{SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"

    headers = {
        "Ocp-Apim-Subscription-Key": SPEECH_KEY,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": _OUTPUT_FORMAT,
        "User-Agent": "SquawksML-TTS/1.0",
    }

    response = requests.post(url, headers=headers, data=ssml.encode("utf-8"), timeout=10)

    if response.status_code == 200:
        return response.content

    log.error("Azure Speech API error %d: %s", response.status_code, response.text[:200])
    return None


def _upload_to_blob(data: bytes, blob_name: str) -> str:
    """Sube bytes a Azure Blob Storage y devuelve la URL pública."""
    from azure.storage.blob import BlobServiceClient, ContentSettings

    blob_service = BlobServiceClient.from_connection_string(STORAGE_CONN_STR)
    blob_client = blob_service.get_blob_client(
        container=STORAGE_CONTAINER,
        blob=blob_name,
    )

    blob_client.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(content_type="audio/mpeg"),
    )

    return f"https://{STORAGE_ACCOUNT}.blob.core.windows.net/{STORAGE_CONTAINER}/{blob_name}"


def _escape_xml(text: str) -> str:
    """Escapa caracteres especiales para SSML."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
