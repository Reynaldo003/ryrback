# digitales/serializers.py
from rest_framework import serializers
from .models import ClientesDigitales, MensajeWhatsApp
from django.utils import timezone
from datetime import timedelta
from django.urls import reverse
class ClientesDigitalesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientesDigitales
        fields = [
            "id",
            "nombre",
            "telefono",
            "correo",
            "agencia",
            "business",
            "canal_contacto",
            "pauta",
            "estado",
            "asesor_digital",
            "asesor_ventas",
            "responsable",
            "auto_interes",
            "comentarios",
            "cita_efectiva",
            "cita_virtual",
            "solicitud_credito",
            "facturado",
            "resultado_solicitud",
            "tipo_venta",
            "primer_contacto_at",
            "ultimo_contacto_at",
            "creado",
            "actualizado",
        ]

EDIT_WINDOW_MINUTES = 15

class WhatsAppMessageSerializer(serializers.ModelSerializer):
    mine = serializers.SerializerMethodField()
    text = serializers.CharField(source="body", read_only=True)
    time = serializers.SerializerMethodField()

    # edición
    editable = serializers.SerializerMethodField()
    edit_expires_at = serializers.SerializerMethodField()
    is_template = serializers.SerializerMethodField()
    is_media = serializers.SerializerMethodField()

    # ✅ adjuntos listos para UI
    attachments = serializers.SerializerMethodField()

    class Meta:
        model = MensajeWhatsApp
        fields = [
            "id",
            "telefono",
            "direction",
            "mine",
            "text",
            "body",
            "wa_message_id",
            "status",
            "raw",
            "created_at",
            "time",

            "editable",
            "edit_expires_at",
            "is_template",
            "is_media",

            "attachments",
        ]

    def get_mine(self, obj):
        return obj.direction == "out"

    def get_time(self, obj):
        if not obj.created_at:
            return ""
        dt = timezone.localtime(obj.created_at)
        return dt.strftime("%I:%M %p").lower()

    def get_is_template(self, obj):
        b = (obj.body or "").strip()
        return b.startswith("[TEMPLATE:")

    def get_is_media(self, obj):
        # si tiene media_id en raw o el body tiene marcador
        raw = obj.raw or {}
        if raw.get("meta_type") in ("image","video","audio","document","sticker"):
            return True
        b = (obj.body or "").strip()
        return b.startswith("[FILE:") or "\n[FILE:" in b

    def get_edit_expires_at(self, obj):
        if not obj.created_at:
            return None
        return (obj.created_at + timedelta(minutes=EDIT_WINDOW_MINUTES)).isoformat()

    def get_editable(self, obj):
        if obj.direction != "out":
            return False
        if not obj.created_at:
            return False
        if self.get_is_template(obj):
            return False
        if self.get_is_media(obj):
            return False
        return timezone.now() <= (obj.created_at + timedelta(minutes=EDIT_WINDOW_MINUTES))

    def get_attachments(self, obj):
        """
        Regresa lista normalizada para el frontend:
        [{id, kind, url, mime, name, size}]
        """
        raw = obj.raw or {}

        # 1) Caso SALIENTE (tu enviar_media_view guarda: raw.upload.id, raw.meta_type, filename, content_type)
        if isinstance(raw, dict) and raw.get("upload") and raw.get("meta_type"):
            media_id = (raw.get("upload") or {}).get("id") or ""
            if media_id:
                kind = raw.get("meta_type")  # image/video/audio/document
                req = self.context.get("request")
                #url = req.build_absolute_uri(f"/digitales/media/{media_id}/") if req else f"/digitales/media/{media_id}/"
                req = self.context.get("request")
                path = reverse("digitales-media-proxy", args=[media_id])
                url = req.build_absolute_uri(path) if req else path
                return [{
                    "id": media_id,
                    "kind": "file" if kind == "document" else kind,
                    "url": url,
                    "mime": raw.get("content_type") or "",
                    "name": raw.get("filename") or "",
                    "size": 0,
                }]

        # 2) Caso ENTRANTE (webhook): raw es el msg de WhatsApp con type y payload
        if isinstance(raw, dict):
            t = (raw.get("type") or "").lower()
            if t in ("image","video","audio","document","sticker"):
                payload = raw.get(t) or {}
                media_id = payload.get("id") or ""
                if media_id:
                    req = self.context.get("request")
                    #url = req.build_absolute_uri(f"/digitales/media/{media_id}/") if req else f"/digitales/media/{media_id}/"
                    req = self.context.get("request")
                    path = reverse("digitales-media-proxy", args=[media_id])
                    url = req.build_absolute_uri(path) if req else path
                    name = payload.get("filename") or ""
                    mime = payload.get("mime_type") or ""
                    return [{
                        "id": media_id,
                        "kind": "sticker" if t == "sticker" else ("file" if t == "document" else t),
                        "url": url,
                        "mime": mime,
                        "name": name,
                        "size": 0,
                    }]

        return []