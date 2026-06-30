from rest_framework import serializers
from .models import Bitacora, Reactivo, Evidencia


class EvidenciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evidencia
        fields = ["id", "archivo", "subido_en"]


class ReactivoSerializer(serializers.ModelSerializer):
    evidencias = EvidenciaSerializer(many=True, read_only=True)

    class Meta:
        model = Reactivo
        fields = ["id", "reactivo_id", "titulo", "estado", "observaciones", "evidencias"]


class BitacoraSerializer(serializers.ModelSerializer):
    reactivos = ReactivoSerializer(many=True, read_only=True)

    class Meta:
        model = Bitacora
        fields = [
            "id",
            "folio",
            "chasis_vin",
            "fecha_ingreso",
            "anio_modelo_color",
            "responsable",
            "fecha_captura",
            "creado_en",
            "reactivos",
        ]