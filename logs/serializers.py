# logs/serializers.py
from rest_framework import serializers

from .models import LogActividad


class LogActividadSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.SerializerMethodField()
    modulo_etiqueta = serializers.CharField(read_only=True)
    restaurable = serializers.SerializerMethodField()

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
            "restaurable",
        ]

    def get_usuario_nombre(self, obj):
        usuario = obj.usuario
        if usuario is None:
            return "Anónimo"
        return f"{usuario.nombre} {usuario.apellidos or ''}".strip() or usuario.usuario

    def get_restaurable(self, obj):
        """Solo los ELIMINAR con snapshot completo y sin purga son restaurables."""
        if obj.tipo != "ELIMINAR":
            return False
        datos = obj.datos
        return bool(
            isinstance(datos, dict)
            and datos.get("modelo")
            and datos.get("campos")
            and not datos.get("purgado")
        )