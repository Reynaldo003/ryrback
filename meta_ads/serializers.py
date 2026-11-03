# meta_ads/serializers.py
from rest_framework import serializers

from .models import CampanaMeta


class CampanaMetaListSerializer(serializers.ModelSerializer):
    resultados_indicador = serializers.IntegerField(read_only=True)
    inversion_indicador = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = CampanaMeta
        fields = (
            "id_campana",
            "id_concesionaria",
            "sucursal",
            "inicio_informe",
            "fin_informe",
            "nombre_campana",
            "estado_campana",
            "objetivo_campana",
            "inicio_campana",
            "fin_campana",
            "total_resultados",
            "messaging_first_reply",
            "alcance",
            "impresiones",
            "presupuesto_anuncio",
            "coste_resultados",
            "importe_gastado",
            "resultados_indicador",
            "inversion_indicador",
        )


class CampanaMetaSerializer(serializers.ModelSerializer):
    """
    Serializer completo solo para detalle o uso administrativo.
    """

    resultados_indicador = serializers.IntegerField(read_only=True)
    inversion_indicador = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = CampanaMeta
        fields = [field.name for field in CampanaMeta._meta.fields] + [
            "resultados_indicador",
            "inversion_indicador",
        ]
