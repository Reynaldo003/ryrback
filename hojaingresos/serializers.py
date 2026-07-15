# hojaingresos/serializers.py
import re
from datetime import time

from django.db import transaction
from rest_framework import serializers

from citas.models import ClienteComercial
from .models import HojaIngresos, TallerActividad


CAMPOS_TALLER = (
    "tecnico",
    "etapa",
    "estatus_agenda",
    "fecha_programada",
    "hora_inicio",
    "hora_fin",
    "tipo_bloque",
    "tipo_servicio",
    "comentarios_taller",
)

ETAPAS_TERMINADAS = {
    "Terminado",
    "Autos terminados no entregados",
}

TIPOS_BLOQUE_SIN_CLIENTE = {
    "comida",
    "capacitacion",
}

HORA_INICIO_AGENDA = time(7, 0)
HORA_FIN_AGENDA = time(20, 0)


def normalizar_telefono(value):
    """Normalización sencilla sin asumir que el teléfono es único."""
    return re.sub(r"\D", "", str(value or ""))


def dividir_servicios(value):
    """
    Convierte `Diagnóstico + Garantía` en una lista para el frontend.

    No se divide por la palabra `y`, porque existen servicios como
    `Hojalatería y pintura`.
    """
    texto = str(value or "").strip()
    if not texto:
        return []

    return [
        parte.strip()
        for parte in re.split(r"\s*(?:\+|,|;|\n)\s*", texto)
        if parte.strip()
    ]


def obtener_correo_cliente(cliente):
    if not cliente:
        return ""

    return str(
        getattr(cliente, "correo", "")
        or getattr(cliente, "correo_electronico", "")
        or ""
    ).strip()


def asignar_correo_cliente(cliente, correo):
    correo = str(correo or "").strip().lower()
    if not cliente or not correo:
        return

    nombres_campos = {campo.name for campo in cliente._meta.fields}
    if "correo" in nombres_campos:
        cliente.correo = correo
    elif "correo_electronico" in nombres_campos:
        cliente.correo_electronico = correo


class HojaIngresosSerializer(serializers.ModelSerializer):
    # Alias compatibles con Taller.jsx.
    cliente = serializers.CharField(required=False, allow_blank=True)
    cliente_id = serializers.IntegerField(required=False, allow_null=True)
    cliente_nombre = serializers.CharField(required=False, allow_blank=True)
    cliente_telefono = serializers.CharField(required=False, allow_blank=True)
    cliente_correo_electronico = serializers.CharField(
        required=False,
        allow_blank=True,
    )
    telefono = serializers.CharField(required=False, allow_blank=True)
    correo = serializers.CharField(required=False, allow_blank=True)

    # Campos que físicamente pertenecen a TallerActividad.
    tecnico = serializers.CharField(required=False, allow_blank=True)
    etapa = serializers.CharField(required=False, allow_blank=True)
    estatus_agenda = serializers.CharField(required=False, allow_blank=True)
    fecha_programada = serializers.DateField(required=False, allow_null=True)
    hora_inicio = serializers.TimeField(
        required=False,
        allow_null=True,
        format="%H:%M",
        input_formats=("%H:%M", "%H:%M:%S"),
    )
    hora_fin = serializers.TimeField(
        required=False,
        allow_null=True,
        format="%H:%M",
        input_formats=("%H:%M", "%H:%M:%S"),
    )
    tipo_bloque = serializers.CharField(required=False, allow_blank=True)
    tipo_servicio = serializers.CharField(required=False, allow_blank=True)
    comentarios_taller = serializers.CharField(required=False, allow_blank=True)

    # Compatibilidad con el arreglo usado por el frontend.
    subtrabajos = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        write_only=True,
    )
    horasAgenda = serializers.SerializerMethodField()
    horasTotales = serializers.SerializerMethodField()
    isManual = serializers.SerializerMethodField()

    class Meta:
        model = HojaIngresos
        fields = (
            "id",
            "cliente",
            "cliente_id",
            "cliente_nombre",
            "cliente_telefono",
            "cliente_correo_electronico",
            "telefono",
            "correo",
            "agencia",
            "no_orden",
            "fecha_ingreso",
            "asistencia",
            "diss",
            "pauta",
            "indicador_resultados",
            "alcance",
            "citado",
            "torre",
            "asesor",
            "agendado_por",
            "nombre_cliente",
            "tipo_cita",
            "declaracion_textual_cliente",
            "comentarios",
            "vin",
            "anio_vehiculo",
            "modelo",
            "medio_concertacion",
            "pauta_origen",
            "venta_mano_obra",
            "asesor_digital",
            "asesor_piso",
            "creado_en",
            "actualizado_en",
            # TallerActividad
            "tecnico",
            "etapa",
            "estatus_agenda",
            "fecha_programada",
            "hora_inicio",
            "hora_fin",
            "tipo_bloque",
            "tipo_servicio",
            "comentarios_taller",
            "subtrabajos",
            "horasAgenda",
            "horasTotales",
            "isManual",
        )
        read_only_fields = (
            "id",
            "creado_en",
            "actualizado_en",
        )

    def _obtener_taller(self, instance):
        if instance is None:
            return None

        try:
            return instance.taller
        except TallerActividad.DoesNotExist:
            return None

    def get_horasAgenda(self, obj):
        taller = self._obtener_taller(obj)
        return float(taller.horas_agenda) if taller else 0.0

    def get_horasTotales(self, obj):
        return self.get_horasAgenda(obj)

    def get_isManual(self, obj):
        return obj.cliente_id is None

    def to_representation(self, instance):
        data = super().to_representation(instance)

        cliente = instance.cliente
        nombre = str(
            getattr(cliente, "nombre", "")
            or instance.nombre_cliente
            or ""
        ).strip()
        telefono = str(getattr(cliente, "telefono", "") or "").strip()
        correo = obtener_correo_cliente(cliente)

        # El frontend utiliza `cliente` como texto, no como PK.
        data["cliente"] = nombre
        data["cliente_id"] = cliente.pk if cliente else None
        data["cliente_nombre"] = nombre
        data["nombre_cliente"] = nombre or instance.nombre_cliente
        data["telefono"] = telefono
        data["correo"] = correo
        data["cliente_telefono"] = telefono
        data["cliente_correo_electronico"] = correo

        taller = self._obtener_taller(instance)

        if taller:
            tipo_servicio = (
                taller.tipo_servicio
                or instance.tipo_cita
                or instance.pauta
                or ""
            )
            data.update(
                {
                    "tecnico": taller.tecnico,
                    "etapa": taller.etapa,
                    "estatus_agenda": taller.estatus_agenda,
                    "fecha_programada": (
                        taller.fecha_programada.isoformat()
                        if taller.fecha_programada
                        else None
                    ),
                    "hora_inicio": (
                        taller.hora_inicio.strftime("%H:%M")
                        if taller.hora_inicio
                        else None
                    ),
                    "hora_fin": (
                        taller.hora_fin.strftime("%H:%M")
                        if taller.hora_fin
                        else None
                    ),
                    "tipo_bloque": taller.tipo_bloque,
                    "tipo_servicio": tipo_servicio,
                    "comentarios_taller": taller.comentarios_taller,
                }
            )
        else:
            tipo_servicio = instance.tipo_cita or instance.pauta or ""
            data.update(
                {
                    "tecnico": "",
                    "etapa": "Ingreso con Cita",
                    "estatus_agenda": "Programado",
                    "fecha_programada": None,
                    "hora_inicio": None,
                    "hora_fin": None,
                    "tipo_bloque": "trabajo",
                    "tipo_servicio": tipo_servicio,
                    "comentarios_taller": "",
                }
            )

        data["subtrabajos"] = [
            {
                "id": f"{instance.pk}-{indice}",
                "nombre": nombre_servicio,
                "horas": 0,
                "orden": indice,
            }
            for indice, nombre_servicio in enumerate(
                dividir_servicios(data.get("tipo_servicio"))
            )
        ]

        return data

    def validate(self, attrs):
        request = self.context.get("request")
        metodo = getattr(request, "method", "").upper()
        taller_actual = self._obtener_taller(self.instance)

        tipo_bloque = str(
            attrs.get(
                "tipo_bloque",
                getattr(taller_actual, "tipo_bloque", "trabajo"),
            )
            or "trabajo"
        ).strip().lower()

        cliente_id = attrs.get("cliente_id")
        cliente_texto = str(attrs.get("cliente", "") or "").strip()
        cliente_nombre = str(
            attrs.get("cliente_nombre", "")
            or cliente_texto
            or attrs.get("nombre_cliente", "")
            or ""
        ).strip()
        telefono = str(
            attrs.get("telefono", "")
            or attrs.get("cliente_telefono", "")
            or ""
        ).strip()

        if cliente_texto.isdigit() and not cliente_id:
            cliente_id = int(cliente_texto)
            attrs["cliente_id"] = cliente_id

        if cliente_id and not ClienteComercial.objects.filter(pk=cliente_id).exists():
            raise serializers.ValidationError(
                {"cliente_id": "El cliente indicado no existe."}
            )

        es_bloque_sin_cliente = tipo_bloque in TIPOS_BLOQUE_SIN_CLIENTE

        if metodo == "POST" and not es_bloque_sin_cliente and not cliente_id:
            if not cliente_nombre:
                raise serializers.ValidationError(
                    {"cliente": "Escribe el nombre del cliente."}
                )
            if not telefono:
                raise serializers.ValidationError(
                    {"telefono": "Escribe el teléfono del cliente."}
                )

        hora_inicio = attrs.get(
            "hora_inicio",
            getattr(taller_actual, "hora_inicio", None),
        )
        hora_fin = attrs.get(
            "hora_fin",
            getattr(taller_actual, "hora_fin", None),
        )

        if hora_inicio and not (HORA_INICIO_AGENDA <= hora_inicio < HORA_FIN_AGENDA):
            raise serializers.ValidationError(
                {"hora_inicio": "La hora inicial debe estar entre 07:00 y 19:45."}
            )

        if hora_fin and not (HORA_INICIO_AGENDA < hora_fin <= HORA_FIN_AGENDA):
            raise serializers.ValidationError(
                {"hora_fin": "La hora final debe estar entre 07:15 y 20:00."}
            )

        if hora_inicio and hora_fin and hora_fin <= hora_inicio:
            raise serializers.ValidationError(
                {"hora_fin": "La hora final debe ser posterior a la hora inicial."}
            )

        etapa = str(
            attrs.get("etapa", getattr(taller_actual, "etapa", "")) or ""
        ).strip()
        if etapa in ETAPAS_TERMINADAS:
            attrs["estatus_agenda"] = "Terminado"

        return attrs

    def _extraer_datos_taller(self, validated_data):
        datos_taller = {}

        for campo in CAMPOS_TALLER:
            if campo in validated_data:
                datos_taller[campo] = validated_data.pop(campo)

        subtrabajos = validated_data.pop("subtrabajos", None)
        if subtrabajos is not None and "tipo_servicio" not in datos_taller:
            nombres = [
                str(item.get("nombre") or "").strip()
                for item in subtrabajos
                if str(item.get("nombre") or "").strip()
            ]
            datos_taller["tipo_servicio"] = " + ".join(nombres)

        return datos_taller

    def _extraer_datos_cliente(
        self,
        validated_data,
    ):
        cliente_id = validated_data.pop(
            "cliente_id",
            None,
        )

        cliente_valor = str(
            validated_data.pop(
                "cliente",
                "",
            )
            or ""
        ).strip()

        # Nunca convertir el nombre a ID.
        if (
            cliente_valor.isdigit()
            and cliente_id is None
        ):
            cliente_id = int(cliente_valor)
            cliente_valor = ""

        nombre = str(
            validated_data.pop(
                "cliente_nombre",
                "",
            )
            or cliente_valor
            or validated_data.get(
                "nombre_cliente",
                "",
            )
            or ""
        ).strip()

        telefono = normaliza_tel_mx(
            validated_data.pop(
                "telefono",
                "",
            )
            or validated_data.pop(
                "cliente_telefono",
                "",
            )
        )

        correo = str(
            validated_data.pop(
                "correo",
                "",
            )
            or validated_data.pop(
                "cliente_correo_electronico",
                "",
            )
            or ""
        ).strip().lower()

        return {
            "cliente_id": cliente_id,
            "nombre": nombre,
            "telefono": telefono,
            "correo": correo,
        }

    def _resolver_cliente(
        self,
        datos_cliente,
        *,
        instance=None,
        tipo_bloque="trabajo",
    ):
        cliente_id = datos_cliente.get("cliente_id")
        nombre = str(
            datos_cliente.get("nombre") or ""
        ).strip()
        telefono = normaliza_tel_mx(
            datos_cliente.get("telefono") or ""
        )
        correo = str(
            datos_cliente.get("correo") or ""
        ).strip().lower()

        if tipo_bloque in TIPOS_BLOQUE_SIN_CLIENTE:
            return None

        cliente = None

        # 1. En edición, conservar primero el cliente asociado.
        if instance is not None and instance.cliente_id:
            cliente = instance.cliente

        # 2. Si el frontend envió un ID válido, usar ese cliente.
        if cliente_id:
            try:
                cliente = ClienteComercial.objects.get(
                    pk=cliente_id,
                )
            except (
                ClienteComercial.DoesNotExist,
                ValueError,
                TypeError,
            ):
                raise serializers.ValidationError({
                    "cliente_id": (
                        "El cliente indicado no existe."
                    ),
                })

        # 3. Para un registro nuevo, reutilizar el cliente por teléfono.
        # ClienteComercial.telefono tiene unique=True.
        if cliente is None and telefono:
            cliente = (
                ClienteComercial.objects
                .filter(telefono=telefono)
                .first()
            )

        # 4. Crear solamente si no existe un cliente con ese teléfono.
        if cliente is None:
            if not telefono:
                raise serializers.ValidationError({
                    "cliente_telefono": (
                        "El teléfono del cliente es obligatorio."
                    ),
                })

            cliente = ClienteComercial(
                nombre=nombre,
                telefono=telefono,
                correo=correo,
            )

        campos_actualizados = []

        if nombre and cliente.nombre != nombre:
            cliente.nombre = nombre
            campos_actualizados.append("nombre")

        if telefono and cliente.telefono != telefono:
            # Solo debería cambiarse cuando no pertenece a otro cliente.
            existe_otro = (
                ClienteComercial.objects
                .filter(telefono=telefono)
                .exclude(pk=cliente.pk)
                .exists()
            )

            if existe_otro:
                raise serializers.ValidationError({
                    "cliente_telefono": (
                        "Ese teléfono ya pertenece a otro cliente."
                    ),
                })

            cliente.telefono = telefono
            campos_actualizados.append("telefono")

        if correo and cliente.correo != correo:
            cliente.correo = correo
            campos_actualizados.append("correo")

        if cliente.pk:
            if campos_actualizados:
                cliente.save(
                    update_fields=list(
                        dict.fromkeys(
                            campos_actualizados +
                            ["actualizado_en"]
                        )
                    )
                )
        else:
            cliente.save()

        return cliente

    def _guardar_taller(self, ingreso, datos_taller):
        if not datos_taller:
            return

        valores_iniciales = {
            "tecnico": "",
            "etapa": "Ingreso con Cita",
            "estatus_agenda": "Programado",
            "fecha_programada": None,
            "hora_inicio": None,
            "hora_fin": None,
            "tipo_bloque": "trabajo",
            "tipo_servicio": ingreso.tipo_cita or ingreso.pauta or "",
            "comentarios_taller": "",
        }

        actividad, creada = TallerActividad.objects.get_or_create(
            ingreso=ingreso,
            defaults={**valores_iniciales, **datos_taller},
        )

        if creada:
            return

        for campo, valor in datos_taller.items():
            setattr(actividad, campo, valor)

        actividad.save()

    @transaction.atomic
    def create(self, validated_data):
        datos_taller = self._extraer_datos_taller(
            validated_data,
        )

        datos_cliente = self._extraer_datos_cliente(
            validated_data,
        )

        tipo_bloque = str(
            datos_taller.get(
                "tipo_bloque",
                "trabajo",
            )
            or "trabajo"
        ).strip().lower()

        cliente = self._resolver_cliente(
            datos_cliente,
            tipo_bloque=tipo_bloque,
        )

        if cliente is not None:
            validated_data["nombre_cliente"] = (
                cliente.nombre or ""
            )

        ingreso = HojaIngresos.objects.create(
            cliente=cliente,
            **validated_data,
        )

        self._guardar_taller(
            ingreso,
            datos_taller,
        )

        return (
            HojaIngresos.objects
            .select_related("cliente", "taller")
            .get(pk=ingreso.pk)
        )

    @transaction.atomic
    def update(
        self,
        instance,
        validated_data,
    ):
        datos_taller = self._extraer_datos_taller(
            validated_data,
        )

        datos_cliente = self._extraer_datos_cliente(
            validated_data,
        )

        taller_actual = self._obtener_taller(
            instance,
        )

        tipo_bloque = str(
            datos_taller.get(
                "tipo_bloque",
                getattr(
                    taller_actual,
                    "tipo_bloque",
                    "trabajo",
                ),
            )
            or "trabajo"
        ).strip().lower()

        hay_datos_cliente = any(
            valor not in (None, "")
            for valor in datos_cliente.values()
        )

        if hay_datos_cliente:
            cliente = self._resolver_cliente(
                datos_cliente,
                instance=instance,
                tipo_bloque=tipo_bloque,
            )

            instance.cliente = cliente

            if cliente is not None:
                validated_data["nombre_cliente"] = (
                    cliente.nombre or ""
                )

        for campo, valor in validated_data.items():
            setattr(
                instance,
                campo,
                valor,
            )

        instance.save()

        self._guardar_taller(
            instance,
            datos_taller,
        )

        return (
            HojaIngresos.objects
            .select_related("cliente", "taller")
            .get(pk=instance.pk)
        )