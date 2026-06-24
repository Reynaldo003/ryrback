# hojaingresos/serializers.py
from rest_framework import serializers

from citas.models import ClienteComercial, normaliza_tel_mx
from .models import HojaIngresos


class HojaIngresosSerializer(serializers.ModelSerializer):
    # Campos de salida del cliente
    telefono = serializers.CharField(source="cliente.telefono", read_only=True)
    correo = serializers.CharField(source="cliente.correo", read_only=True)

    # Este campo se recibe desde frontend, pero también lo devolvemos manualmente
    cliente_nombre = serializers.CharField(required=False, allow_blank=True, write_only=True)

    # Campos auxiliares de entrada
    cliente_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    cliente_telefono = serializers.CharField(required=False, allow_blank=True, write_only=True)
    cliente_correo_electronico = serializers.CharField(required=False, allow_blank=True, write_only=True)

    citado = serializers.BooleanField(required=False)
    asistencia = serializers.BooleanField(required=False)

    class Meta:
        model = HojaIngresos
        fields = "__all__"
        extra_kwargs = {
            "cliente": {"required": False},
            # Si ya no quieres que el frontend modifique este duplicado directamente:
            "nombre_cliente": {"required": False, "allow_blank": True},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)

        cliente = getattr(instance, "cliente", None)

        nombre_cliente = ""
        telefono = ""
        correo = ""

        if cliente:
            nombre_cliente = str(getattr(cliente, "nombre", "") or "").strip()
            telefono = str(getattr(cliente, "telefono", "") or "").strip()
            correo = str(getattr(cliente, "correo", "") or "").strip()

        # Fuente real para frontend
        data["cliente_nombre"] = nombre_cliente
        data["telefono"] = telefono
        data["correo"] = correo

        # Para compatibilidad con tu frontend actual y datos viejos.
        # Pero ya debe reflejar lo que hay en ClienteComercial.
        data["nombre_cliente"] = nombre_cliente or str(getattr(instance, "nombre_cliente", "") or "").strip()

        return data

    def validate(self, attrs):
        request = self.context.get("request")
        metodo = getattr(request, "method", "").upper()

        cliente_id = attrs.get("cliente_id")
        telefono = str(attrs.get("cliente_telefono", "") or "").strip()

        nombre_payload = (
            str(attrs.get("cliente_nombre", "") or "").strip()
            or str(attrs.get("nombre_cliente", "") or "").strip()
        )

        cliente_existente = None

        if cliente_id:
            cliente_existente = ClienteComercial.objects.filter(
                id_cliente=cliente_id
            ).first()

            if not cliente_existente:
                raise serializers.ValidationError({
                    "cliente_id": "El cliente indicado no existe."
                })

        nombre_existente = ""
        if cliente_existente:
            nombre_existente = str(getattr(cliente_existente, "nombre", "") or "").strip()

        if metodo == "POST":
            if not cliente_id and not telefono:
                raise serializers.ValidationError({
                    "cliente_telefono": "El teléfono del cliente es obligatorio."
                })

            if not nombre_payload and not nombre_existente:
                raise serializers.ValidationError({
                    "cliente_nombre": "El nombre del cliente es obligatorio."
                })

        return attrs

    def _resolver_cliente(self, validated_data, instance=None):
        cliente_id = validated_data.pop("cliente_id", None)

        nombre = (
            str(validated_data.pop("cliente_nombre", "") or "").strip()
            or str(validated_data.pop("nombre_cliente", "") or "").strip()
        )

        telefono_raw = str(validated_data.pop("cliente_telefono", "") or "").strip()
        correo = str(validated_data.pop("cliente_correo_electronico", "") or "").strip()

        cliente = None

        if cliente_id:
            cliente = ClienteComercial.objects.filter(id_cliente=cliente_id).first()

        telefono_normalizado = normaliza_tel_mx(telefono_raw) if telefono_raw else ""

        if cliente is None and telefono_normalizado:
            cliente = ClienteComercial.objects.filter(
                telefono=telefono_normalizado
            ).first()

        if cliente is None and instance is not None:
            cliente = instance.cliente

        if cliente is None:
            cliente = ClienteComercial()

        if telefono_normalizado:
            cliente.telefono = telefono_normalizado

        if nombre:
            cliente.nombre = nombre

        if correo:
            cliente.correo = correo

        cliente.save()

        if cliente.nombre:
            validated_data["nombre_cliente"] = cliente.nombre

        return cliente

    def create(self, validated_data):
        cliente = self._resolver_cliente(validated_data)

        return HojaIngresos.objects.create(
            cliente=cliente,
            **validated_data,
        )

    def update(self, instance, validated_data):
        cliente = self._resolver_cliente(validated_data, instance=instance)

        instance.cliente = cliente

        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)

        # Blindaje final: si el cliente tiene nombre, sincronizamos.
        if cliente.nombre:
            instance.nombre_cliente = cliente.nombre

        instance.save()
        return instance