from rest_framework import serializers

from .models import (
    VacanteReclutamiento,
    CandidatoReclutamiento,
    Puesto,
    EvaluacionPuesto,
)

class CandidatoReclutamientoSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="id_candidato", read_only=True)

    class Meta:
        model = CandidatoReclutamiento
        fields = [
            "id",
            "id_candidato",
            "nombre",
            "sexo",
            "telefono",
            "correo",
            "ubicacion",
            "puesto_postulado",
            "fuente",
            "estatus",
            "cv",          # ✅ NUEVO
            "fecha_entrevista_do",
            "fecha_entrevista_gerente",
            "fecha_respuesta_gerente",
            "fecha_alta_khor",
            "fecha_realizacion_khor",
            "fecha_entrega_resultados_khor",
            "tipo_validacion_socioeconomica",
            "fecha_solicitud_estudio_socioeconomico",
            "fecha_entrega_reporte_socioeconomico",
            "fecha_solicitud_referencias_laborales",
            "fecha_entrega_referencias_laborales",
            "fecha_solicitud_alta",
            "fecha_respuesta_alta",
            "fecha_ingreso",
            "comentarios",
            "creado_at",
            "actualizado_at",
        ]
        read_only_fields = ["id", "id_candidato", "creado_at", "actualizado_at"]

    def validate(self, data):
        campos_obligatorios = {
            "nombre": "El nombre del candidato es obligatorio.",
            "sexo": "El sexo del candidato es obligatorio.",
            "telefono": "El teléfono del candidato es obligatorio.",
            "correo": "El correo del candidato es obligatorio.",
            "ubicacion": "La ubicación del candidato es obligatoria.",
            "puesto_postulado": "El puesto postulado es obligatorio.",
            "fuente": "La fuente del candidato es obligatoria.",
        }

        for campo, mensaje in campos_obligatorios.items():
            valor = data.get(campo)
            if valor is not None and not str(valor).strip():
                raise serializers.ValidationError({campo: mensaje})

        tipo_validacion = data.get("tipo_validacion_socioeconomica")

        if tipo_validacion != "Estudio socioeconómico":
            data["fecha_solicitud_estudio_socioeconomico"] = None
            data["fecha_entrega_reporte_socioeconomico"] = None

        if tipo_validacion != "Referencias laborales":
            data["fecha_solicitud_referencias_laborales"] = None
            data["fecha_entrega_referencias_laborales"] = None

        if data.get("fecha_ingreso"):
            data["estatus"] = "Contratado"

        return data


class VacanteReclutamientoSerializer(serializers.ModelSerializer):
    candidatos = CandidatoReclutamientoSerializer(
        many=True,
        required=False,
    )

    class Meta:
        model = VacanteReclutamiento
        fields = [
            "id_vacante",
            "estatus",
            "puesto",
            "dealer",
            "fuente_reclutamiento",
            "solicitado_por",
            "fecha_publicacion",
            "fecha_cierre",
            "creado_at",
            "actualizado_at",
            "candidatos",
        ]
        read_only_fields = [
            "id_vacante",
            "fecha_publicacion",
            "fecha_cierre",
            "creado_at",
            "actualizado_at",
        ]

    def validate(self, data):
        campos_obligatorios = {
            "puesto": "El puesto es obligatorio.",
            "dealer": "El dealer es obligatorio.",
            "fuente_reclutamiento": "La fuente de reclutamiento es obligatoria.",
            "solicitado_por": "El campo solicitado por es obligatorio.",
        }

        for campo, mensaje in campos_obligatorios.items():
            valor = data.get(campo)
            if valor is not None and not str(valor).strip():
                raise serializers.ValidationError({campo: mensaje})

        return data

    def create(self, validated_data):
        candidatos_data = validated_data.pop("candidatos", [])
        archivos = self.context.get("archivos", {})  # ✅ NUEVO

        vacante = VacanteReclutamiento.objects.create(**validated_data)

        for index, candidato_data in enumerate(candidatos_data):
            archivo_cv = archivos.get(f"cv_archivo_{index}")  # ✅ NUEVO
            if archivo_cv:
                candidato_data["cv"] = archivo_cv              # ✅ NUEVO
            CandidatoReclutamiento.objects.create(
                vacante=vacante,
                **candidato_data,
            )

        return vacante

    def update(self, instance, validated_data):
        candidatos_data = validated_data.pop("candidatos", None)

        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)

        instance.save()

        if candidatos_data is not None:
            self._sincronizar_candidatos(instance, candidatos_data)

        return instance

    def _sincronizar_candidatos(self, vacante, candidatos_data):
        raw_candidatos = self.initial_data.get("candidatos", [])

        archivos = self.context.get("archivos", {})

        candidatos_existentes = {
            candidato.id_candidato: candidato
            for candidato in vacante.candidatos.all()
        }

        ids_recibidos = []

        for index, candidato_data in enumerate(candidatos_data):
            raw = raw_candidatos[index] if index < len(raw_candidatos) else {}

            id_candidato = raw.get("id_candidato") or raw.get("id")
            if id_candidato:
                try:
                    id_candidato = int(id_candidato)
                except (TypeError, ValueError):
                    id_candidato = None

            archivo_cv = archivos.get(f"cv_archivo_{index}")

            if id_candidato and id_candidato in candidatos_existentes:
                candidato = candidatos_existentes[id_candidato]

                for campo, valor in candidato_data.items():
                    setattr(candidato, campo, valor)

                if archivo_cv:
                    candidato.cv = archivo_cv

                candidato.save()
                ids_recibidos.append(candidato.id_candidato)

            else:
                if archivo_cv:
                    candidato_data["cv"] = archivo_cv

                candidato = CandidatoReclutamiento.objects.create(
                    vacante=vacante,
                    **candidato_data,
                )

                ids_recibidos.append(candidato.id_candidato)

        vacante.candidatos.exclude(
            id_candidato__in=ids_recibidos
        ).delete()

class PuestoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Puesto
        fields = '__all__'


class EvaluacionPuestoSerializer(serializers.ModelSerializer):
    puesto_nombre = serializers.CharField(source='puesto.nombre', read_only=True)

    class Meta:
        model = EvaluacionPuesto
        fields = '__all__'
        read_only_fields = ['fecha', 'creado_at']