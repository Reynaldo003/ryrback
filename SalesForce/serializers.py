from rest_framework import serializers

from .models import (
    ActividadProceso, ActividadProspecto, EntregaComercial, FacturaComercial,
    ImportacionComercial, ProcesoComercial, ProcesoComercialDetalle, Prospecto,
)


class SalesforceSerializer(serializers.ModelSerializer):
    """El JSON de origen se conserva, pero no se modifica desde el CRUD manual."""

    class Meta:
        abstract = True


class ProspectoSerializer(SalesforceSerializer):
    class Meta:
        model = Prospecto
        fields = "__all__"
        read_only_fields = ("datos_origen", "sincronizado_en")


class ProcesoComercialSerializer(SalesforceSerializer):
    class Meta:
        model = ProcesoComercial
        fields = "__all__"
        read_only_fields = ("datos_origen", "sincronizado_en")


class ProcesoDetalleSerializer(SalesforceSerializer):
    class Meta:
        model = ProcesoComercialDetalle
        fields = "__all__"
        read_only_fields = ("datos_origen", "sincronizado_en")


class ActividadProspectoSerializer(SalesforceSerializer):
    class Meta:
        model = ActividadProspecto
        fields = "__all__"
        read_only_fields = ("datos_origen", "sincronizado_en")


class ActividadProcesoSerializer(SalesforceSerializer):
    class Meta:
        model = ActividadProceso
        fields = "__all__"
        read_only_fields = ("datos_origen", "sincronizado_en")


class FacturaComercialSerializer(SalesforceSerializer):
    class Meta:
        model = FacturaComercial
        fields = "__all__"
        read_only_fields = ("datos_origen", "sincronizado_en")


class EntregaComercialSerializer(SalesforceSerializer):
    class Meta:
        model = EntregaComercial
        fields = "__all__"
        read_only_fields = ("datos_origen", "sincronizado_en")


class ImportacionComercialSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportacionComercial
        fields = "__all__"
        read_only_fields = [campo.name for campo in ImportacionComercial._meta.fields]


class ArchivoImportacionSerializer(serializers.Serializer):
    tabla = serializers.CharField(max_length=80)
    archivo = serializers.FileField()
    huella = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        from .importador import TABLAS, archivo_legible

        if attrs["tabla"] not in TABLAS:
            raise serializers.ValidationError({"tabla": "No existe esa tabla."})
        try:
            archivo_legible(attrs["archivo"])
        except ValueError as exc:
            raise serializers.ValidationError({"archivo": str(exc)}) from exc
        return attrs
