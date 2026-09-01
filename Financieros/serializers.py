#Financieros/serializers.py
from django.db import transaction
from rest_framework import serializers

from citas.models import ClienteComercial, normaliza_tel_mx
from .models import SolicitudCredito, LongDrive


class ClienteComercialMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClienteComercial
        fields = ("id_cliente", "nombre", "telefono", "correo")


class BaseClienteComercialSerializer(serializers.ModelSerializer):
    cliente = ClienteComercialMiniSerializer(read_only=True)

    cliente_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    nombre = serializers.CharField(write_only=True, required=False, allow_blank=True, default="")
    telefono = serializers.CharField(write_only=True, required=False, allow_blank=True, default="")
    correo = serializers.EmailField(write_only=True, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        attrs = super().validate(attrs)

        telefono = attrs.get("telefono", None)
        cliente_id = attrs.get("cliente_id", None)

        if self.instance is None:
            if not cliente_id and not str(telefono or "").strip():
                raise serializers.ValidationError({
                    "telefono": "El teléfono es requerido para crear el registro."
                })

        if telefono is not None and str(telefono).strip():
            telefono_normalizado = normaliza_tel_mx(telefono)
            if not telefono_normalizado:
                raise serializers.ValidationError({
                    "telefono": "Teléfono inválido. Debe tener 10 dígitos o 52 + 10 dígitos."
                })
            attrs["telefono"] = telefono_normalizado

        return attrs

    def _resolver_cliente(self, validated_data):
        cliente_id = validated_data.pop("cliente_id", None)
        nombre = validated_data.pop("nombre", "")
        telefono = validated_data.pop("telefono", "")
        correo = validated_data.pop("correo", "")

        if cliente_id:
            try:
                cliente = ClienteComercial.objects.get(pk=cliente_id)
            except ClienteComercial.DoesNotExist:
                raise serializers.ValidationError({
                    "cliente_id": "El cliente indicado no existe."
                })

            cambios = False

            if nombre is not None and str(nombre).strip() != cliente.nombre:
                cliente.nombre = nombre
                cambios = True

            if correo is not None and str(correo).strip() != (cliente.correo or ""):
                cliente.correo = correo
                cambios = True

            if telefono:
                telefono_normalizado = normaliza_tel_mx(telefono)
                if not telefono_normalizado:
                    raise serializers.ValidationError({
                        "telefono": "Teléfono inválido."
                    })

                if telefono_normalizado != cliente.telefono:
                    existe = ClienteComercial.objects.filter(telefono=telefono_normalizado).exclude(pk=cliente.pk).exists()
                    if existe:
                        raise serializers.ValidationError({
                            "telefono": "Ya existe otro cliente con ese teléfono."
                        })
                    cliente.telefono = telefono_normalizado
                    cambios = True

            if cambios:
                cliente.save()

            return cliente

        telefono = normaliza_tel_mx(telefono)
        if not telefono:
            raise serializers.ValidationError({
                "telefono": "El teléfono es requerido."
            })

        cliente, creado = ClienteComercial.objects.get_or_create(
            telefono=telefono,
            defaults={
                "nombre": nombre or "",
                "correo": correo or "",
            },
        )

        cambios = False

        if nombre is not None and str(nombre).strip() and cliente.nombre != nombre:
            cliente.nombre = nombre
            cambios = True

        if correo is not None and cliente.correo != correo:
            cliente.correo = correo
            cambios = True

        if cambios:
            cliente.save()

        return cliente


class SolicitudCreditoSerializer(BaseClienteComercialSerializer):
    class Meta:
        model = SolicitudCredito
        fields = (
            "id",
            "cliente",
            "cliente_id",
            "nombre",
            "telefono",
            "correo",
            "agencia",
            "id_soli_cred",
            "producto_financiero",
            "plazo_meses",
            "monto_financiero",
            "auto_interes",
            "canal_origen",
            "asesor_ventas",
            "estado_financiamiento",
            "estado_compra",
            "fecha_respuesta",
            "comentarios",
            "creado",
        )

        read_only_fields = (
            "id",
            "cliente",
        )

    @transaction.atomic
    def create(self, validated_data):
        cliente = self._resolver_cliente(validated_data)

        return SolicitudCredito.objects.create(
            cliente=cliente,
            **validated_data
        )

    @transaction.atomic
    def update(self, instance, validated_data):
        cliente = self._resolver_cliente(validated_data) if (
            "cliente_id" in validated_data or
            "nombre" in validated_data or
            "telefono" in validated_data or
            "correo" in validated_data
        ) else instance.cliente

        instance.cliente = cliente

        campos = [
            "agencia",
            "id_soli_cred",
            "producto_financiero",
            "plazo_meses",
            "monto_financiero",
            "auto_interes",
            "canal_origen",
            "asesor_ventas",
            "estado_financiamiento",
            "estado_compra",
            "fecha_respuesta",
            "comentarios",
            "creado",
        ]

        for campo in campos:
            if campo in validated_data:
                setattr(instance, campo, validated_data[campo])

        instance.save()

        return instance

class LongDriveSerializer(BaseClienteComercialSerializer):
    class Meta:
        model = LongDrive
        fields = (
            "id",
            "cliente",
            "cliente_id",
            "nombre",
            "telefono",
            "correo",
            "agencia",
            "chasis",
            "producto_long_drive",
            "tipo_venta",
            "fecha_entrega",
            "creado",
        )
        read_only_fields = ("id", "cliente", "creado")

    @transaction.atomic
    def create(self, validated_data):
        cliente = self._resolver_cliente(validated_data)

        return LongDrive.objects.create(cliente=cliente, **validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        cliente = self._resolver_cliente(validated_data) if (
            "cliente_id" in validated_data or
            "nombre" in validated_data or
            "telefono" in validated_data or
            "correo" in validated_data
        ) else instance.cliente

        instance.cliente = cliente

        campos = [
            "agencia",
            "chasis",
            "producto_long_drive",
            "tipo_venta",
            "fecha_entrega",
        ]

        for campo in campos:
            if campo in validated_data:
                setattr(instance, campo, validated_data[campo])

        instance.save()
        return instance