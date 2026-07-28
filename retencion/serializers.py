# retencion/serializers.py
from rest_framework import serializers

from .models import OrdenServicioCompletaVW, OrdenServicioVentaVW, TareaCliente



class TareaClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TareaCliente
        fields = (
            "id",
            "telefono_cliente",
            "nombre_cliente",
            "titulo",
            "descripcion",
            "forma_contacto",
            "motivo_contacto",
            "resultado",
            "estado",
            "fecha_limite",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_telefono_cliente(self, value):
        limpio = (value or "").strip()
        if not limpio:
            raise serializers.ValidationError("El teléfono del cliente es requerido.")
        return limpio

    def validate_titulo(self, value):
        limpio = (value or "").strip()
        if not limpio:
            raise serializers.ValidationError("El título de la tarea es requerido.")
        return limpio


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