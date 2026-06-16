#PedidosPiezas/serializers.py
import re
from django.db import transaction
from rest_framework import serializers

from .models import PedidosPiezas, Piezas, PedidoPiezaDetalle


class PiezasSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="id_pieza", read_only=True)
    numeroParte = serializers.CharField(source="codigo")
    descripcion = serializers.CharField(source="nombre")

    class Meta:
        model = Piezas
        fields = [
            "id",
            "numeroParte",
            "descripcion",
            "costo",
        ]
        read_only_fields = ["id"]

    def validate_numeroParte(self, value):
        value = (value or "").strip().upper()
        if not value:
            raise serializers.ValidationError("El número de parte es obligatorio.")
        if not re.match(r"^[A-Za-z0-9\-/. ]+$", value):
            raise serializers.ValidationError(
                "Solo se permiten letras, números, espacios y - / ."
            )
        return value

    def validate_descripcion(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("La descripción es obligatoria.")
        return value

class PedidoPiezaDetalleSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="id_detalle", read_only=True)
    piezaId = serializers.PrimaryKeyRelatedField(
        source="pieza",
        queryset=Piezas.objects.all(),
        required=False,
        allow_null=True,
    )
    numeroParte = serializers.CharField(source="numero_parte", required=False, allow_blank=True)
    tipoPedido = serializers.CharField(source="tipo_pedido", required=False, allow_blank=True)
    costoUnitario = serializers.DecimalField(
        source="costo_unitario",
        max_digits=12,
        decimal_places=2,
        required=False,
    )
    fechaLlegada = serializers.DateField(
        source="fecha_llegada",
        required=False,
        allow_null=True,
    )

    class Meta:
        model = PedidoPiezaDetalle
        fields = [
            "id",
            "piezaId",
            "numeroParte",
            "descripcion",
            "cantidad",
            "tipoPedido",
            "estatus",
            "costoUnitario",
            "fechaLlegada",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        pieza = attrs.get("pieza")
        numero_parte = (attrs.get("numero_parte") or "").strip().upper()
        descripcion = (attrs.get("descripcion") or "").strip()
        tipo_pedido = (attrs.get("tipo_pedido") or "").strip()
        estatus = (attrs.get("estatus") or "").strip()
        cantidad = attrs.get("cantidad")
        costo_unitario = attrs.get("costo_unitario", None)

        if pieza:
            if not numero_parte:
                numero_parte = (pieza.codigo or "").strip().upper()
            if not descripcion:
                descripcion = (pieza.nombre or "").strip()
            if costo_unitario is None:
                costo_unitario = pieza.costo

        if not numero_parte:
            raise serializers.ValidationError({
                "numeroParte": "El número de parte es obligatorio."
            })

        if not re.match(r"^[A-Za-z0-9\-/. ]+$", numero_parte):
            raise serializers.ValidationError({
                "numeroParte": "Solo se permiten letras, números, espacios y - / ."
            })

        if not descripcion:
            raise serializers.ValidationError({
                "descripcion": "La descripción es obligatoria."
            })

        if cantidad is None:
            raise serializers.ValidationError({
                "cantidad": "La cantidad es obligatoria."
            })

        if int(cantidad) <= 0:
            raise serializers.ValidationError({
                "cantidad": "La cantidad debe ser mayor a 0."
            })

        attrs["numero_parte"] = numero_parte
        attrs["descripcion"] = descripcion
        attrs["tipo_pedido"] = tipo_pedido
        attrs["estatus"] = estatus

        if costo_unitario is not None:
            attrs["costo_unitario"] = costo_unitario

        return attrs

class PedidosPiezasSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="id_pedido", read_only=True)
    numeroPedido = serializers.CharField(source="numero_pedido")
    creadoEn = serializers.DateTimeField(source="creado", read_only=True)
    fechaPedido = serializers.DateField(source="fecha_pedido", required=False)
    fechaProgramadaLlegada = serializers.DateField(
        source="fecha_programada_llegada",
        required=False,
        allow_null=True,
    )
    nombreCliente = serializers.CharField(source="nombre_cliente")
    ordenServicio = serializers.CharField(source="orden_servicio")
    ticketSar = serializers.CharField(source="ticket_sar", required=False, allow_blank=True)
    piezas = PedidoPiezaDetalleSerializer(many=True)

    totalPiezas = serializers.SerializerMethodField()
    piezasEntregadas = serializers.SerializerMethodField()
    progreso = serializers.SerializerMethodField()

    class Meta:
        model = PedidosPiezas
        fields = [
            "id",
            "numeroPedido",
            "creadoEn",
            "fechaPedido",
            "fechaProgramadaLlegada",
            "dealer",
            "nombreCliente",
            "asesor",
            "ordenServicio",
            "ticketSar",
            "canal",
            "estatus",
            "piezas",
            "totalPiezas",
            "piezasEntregadas",
            "progreso",
        ]
        read_only_fields = [
            "id",
            "creadoEn",
            "totalPiezas",
            "piezasEntregadas",
            "progreso",
        ]

    def get_totalPiezas(self, obj):
        return sum(int(item.cantidad or 0) for item in obj.piezas.all())

    def get_piezasEntregadas(self, obj):
        return sum(
            int(item.cantidad or 0)
            for item in obj.piezas.all()
            if (item.estatus or "").strip().lower() == "entregadas"
        )

    def get_progreso(self, obj):
        total = self.get_totalPiezas(obj)
        if total <= 0:
            return 0
        entregadas = self.get_piezasEntregadas(obj)
        return round((entregadas / total) * 100)

    def validate_numeroPedido(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("El número de pedido es obligatorio.")

        queryset = PedidosPiezas.objects.filter(numero_pedido=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError("Ya existe un pedido con ese número.")

        return value

    def validate(self, attrs):
        for campo in [
            "dealer",
            "nombre_cliente",
            "asesor",
            "orden_servicio",
            "ticket_sar",
            "canal",
            "estatus",
        ]:
            if campo in attrs and isinstance(attrs.get(campo), str):
                attrs[campo] = attrs[campo].strip()

        nombre_cliente = attrs.get("nombre_cliente")
        if nombre_cliente is not None:
            if not nombre_cliente:
                raise serializers.ValidationError({
                    "nombreCliente": "El nombre del cliente es obligatorio."
                })
            if not re.match(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s]+$", nombre_cliente):
                raise serializers.ValidationError({
                    "nombreCliente": "El nombre del cliente solo acepta letras y espacios."
                })

        orden_servicio = attrs.get("orden_servicio")
        if orden_servicio is not None:
            if not orden_servicio:
                raise serializers.ValidationError({
                    "ordenServicio": "La orden de servicio es obligatoria."
                })
            if not orden_servicio.isdigit():
                raise serializers.ValidationError({
                    "ordenServicio": "La orden de servicio solo acepta números."
                })

        fecha_pedido = attrs.get(
            "fecha_pedido",
            self.instance.fecha_pedido if self.instance else None
        )
        fecha_programada_llegada = attrs.get(
            "fecha_programada_llegada",
            self.instance.fecha_programada_llegada if self.instance else None
        )

        if fecha_pedido and fecha_programada_llegada and fecha_programada_llegada < fecha_pedido:
            raise serializers.ValidationError({
                "fechaProgramadaLlegada": "No puede ser menor que la fecha del pedido."
            })

        piezas = attrs.get("piezas", None)

        if self.instance is None and (piezas is None or len(piezas) == 0):
            raise serializers.ValidationError({
                "piezas": "Debes agregar al menos una pieza al pedido."
            })

        if piezas is not None and len(piezas) == 0:
            raise serializers.ValidationError({
                "piezas": "Debes agregar al menos una pieza al pedido."
            })

        if piezas is not None:
            errores_piezas = []

            for pieza in piezas:
                error_pieza = {}

                fecha_llegada = pieza.get("fecha_llegada")
                estatus_pieza = (pieza.get("estatus") or "").strip().lower()

                if fecha_llegada and fecha_pedido and fecha_llegada < fecha_pedido:
                    error_pieza["fechaLlegada"] = "No puede ser menor que la fecha del pedido."

                if estatus_pieza == "entregadas" and not fecha_llegada:
                    error_pieza["fechaLlegada"] = "Captura la fecha de llegada de la pieza."

                errores_piezas.append(error_pieza)

            if any(bool(item) for item in errores_piezas):
                raise serializers.ValidationError({
                    "piezas": errores_piezas
                })

        return attrs

    def _guardar_piezas(self, pedido, piezas_data):
        for pieza_data in piezas_data:
            PedidoPiezaDetalle.objects.create(
                pedido=pedido,
                **pieza_data,
            )

    @transaction.atomic
    def create(self, validated_data):
        piezas_data = validated_data.pop("piezas", [])
        pedido = PedidosPiezas.objects.create(**validated_data)
        self._guardar_piezas(pedido, piezas_data)
        return pedido

    @transaction.atomic
    def update(self, instance, validated_data):
        piezas_data = validated_data.pop("piezas", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if piezas_data is not None:
            instance.piezas.all().delete()
            self._guardar_piezas(instance, piezas_data)

        return instance