
# retencion/serializers_postgres.py
# Serializers de prueba para PostgreSQL.
# No reemplazan los serializers actuales.

from rest_framework import serializers

from .models_postgres import (
    OrdenServicioVentaPostgres,
    OrdenServicioHistorialPostgres,
)


class OrdenServicioVentaPostgresSerializer(serializers.ModelSerializer):
    agencia = serializers.SerializerMethodField()

    class Meta:
        model = OrdenServicioVentaPostgres
        fields = "__all__"

    def get_agencia(self, obj):
        if obj.fecha_venta is None:
            return obj.agencia_servicio
        return obj.agencia_venta


class OrdenServicioHistorialPostgresSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = OrdenServicioHistorialPostgres
        fields = "__all__"
