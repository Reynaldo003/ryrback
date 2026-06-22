#Encuestas/serializers.py
from rest_framework import serializers
from .models import EncuestaSatisfaccion, EncuestaServicio, EncuestaPiso


class EncuestaSatisfaccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EncuestaSatisfaccion
        fields = [
            "id_encuesta",
            "creado",
            "agencia",
            "nombre_cliente",
            "asesor_atendio",
            "motivo_visita",
            "atencion_asesor",
            "seguimiento_asesor",
            "tiempo_entrega_unidad",
            "experiencia_recepcion",
            "comentario",
        ]
        read_only_fields = ["id_encuesta", "creado"]

    def validate(self, attrs):
        campos_calificacion = [
            "atencion_asesor",
            "seguimiento_asesor",
            "tiempo_entrega_unidad",
            "experiencia_recepcion",
        ]

        for campo in campos_calificacion:
            valor = attrs.get(campo)

            if valor is None:
                raise serializers.ValidationError({
                    campo: "Este campo es obligatorio."
                })

            if int(valor) < 1 or int(valor) > 5:
                raise serializers.ValidationError({
                    campo: "Debe ser un valor entre 1 y 5."
                })

        attrs["agencia"] = (attrs.get("agencia") or "").strip()
        attrs["nombre_cliente"] = (attrs.get("nombre_cliente") or "").strip()
        attrs["asesor_atendio"] = (attrs.get("asesor_atendio") or "").strip()
        attrs["motivo_visita"] = (attrs.get("motivo_visita") or "").strip()
        attrs["comentario"] = (attrs.get("comentario") or "").strip()

        return attrs


class EncuestaServicioSerializer(serializers.ModelSerializer):
    class Meta:
        model = EncuestaServicio
        fields = [
            "id_encuesta",
            "creado",
            "agencia",
            "nombre_OS_cliente",
            "asesor_atendio",
            "satisfaccion_agenda_cita",
            "satisfaccion_atencion_asesor",
            "percepcion_calidad_precio",
            "satisfaccion_servicio_ryr",
            "comentario",
        ]
        read_only_fields = ["id_encuesta", "creado"]

    def validate(self, attrs):
        campos_calificacion = [
            "satisfaccion_atencion_asesor",
            "percepcion_calidad_precio",
            "satisfaccion_servicio_ryr",
        ]

        for campo in campos_calificacion:
            valor = attrs.get(campo)

            if valor is None:
                raise serializers.ValidationError({
                    campo: "Este campo es obligatorio."
                })

            if int(valor) < 1 or int(valor) > 5:
                raise serializers.ValidationError({
                    campo: "Debe ser un valor entre 1 y 5."
                })

        attrs["agencia"] = (attrs.get("agencia") or "").strip()
        attrs["nombre_OS_cliente"] = (attrs.get("nombre_OS_cliente") or "").strip()
        attrs["asesor_atendio"] = (attrs.get("asesor_atendio") or "").strip()
        attrs["satisfaccion_agenda_cita"] = (attrs.get("satisfaccion_agenda_cita") or "").strip()
        attrs["comentario"] = (attrs.get("comentario") or "").strip()

        if not attrs["nombre_OS_cliente"]:
            raise serializers.ValidationError({
                "nombre_OS_cliente": "Este campo es obligatorio."
            })

        if not attrs["asesor_atendio"]:
            raise serializers.ValidationError({
                "asesor_atendio": "Este campo es obligatorio."
            })

        if not attrs["satisfaccion_agenda_cita"]:
            raise serializers.ValidationError({
                "satisfaccion_agenda_cita": "Este campo es obligatorio."
            })

        return attrs

class EncuestaPisoSerializer(serializers.ModelSerializer):
    class Meta:
        model = EncuestaPiso
        fields = [
            "id_encuesta", "creado_en", "agencia", "nombre_cliente",
            "telefono", "asesor_atendio", "id_trafico", "flow_token",
            "atencion_llegada", "amenidades", "atencion_asesor",
            "financiamiento", "experiencia", "medio_contacto",
            "prueba_manejo", "recomendacion", "contacto_post",
            "tiempo_contacto", "comentarios",
        ]
        read_only_fields = ["id_encuesta", "creado"]

    def validate(self, attrs):
        campos_calificacion = [
            "atencion_asesor",
            "seguimiento_asesor",
            "tiempo_entrega_unidad",
            "experiencia_recepcion",
        ]
        for campo in campos_calificacion:
            valor = attrs.get(campo)
            if valor is None:
                raise serializers.ValidationError({campo: "Este campo es obligatorio."})
            if int(valor) < 1 or int(valor) > 5:
                raise serializers.ValidationError({campo: "Debe ser un valor entre 1 y 5."})

        attrs["agencia"]        = (attrs.get("agencia") or "").strip()
        attrs["nombre_cliente"] = (attrs.get("nombre_cliente") or "").strip()
        attrs["asesor_atendio"] = (attrs.get("asesor_atendio") or "").strip()
        attrs["motivo_visita"]  = (attrs.get("motivo_visita") or "").strip()
        attrs["comentario"]     = (attrs.get("comentario") or "").strip()
        attrs["telefono"]       = (attrs.get("telefono") or "").strip()
        attrs["flow_token"]     = (attrs.get("flow_token") or "").strip()
        return attrs