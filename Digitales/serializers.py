# digitales/serializers.py
from rest_framework import serializers
from .models import ClientesDigitales, MensajeWhatsApp
from django.utils import timezone
from datetime import timedelta

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

        # ventana de tiempo
        return timezone.now() <= (obj.created_at + timedelta(minutes=EDIT_WINDOW_MINUTES))
