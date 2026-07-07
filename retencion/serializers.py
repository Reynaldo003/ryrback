# retencion/serializers.py
from rest_framework import serializers

from .models import OrdenServicioCompletaVW, OrdenServicioVentaVW


class OrdenServicioVentaVWSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrdenServicioVentaVW
        fields = (
            "vin",
            "agencia",
            "fecha_venta",
            "fecha_salida",
            "numero_nota",
            "total_nota",
            "marca",
            "modelo_codigo",
            "modelo_nombre",
            "condicion_vehiculo",
            "nombre_cliente",
            "telefono_cliente",
            "correo_cliente",
            "ultima_orden_servicio",
            "tipo_orden",
            "subtipo_orden",
            "fecha_ultima_os",
            "situacion_os",
            "cliente_vehiculo",
            "placa_vehiculo",
            "kilometraje",
            "medio_contacto",
            "total_ultimo_servicio",
            "estado_actividad",
            "meses_desde_venta",
            "segmento",
        )
        read_only_fields = fields


class OrdenServicioCompletaVWSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrdenServicioCompletaVW
        fields = (
            "vin",
            "agencia",
            "fecha_venta",
            "fecha_salida",
            "numero_nota",
            "total_nota",
            "marca",
            "modelo_codigo",
            "modelo_nombre",
            "condicion_vehiculo",
            "nombre_cliente",
            "telefono_cliente",
            "telefono_cliente2",
            "telefono_cliente3",
            "correo_cliente",
            "correo_cliente",
            "numero_orden_servicio",
            "tipo_orden",
            "subtipo_orden",
            "fecha_os",
            "situacion_os",
            "cliente_vehiculo",
            "placa_vehiculo",
            "kilometraje",
            "medio_contacto",
            "total_servicio",
            "estado_actividad",
            "meses_desde_venta",
            "segmento",
        )
        read_only_fields = fields