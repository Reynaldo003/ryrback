#usados/serializers.py
import json
import mimetypes
from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework import serializers

from citas.models import ClienteComercial, normaliza_tel_mx
from .models import AvaluoUsado, AvaluoUsadoEvidencia, ConceptoAvaluo


class ClienteComercialMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClienteComercial
        fields = ("id_cliente", "nombre", "telefono", "correo")


class AvaluoUsadoEvidenciaSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = AvaluoUsadoEvidencia
        fields = ("id", "nombre", "tipo", "archivo", "url", "creado")
        read_only_fields = ("id", "nombre", "tipo", "archivo", "url", "creado")

    def get_url(self, obj):
        if not obj.archivo:
            return ""

        try:
            url = obj.archivo.url
        except Exception:
            return ""

        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url


class ConceptoAvaluoSerializer(serializers.ModelSerializer):
    costo = serializers.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        model = ConceptoAvaluo
        fields = ("id", "descripcion", "costo")
        read_only_fields = ("id",)


class BaseClienteComercialSerializer(serializers.ModelSerializer):
    cliente = ClienteComercialMiniSerializer(read_only=True)

    cliente_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    nombre = serializers.CharField(write_only=True, required=False, allow_blank=True, default="")
    telefono = serializers.CharField(write_only=True, required=False, allow_blank=True, default="")
    correo = serializers.EmailField(write_only=True, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        attrs = super().validate(attrs)

        telefono = attrs.get("telefono")
        cliente_id = attrs.get("cliente_id")

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

            if nombre is not None and str(nombre).strip() != (cliente.nombre or ""):
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

        cliente, _ = ClienteComercial.objects.get_or_create(
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


class AvaluoUsadoSerializer(BaseClienteComercialSerializer):
    evidencias = AvaluoUsadoEvidenciaSerializer(many=True, read_only=True)
    conceptos = ConceptoAvaluoSerializer(many=True, read_only=True)

    conceptos_json = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        default="",
    )

    delete_evidencia_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        allow_empty=True,
    )

    class Meta:
        model = AvaluoUsado
        fields = (
            "id",
            "cliente",
            "cliente_id",
            "nombre",
            "telefono",
            "correo",
            "agencia",
            "fecha_avaluo",
            "asesor_ventas",
            "marca_auto",
            "modelo",
            "anio_modelo",
            "serie",
            "kilometraje",
            "precio_guia",
            "costo_reparacion",
            "costo_estimado",
            "oferta_economica",
            "color",
            "descripcion",
            "ganador_subasta",
            "etapa_proceso",
            "tipo_toma",
            "comentarios",
            "evidencias",
            "conceptos",
            "conceptos_json",
            "delete_evidencia_ids",
            "creado",
        )

        read_only_fields = (
            "id",
            "cliente",
            "evidencias",
            "conceptos",
            "creado",
        )

    def _parse_decimal(self, valor):
        texto = str(valor or "").strip()

        if not texto:
            return Decimal("0.00")

        texto = (
            texto.replace("$", "")
            .replace(",", "")
            .replace(" ", "")
        )

        try:
            return Decimal(texto).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            raise serializers.ValidationError({
                "conceptos_json": f"Costo inválido en conceptos: '{valor}'."
            })

    def _normalizar_conceptos(self, raw_conceptos):
        if raw_conceptos in (None, "", []):
            return []

        if isinstance(raw_conceptos, str):
            try:
                raw_conceptos = json.loads(raw_conceptos)
            except json.JSONDecodeError:
                raise serializers.ValidationError({
                    "conceptos_json": "El formato de conceptos no es válido."
                })

        if not isinstance(raw_conceptos, list):
            raise serializers.ValidationError({
                "conceptos_json": "Los conceptos deben enviarse como una lista."
            })

        conceptos = []

        for item in raw_conceptos:
            if not isinstance(item, dict):
                raise serializers.ValidationError({
                    "conceptos_json": "Cada concepto debe ser un objeto."
                })

            descripcion = str(item.get("descripcion") or "").strip()
            costo = self._parse_decimal(item.get("costo"))

            if not descripcion and costo == Decimal("0.00"):
                continue

            if not descripcion:
                raise serializers.ValidationError({
                    "conceptos_json": "Cada concepto debe tener descripción."
                })

            conceptos.append({
                "descripcion": descripcion,
                "costo": costo,
            })

        return conceptos

    def _obtener_conceptos_desde_request(self, attrs):
        """
        Devuelve:
        - conceptos_recibidos: True si el frontend mandó conceptos_json.
        - conceptos: lista normalizada.

        Esto evita borrar conceptos por accidente cuando algún PATCH no mande
        conceptos_json.
        """

        request = self.context.get("request")
        raw_conceptos = attrs.get("conceptos_json", None)
        conceptos_recibidos = raw_conceptos is not None

        if request is not None and hasattr(request.data, "get"):
            if "conceptos_json" in request.data:
                raw_conceptos = request.data.get("conceptos_json")
                conceptos_recibidos = True

        if not conceptos_recibidos:
            return False, []

        return True, self._normalizar_conceptos(raw_conceptos)

    def validate(self, attrs):
        attrs = super().validate(attrs)

        request = self.context.get("request")
        archivos = []
        delete_ids = attrs.get("delete_evidencia_ids", [])

        if request is not None:
            if hasattr(request.FILES, "getlist"):
                archivos = request.FILES.getlist("evidencias_nuevas")

            if hasattr(request.data, "getlist"):
                raw_delete_ids = request.data.getlist("delete_evidencia_ids")
                if raw_delete_ids:
                    delete_ids = raw_delete_ids

        delete_ids_limpios = []

        for valor in delete_ids or []:
            valor = str(valor).strip()

            if not valor:
                continue

            try:
                delete_ids_limpios.append(int(valor))
            except ValueError:
                raise serializers.ValidationError({
                    "delete_evidencia_ids": "Todos los IDs de evidencias a eliminar deben ser números enteros."
                })

        for archivo in archivos:
            if archivo.size > 50 * 1024 * 1024:
                raise serializers.ValidationError({
                    "evidencias_nuevas": f"El archivo '{archivo.name}' supera el límite de 50 MB."
                })

        conceptos_recibidos, conceptos = self._obtener_conceptos_desde_request(attrs)

        if conceptos_recibidos:
            total_reparacion = sum(
                (item["costo"] for item in conceptos),
                Decimal("0.00"),
            )

            attrs["costo_reparacion"] = f"{total_reparacion:.2f}"
            attrs["_conceptos"] = conceptos
            attrs["_conceptos_recibidos"] = True
        else:
            attrs["_conceptos"] = []
            attrs["_conceptos_recibidos"] = False

        attrs["_evidencias_nuevas"] = archivos
        attrs["_delete_evidencia_ids"] = delete_ids_limpios

        return attrs

    def _inferir_tipo_archivo(self, archivo):
        content_type = getattr(archivo, "content_type", "") or ""

        if not content_type:
            content_type = mimetypes.guess_type(
                getattr(archivo, "name", "")
            )[0] or ""

        if content_type.startswith("image/"):
            return AvaluoUsadoEvidencia.TIPO_IMAGEN

        if content_type.startswith("video/"):
            return AvaluoUsadoEvidencia.TIPO_VIDEO

        return AvaluoUsadoEvidencia.TIPO_ARCHIVO

    def _crear_evidencias(self, avaluo, archivos):
        for archivo in archivos:
            AvaluoUsadoEvidencia.objects.create(
                avaluo=avaluo,
                archivo=archivo,
                nombre=getattr(archivo, "name", "") or "archivo",
                tipo=self._inferir_tipo_archivo(archivo),
            )

    def _guardar_conceptos(self, avaluo, conceptos):
        avaluo.conceptos.all().delete()

        for item in conceptos:
            ConceptoAvaluo.objects.create(
                avaluo=avaluo,
                descripcion=item["descripcion"],
                costo=item["costo"],
            )

    @transaction.atomic
    def create(self, validated_data):
        evidencias_nuevas = validated_data.pop("_evidencias_nuevas", [])
        conceptos = validated_data.pop("_conceptos", [])
        validated_data.pop("_conceptos_recibidos", None)
        validated_data.pop("_delete_evidencia_ids", None)
        validated_data.pop("delete_evidencia_ids", None)
        validated_data.pop("conceptos_json", None)

        cliente = self._resolver_cliente(validated_data)
        avaluo = AvaluoUsado.objects.create(cliente=cliente, **validated_data)

        self._crear_evidencias(avaluo, evidencias_nuevas)
        self._guardar_conceptos(avaluo, conceptos)

        return avaluo

    @transaction.atomic
    def update(self, instance, validated_data):
        evidencias_nuevas = validated_data.pop("_evidencias_nuevas", [])
        delete_ids = validated_data.pop("_delete_evidencia_ids", [])
        conceptos = validated_data.pop("_conceptos", [])
        conceptos_recibidos = validated_data.pop("_conceptos_recibidos", False)

        validated_data.pop("delete_evidencia_ids", None)
        validated_data.pop("conceptos_json", None)

        usar_cliente = (
            "cliente_id" in validated_data
            or "nombre" in validated_data
            or "telefono" in validated_data
            or "correo" in validated_data
        )

        if usar_cliente:
            cliente = self._resolver_cliente(validated_data)
            instance.cliente = cliente

        campos = [
            "agencia",
            "fecha_avaluo",
            "asesor_ventas",
            "marca_auto",
            "modelo",
            "anio_modelo",
            "serie",
            "kilometraje",
            "precio_guia",
            "costo_reparacion",
            "costo_estimado",
            "oferta_economica",
            "color",
            "descripcion",
            "ganador_subasta",
            "etapa_proceso",
            "tipo_toma",
            "comentarios",
        ]

        for campo in campos:
            if campo in validated_data:
                setattr(instance, campo, validated_data[campo])

        instance.save()

        if delete_ids:
            instance.evidencias.filter(id__in=delete_ids).delete()

        if evidencias_nuevas:
            self._crear_evidencias(instance, evidencias_nuevas)

        if conceptos_recibidos:
            self._guardar_conceptos(instance, conceptos)

        return instance