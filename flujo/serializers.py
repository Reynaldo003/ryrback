# flujo/serializers.py

from rest_framework import serializers

from .models import DiagramaFlujo


class DiagramaFlujoSerializer(serializers.ModelSerializer):
    usuario_id = serializers.IntegerField(
        source="usuario.id_usuario",
        read_only=True,
    )

    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = DiagramaFlujo
        fields = [
            "id",
            "usuario_id",
            "usuario_nombre",
            "nombre",
            "descripcion",
            "pasos",
            "nodos",
            "conexiones",
            "metadatos",
            "total_pasos",
            "total_nodos",
            "total_conexiones",
            "total_decisiones",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = [
            "id",
            "usuario_id",
            "usuario_nombre",
            "total_pasos",
            "total_nodos",
            "total_conexiones",
            "total_decisiones",
            "creado_en",
            "actualizado_en",
        ]

    def get_usuario_nombre(self, obj):
        if not obj.usuario:
            return ""

        nombre = str(obj.usuario.nombre or "").strip()
        apellidos = str(obj.usuario.apellidos or "").strip()

        return f"{nombre} {apellidos}".strip()

    def validate_nombre(self, value):
        value = str(value or "").strip()

        if not value:
            raise serializers.ValidationError("El nombre del diagrama es obligatorio.")

        if len(value) > 180:
            raise serializers.ValidationError("El nombre no puede exceder 180 caracteres.")

        return value

    def validate_pasos(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("pasos debe ser una lista.")
        return value

    def validate_nodos(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("nodos debe ser una lista.")
        return value

    def validate_conexiones(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("conexiones debe ser una lista.")
        return value

    def validate_metadatos(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("metadatos debe ser un objeto JSON.")
        return value