#Safety/serializers.py
from rest_framework import serializers
from .models import ReporteSafety, AdjuntoReporteSafety


class AdjuntoReporteSafetySerializer(serializers.ModelSerializer):
    url_archivo = serializers.SerializerMethodField()

    class Meta:
        model = AdjuntoReporteSafety
        fields = [
            "id_adjunto",
            "punto_checklist_id",
            "tipo_adjunto",
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
        if not obj.archivo:
            return ""

        if request:
            return request.build_absolute_uri(obj.archivo.url)

        return obj.archivo.url


class ReporteSafetySerializer(serializers.ModelSerializer):
    adjuntos = AdjuntoReporteSafetySerializer(many=True, read_only=True)

    class Meta:
        model = ReporteSafety
        fields = [
            "id_reporte",
            "creado",
            "fecha_reporte",
            "reportante",
            "agencia",
            "nombre_cliente",
            "orden_servicio",
            "tecnico_reparo",
            "valido_control_calidad",
            "checklist",
            "comentarios_finales",
            "adjuntos",
        ]
        read_only_fields = ["id_reporte", "creado", "adjuntos"]

    def validate_checklist(self, value):
        if not isinstance(value, list) or len(value) == 0:
            raise serializers.ValidationError(
                "Debes enviar al menos un punto del checklist."
            )

        checklist_limpio = []

        for indice, item in enumerate(value, start=1):
            if not isinstance(item, dict):
                raise serializers.ValidationError(
                    f"El punto {indice} del checklist no tiene un formato válido."
                )

            id_item = str(item.get("id", "")).strip()
            titulo = str(item.get("titulo", "")).strip()
            descripcion = str(item.get("descripcion", "")).strip()
            estado = str(item.get("estado", "")).strip().lower()
            observaciones = str(item.get("observaciones", "")).strip()

            permite_no_aplica = item.get("permite_no_aplica", item.get("permiteNoAplica", False))
            permite_no_aplica = bool(permite_no_aplica)

            if not id_item:
                raise serializers.ValidationError(
                    f"El punto {indice} no tiene id."
                )

            if not titulo:
                raise serializers.ValidationError(
                    f"El punto {indice} no tiene título."
                )

            if estado not in ["si", "no", "na"]:
                raise serializers.ValidationError(
                    f"El punto '{titulo}' debe tener estado 'si', 'no' o 'na'."
                )

            if estado == "na" and not permite_no_aplica:
                raise serializers.ValidationError(
                    f"El punto '{titulo}' no permite 'No aplica'."
                )

            if estado == "no" and not observaciones:
                raise serializers.ValidationError(
                    f"El punto '{titulo}' requiere observaciones cuando el estado es 'No'."
                )

            checklist_limpio.append({
                "id": id_item,
                "titulo": titulo,
                "descripcion": descripcion,
                "permite_no_aplica": permite_no_aplica,
                "estado": estado,
                "observaciones": observaciones,
            })

        return checklist_limpio

    def validate(self, attrs):
        campos_texto = [
            "reportante",
            "agencia",
            "nombre_cliente",
            "orden_servicio",
            "tecnico_reparo",
            "valido_control_calidad",
            "comentarios_finales",
        ]

        for campo in campos_texto:
            valor = attrs.get(campo, "")
            if isinstance(valor, str):
                attrs[campo] = valor.strip()

        requeridos = [
            "reportante",
            "agencia",
            "nombre_cliente",
            "orden_servicio",
            "tecnico_reparo",
            "valido_control_calidad",
        ]

        for campo in requeridos:
            if not attrs.get(campo):
                raise serializers.ValidationError({
                    campo: "Este campo es obligatorio."
                })

        return attrs