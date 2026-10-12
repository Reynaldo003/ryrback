# logs/serializers.py
from rest_framework import serializers

from .models import LogActividad


class LogActividadSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.SerializerMethodField()
    modulo_etiqueta = serializers.CharField(read_only=True)

    class Meta:
        model = LogActividad
        fields = [
            "id",
            "usuario",
            "usuario_nombre",
            "modulo",
            "modulo_etiqueta",
            "tipo",
            "entidad",
            "cambio",
            "ip",
            "fecha",
        ]

    def get_usuario_nombre(self, obj):
        usuario = obj.usuario
        if usuario is None:
            return "Anónimo"
        return f"{usuario.nombre} {usuario.apellidos or ''}".strip() or usuario.usuario