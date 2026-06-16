from rest_framework import serializers

from .models import OrdenServicioVW


class OrdenServicioVWSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrdenServicioVW
        fields = (
            "chassi",
            "cliente_veiculo",
            "marca_auto",
            "modelo_auto",
            "num_os",
            "fecha_os",
            "fecha_emision",
            "fecha_salida",
            "estado",
            "dias_os_a_actual",
            "segmento",
            "meses_actual_a_emision",
            "num_nota",
            "total_nota",
            "subtipo_os",
            "telefono",
            "correo",
            "nombre",
            "serie",
            "total_servicio",
        )
        read_only_fields = fields