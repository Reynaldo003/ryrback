#hojaingresos/serializers.py
from rest_framework import serializers

from citas.models import ClienteComercial, normaliza_tel_mx
from .models import HojaIngresos


def obtener_atributo(obj, nombres, default=""):
    for nombre in nombres:
        valor = getattr(obj, nombre, None)
        if valor not in (None, ""):
            return valor
    return default


def asignar_si_existe(obj, campo, valor):
    if valor not in (None, "") and hasattr(obj, campo):
        setattr(obj, campo, valor)


class HojaIngresosSerializer(serializers.ModelSerializer):
    telefono = serializers.CharField(source="cliente.telefono", read_only=True)
    correo = serializers.CharField(source="cliente.correo", read_only=True)
    cliente_nombre = serializers.CharField(source="cliente.nombre", read_only=True)

    cliente_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    cliente_telefono = serializers.CharField(required=False, allow_blank=True, write_only=True)
    cliente_correo_electronico = serializers.CharField(required=False, allow_blank=True, write_only=True)

    citado = serializers.BooleanField(required=False)
    asistencia = serializers.BooleanField(required=False)
    agendado_por = serializers.CharField(read_only=True)


    class Meta:
        model = HojaIngresos
        fields = "__all__"
        extra_kwargs = {
            "cliente": {"required": False},
        }
        
    def get_cliente(self, obj):
        cliente = getattr(obj, "cliente", None)

        if not cliente:
            return None

        return {
            "id": getattr(cliente, "id_cliente", None),
            "nombre": obtener_atributo(cliente, ["nombre", "nombre_cliente", "cliente"]),
            "telefono": obtener_atributo(cliente, ["telefono", "celular", "telefono_cliente"]),
            "correo_electronico": obtener_atributo(
                cliente,
                ["correo_electronico", "correo", "email"],
            ),
        }

    def get_telefono(self, obj):
        cliente = getattr(obj, "cliente", None)
        if not cliente:
            return ""
        return obtener_atributo(cliente, ["telefono", "celular", "telefono_cliente"])

    def get_correo_electronico(self, obj):
        cliente = getattr(obj, "cliente", None)
        if not cliente:
            return ""
        return obtener_atributo(cliente, ["correo_electronico", "correo", "email"])

    def validate(self, attrs):
        request = self.context.get("request")
        metodo = getattr(request, "method", "").upper()

        cliente_id = attrs.get("cliente_id")
        telefono = attrs.get("cliente_telefono", "")

        if metodo == "POST" and not cliente_id and not str(telefono).strip():
            raise serializers.ValidationError({
                "cliente_telefono": "El teléfono del cliente es obligatorio."
            })

        return attrs

    def _resolver_cliente(self, validated_data, instance=None):
        cliente_id = validated_data.pop("cliente_id", None)
        nombre = str(validated_data.pop("cliente_nombre", "") or "").strip()
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
            asignar_si_existe(cliente, "telefono", telefono_normalizado)

        if nombre:
            asignar_si_existe(cliente, "nombre", nombre)
            asignar_si_existe(cliente, "nombre_cliente", nombre)

        if correo:
            asignar_si_existe(cliente, "correo_electronico", correo)
            asignar_si_existe(cliente, "correo", correo)
            asignar_si_existe(cliente, "email", correo)

        cliente.save()

        if nombre:
            validated_data["nombre_cliente"] = nombre
        elif not validated_data.get("nombre_cliente"):
            validated_data["nombre_cliente"] = obtener_atributo(
                cliente,
                ["nombre", "nombre_cliente", "cliente"],
            )

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

        instance.save()
        return instance