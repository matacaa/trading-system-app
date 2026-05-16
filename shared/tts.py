"""
shared/tts.py
─────────────
Text-to-Speech con Azure Speech Services REST API.
Convierte texto de squawk en MP3 y lo sube a Azure Blob Storage.

Uso:
    from shared.tts import generate_audio
    audio_url = generate_audio(squawk_id, text, locale="es")

Requiere env vars:
    AZURE_SPEECH_KEY         — Key del recurso Azure Speech
    AZURE_SPEECH_REGION      — Region (spaincentral)
    AZURE_STORAGE_CONN_STR   — Connection string del Storage Account
"""

from __future__ import annotations

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


def generate_audio(squawk_id: str, text: str, locale: str = "es") -> str | None:
    """
    Genera audio MP3 desde texto y lo sube a Blob Storage.

    Args:
        squawk_id: ID del squawk (para nombrar el archivo)
        text:      texto a convertir en audio
        locale:    idioma (es, en)

    Returns:
        URL pública del MP3, o None si falla
    """
    if not SPEECH_KEY:
        log.warning("AZURE_SPEECH_KEY no configurado — TTS desactivado")
        return None

    if not STORAGE_CONN_STR:
        log.warning("AZURE_STORAGE_CONN_STR no configurado — TTS desactivado")
        return None

    try:
        # 1. Generar audio con Azure Speech REST API
        audio_data = _synthesize_speech(text, locale)
        if not audio_data:
            return None

        # 2. Subir a Blob Storage
        blob_name = f"{squawk_id}_{uuid.uuid4().hex[:8]}.mp3"
        audio_url = _upload_to_blob(audio_data, blob_name)

        log.info("  TTS: audio generado (%d bytes) → %s", len(audio_data), blob_name)
        return audio_url

    except Exception as e:
        log.error("Error en TTS: %s", e)
        return None


def _synthesize_speech(text: str, locale: str) -> bytes | None:
    """Llama a Azure Speech REST API para generar audio."""
    voice = VOICES.get(locale, VOICES["es"])
    lang = "es-ES" if locale.startswith("es") else "en-US"

    # SSML para controlar voz, velocidad y formato
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
        "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
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
