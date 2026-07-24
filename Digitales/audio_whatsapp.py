"""
Conversión de audios para WhatsApp Cloud API mediante FFmpeg.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

from django.conf import settings
from django.core.files import File


# Extensiones que deben tratarse como audio aunque el navegador
# no envíe correctamente el content_type.
AUDIO_EXTENSIONS = {
    ".aac",
    ".amr",
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".oga",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
}


@dataclass
class MediaPreparada:
    """
    Resultado de preparar un archivo antes de enviarlo a Meta.
    """

    archivo: BinaryIO
    nombre: str
    content_type: str
    convertido: bool
    nombre_original: str


def es_archivo_audio(nombre: str = "", content_type: str = "") -> bool:
    """
    Detecta audio por MIME o por extensión.

    Esto es importante porque algunos navegadores pueden mandar:
    application/octet-stream
    aunque el archivo realmente sea WebM, M4A u OGG.
    """

    mime = str(content_type or "").split(";", 1)[0].strip().lower()
    extension = Path(str(nombre or "")).suffix.lower()

    return mime.startswith("audio/") or extension in AUDIO_EXTENSIONS


def _resolver_ffmpeg() -> str:
    """
    Busca FFmpeg.

    Primero revisa settings.FFMPEG_BIN.
    Si no existe, intenta encontrar 'ffmpeg' en el PATH.
    """

    configured = str(
        getattr(settings, "FFMPEG_BIN", "ffmpeg") or "ffmpeg"
    ).strip()

    if os.path.isabs(configured) and os.path.isfile(configured):
        return configured

    resolved = shutil.which(configured)

    if resolved:
        return resolved

    raise RuntimeError(
        "FFmpeg no está instalado o no está disponible en PATH. "
        "Instálalo y verifica con: ffmpeg -version"
    )


def _copiar_upload_a_disco(file_obj, destination: str) -> None:
    """
    Copia un UploadedFile de Django a un archivo temporal.
    """

    try:
        file_obj.seek(0)
    except Exception:
        pass

    with open(destination, "wb") as output:
        if hasattr(file_obj, "chunks"):
            for chunk in file_obj.chunks():
                output.write(chunk)
        else:
            shutil.copyfileobj(file_obj, output)

    try:
        file_obj.seek(0)
    except Exception:
        pass


@contextmanager
def preparar_media_whatsapp(
    file_obj,
    *,
    filename: str,
    content_type: str,
) -> Iterator[MediaPreparada]:
    """
    Prepara un archivo antes de subirlo a WhatsApp.

    Si no es audio:
        devuelve el archivo original sin modificar.

    Si es audio:
        lo convierte a:
        - contenedor OGG
        - códec Opus
        - mono
        - 48 kHz
        - 32 kbps
    """

    original_name = str(
        filename
        or getattr(file_obj, "name", "archivo")
        or "archivo"
    )

    original_type = str(
        content_type
        or getattr(file_obj, "content_type", "")
        or ""
    )

    # Imágenes, videos y documentos continúan con el flujo normal.
    if not es_archivo_audio(original_name, original_type):
        yield MediaPreparada(
            archivo=file_obj,
            nombre=original_name,
            content_type=original_type,
            convertido=False,
            nombre_original=original_name,
        )
        return

    ffmpeg = _resolver_ffmpeg()

    input_suffix = Path(original_name).suffix.lower() or ".bin"

    with tempfile.TemporaryDirectory(
        prefix="whatsapp_audio_"
    ) as temp_dir:

        input_path = os.path.join(
            temp_dir,
            f"entrada{input_suffix}",
        )

        output_name = (
            f"nota-voz-{uuid.uuid4().hex}.ogg"
        )

        output_path = os.path.join(
            temp_dir,
            output_name,
        )

        _copiar_upload_a_disco(
            file_obj,
            input_path,
        )

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",

            "-i",
            input_path,

            # No conservar metadatos del archivo original.
            "-map_metadata",
            "-1",

            # Asegura que solamente se procese audio.
            "-vn",

            # Audio mono.
            "-ac",
            "1",

            # Frecuencia compatible con Opus.
            "-ar",
            "48000",

            # Códec de voz.
            "-c:a",
            "libopus",

            # Bitrate suficiente para nota de voz.
            "-b:a",
            "32k",

            "-vbr",
            "on",

            "-compression_level",
            "10",

            # Optimiza Opus para voz.
            "-application",
            "voip",

            # Contenedor final.
            "-f",
            "ogg",

            output_path,
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )

        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "La conversión del audio excedió 120 segundos."
            ) from exc

        if (
            result.returncode != 0
            or not os.path.exists(output_path)
        ):
            detail = (
                result.stderr
                or result.stdout
                or "Error desconocido de FFmpeg"
            ).strip()

            raise RuntimeError(
                "No se pudo convertir el audio a OGG/Opus: "
                f"{detail[-1200:]}"
            )

        if os.path.getsize(output_path) <= 0:
            raise RuntimeError(
                "FFmpeg generó un audio vacío."
            )

        # Este archivo permanece abierto solamente dentro del with.
        with open(output_path, "rb") as converted_stream:
            django_file = File(
                converted_stream,
                name=output_name,
            )

            yield MediaPreparada(
                archivo=django_file,
                nombre=output_name,
                content_type="audio/ogg",
                convertido=True,
                nombre_original=original_name,
            )