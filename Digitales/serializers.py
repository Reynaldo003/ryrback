# digitales/serializers.py
from rest_framework import serializers
from .models import ClientesDigitales, MensajeWhatsApp
from django.utils import timezone

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

class WhatsAppMessageSerializer(serializers.ModelSerializer):
    mine = serializers.SerializerMethodField()
    text = serializers.CharField(source="body", read_only=True)
    time = serializers.SerializerMethodField()

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
        ]

    def get_mine(self, obj):
        return obj.direction == "out"

    def get_time(self, obj):
        if not obj.created_at:
            return ""
        dt = timezone.localtime(obj.created_at)
        return dt.strftime("%I:%M %p").lower()
