#gestion_inversion/serializers.py
from django.conf import settings

from rest_framework import serializers

from .models import FacturaMarketing, ConceptoFactura, SITIOS_POR_CLASIFICACION, DEALERS, DEPARTAMENTOS

class FacturaUploadSerializer(serializers.Serializer):
    archivo = serializers.FileField()
    dealer = serializers.ChoiceField(choices=DEALERS)
    departamento = serializers.ChoiceField(choices=DEPARTAMENTOS)

    def validate_archivo(self, archivo):
        nombre = str(getattr(archivo, "name", "") or "").lower()
        mime = str(getattr(archivo, "content_type", "") or "").lower()

        if not nombre.endswith(".pdf"):
            raise serializers.ValidationError("Solo se permiten archivos con extensión .pdf.")

        if mime and mime != "application/pdf":
            raise serializers.ValidationError("Solo se permiten archivos PDF.")

        posicion = archivo.tell() if hasattr(archivo, "tell") else 0
        cabecera = archivo.read(5)

        if hasattr(archivo, "seek"):
            archivo.seek(posicion)

        if cabecera != b"%PDF-":
            raise serializers.ValidationError("El archivo seleccionado no es un PDF válido.")

        max_bytes = int(getattr(settings, "OPENAI_MAX_PDF_BYTES", 18 * 1024 * 1024))

        if archivo.size > max_bytes:
            limite_mb = round(max_bytes / 1024 / 1024, 2)
            raise serializers.ValidationError(f"El PDF supera el límite de {limite_mb} MB para análisis.")

        return archivo

class ConceptoFacturaSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(
        source="id_concepto",
        read_only=True,
    )

    cantidad = serializers.FloatField(
        read_only=True,
    )

    precioUnitario = serializers.FloatField(
        source="precio_unitario",
        read_only=True,
    )

    importe = serializers.FloatField(
        read_only=True,
    )

    class Meta:
        model = ConceptoFactura

        fields = [
            "id",
            "clave",
            "descripcion",
            "cantidad",
            "unidad",
            "precioUnitario",
            "importe",
            "clasificacion",
            "sitio",
            "motivo",
        ]

        read_only_fields = [
            "id",
            "clave",
            "descripcion",
            "cantidad",
            "unidad",
            "precioUnitario",
            "importe",
        ]

    def validate(self, attrs):
        instancia = self.instance

        clasificacion = attrs.get(
            "clasificacion",
            getattr(
                instancia,
                "clasificacion",
                "",
            ),
        )

        sitio = attrs.get(
            "sitio",
            getattr(
                instancia,
                "sitio",
                "",
            ),
        )

        # Si se está cambiando la clasificación sin mandar sitio,
        # la validación del sitio anterior se realiza posteriormente
        # dentro de update(), donde puede limpiarse automáticamente.
        if (
            "clasificacion" in attrs
            and "sitio" not in attrs
        ):
            sitio = ""

        if sitio and not clasificacion:
            raise serializers.ValidationError({
                "sitio":
                    "Selecciona primero una clasificación."
            })

        if sitio:
            opciones = SITIOS_POR_CLASIFICACION.get(
                clasificacion,
                [],
            )

            if sitio not in opciones:
                raise serializers.ValidationError({
                    "sitio":
                        "El sitio/rubro no pertenece a la clasificación seleccionada."
                })

        return attrs

    def update(self, instance, validated_data):
        if (
            "clasificacion" in validated_data
            and "sitio" not in validated_data
        ):
            nueva_clasificacion = (
                validated_data.get(
                    "clasificacion",
                    "",
                )
            )

            sitios_validos = (
                SITIOS_POR_CLASIFICACION.get(
                    nueva_clasificacion,
                    [],
                )
            )

            if instance.sitio not in sitios_validos:
                validated_data["sitio"] = ""

        return super().update(
            instance,
            validated_data,
        )

class FacturaMarketingSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="id_factura", read_only=True)
    archivo = serializers.CharField(source="nombre_original", read_only=True)
    archivoUrl = serializers.SerializerMethodField()
    archivoSize = serializers.IntegerField(source="tamano_bytes", read_only=True)
    fechaCarga = serializers.DateTimeField(source="creado", read_only=True)
    creadoPor = serializers.CharField(source="creado_por", read_only=True)
    errorAnalisis = serializers.CharField(source="error_analisis", read_only=True)
    analizadoEn = serializers.DateTimeField(source="analizado", read_only=True)
    emisor = serializers.SerializerMethodField()
    receptor = serializers.SerializerMethodField()
    comprobante = serializers.SerializerMethodField()
    totales = serializers.SerializerMethodField()
    conceptos = ConceptoFacturaSerializer(many=True, read_only=True)

    class Meta:
        model = FacturaMarketing
        fields = [
            "id",
            "archivo",
            "archivoUrl",
            "archivoSize",
            "dealer",
            "departamento",
            "estado",
            "fechaCarga",
            "creadoPor",
            "errorAnalisis",
            "analizadoEn",
            "emisor",
            "receptor",
            "comprobante",
            "totales",
            "conceptos",
        ]
        read_only_fields = fields

    def get_archivoUrl(self, obj):
        if not obj.archivo:
            return ""

        request = self.context.get("request")
        return request.build_absolute_uri(obj.archivo.url) if request else obj.archivo.url

    def get_emisor(self, obj):
        return {
            "razonSocial": obj.emisor_razon_social,
            "rfc": obj.emisor_rfc,
            "regimenFiscal": obj.emisor_regimen_fiscal,
            "domicilio": obj.emisor_domicilio,
        }

    def get_receptor(self, obj):
        return {
            "razonSocial": obj.receptor_razon_social,
            "rfc": obj.receptor_rfc,
            "usoCfdi": obj.receptor_uso_cfdi,
        }

    def get_comprobante(self, obj):
        return {
            "uuid": obj.uuid_cfdi,
            "folio": obj.folio,
            "fecha": obj.fecha_factura.isoformat() if obj.fecha_factura else None,
            "moneda": obj.moneda or "MXN",
            "metodoPago": obj.metodo_pago,
            "formaPago": obj.forma_pago,
        }

    def get_totales(self, obj):
        return {
            "subtotal": float(obj.subtotal or 0),
            "impuestos": float(obj.impuestos or 0),
            "total": float(obj.total or 0),
        }