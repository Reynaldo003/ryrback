# documentacion/serializers.py
from rest_framework import serializers

from .models import Expediente, DocumentoExpediente
from .requisitos import obtener_requisitos


def obtener_nombre_usuario(usuario):
    if hasattr(usuario, "get_full_name"):
        nombre = usuario.get_full_name()
        if nombre: return nombre

    return (
        getattr(usuario, "nombre_completo", "")
        or getattr(usuario, "nombre", "")
        or getattr(usuario, "username", "")
        or getattr(usuario, "email", "")
        or str(usuario)
    )


class DocumentoExpedienteSerializer(serializers.ModelSerializer):
    url_archivo = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoExpediente
        fields = [
            "id_documento",
            "requisito_id",
            "requisito_nombre",
            "archivo",
            "url_archivo",
            "nombre_original",
            "tipo_mime",
            "tamano_bytes",
            "creado",
        ]
        read_only_fields = fields

    def get_url_archivo(self, obj):
        request = self.context.get("request")

        if not obj.archivo: return ""
        if request: return request.build_absolute_uri(obj.archivo.url)

        return obj.archivo.url


class DocumentoUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentoExpediente
        fields = ["requisito_id", "archivo"]

    def validate_archivo(self, archivo):
        nombre = str(getattr(archivo, "name", "") or "").lower()
        mime = str(getattr(archivo, "content_type", "") or "").lower()

        if not nombre.endswith(".pdf"): raise serializers.ValidationError("Solo se permiten archivos con extensión .pdf.")
        if mime and mime != "application/pdf": raise serializers.ValidationError("Solo se permiten archivos PDF.")

        posicion = archivo.tell() if hasattr(archivo, "tell") else 0
        cabecera = archivo.read(5)

        if hasattr(archivo, "seek"): archivo.seek(posicion)
        if cabecera != b"%PDF-": raise serializers.ValidationError("El archivo seleccionado no es un PDF válido.")

        return archivo


class ExpedienteSerializer(serializers.ModelSerializer):
    asesor_id = serializers.SerializerMethodField()
    asesor_nombre = serializers.SerializerMethodField()
    documentos = serializers.SerializerMethodField()
    requisitos = serializers.SerializerMethodField()
    avance = serializers.SerializerMethodField()

    class Meta:
        model = Expediente
        fields = [
            "id_expediente",
            "folio",
            "cliente",
            "agencia",
            "tipo_persona",
            "financiamiento",
            "asesor_id",
            "asesor_nombre",
            "documentos",
            "requisitos",
            "avance",
            "creado",
            "actualizado",
        ]
        read_only_fields = [
            "id_expediente",
            "folio",
            "asesor_id",
            "asesor_nombre",
            "documentos",
            "requisitos",
            "avance",
            "creado",
            "actualizado",
        ]

    def get_asesor_id(self, obj): return obj.asesor.pk

    def get_asesor_nombre(self, obj): return obtener_nombre_usuario(obj.asesor)

    def get_requisitos(self, obj): return obtener_requisitos(obj.tipo_persona, obj.financiamiento) or []

    def get_documentos(self, obj):
        serializer = DocumentoExpedienteSerializer(obj.documentos.all(), many=True, context=self.context)
        return {str(documento["requisito_id"]): documento for documento in serializer.data}

    def get_avance(self, obj):
        requisitos = obtener_requisitos(obj.tipo_persona, obj.financiamiento) or []
        obligatorios = [item for item in requisitos if item.get("obligatorio")]
        cargados = set(obj.documentos.values_list("requisito_id", flat=True))

        completados = sum(1 for item in obligatorios if item["id"] in cargados)
        total = len(obligatorios)

        return {
            "completados": completados,
            "total": total,
            "faltantes": max(total - completados, 0),
            "porcentaje": round((completados / total) * 100) if total else 0,
        }

    def validate(self, attrs):
        for campo in ["cliente", "agencia"]:
            valor = attrs.get(campo)
            if isinstance(valor, str): attrs[campo] = valor.strip()

        if not attrs.get("cliente"): raise serializers.ValidationError({"cliente": "Este campo es obligatorio."})
        if not attrs.get("agencia"): raise serializers.ValidationError({"agencia": "Este campo es obligatorio."})

        tipo_persona = attrs.get("tipo_persona")
        financiamiento = attrs.get("financiamiento")

        if obtener_requisitos(tipo_persona, financiamiento) is None:
            raise serializers.ValidationError({
                "financiamiento": "Esta combinación de persona y financiamiento todavía no tiene requisitos configurados."
            })

        return attrs