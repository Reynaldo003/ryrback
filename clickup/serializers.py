# clickup/serializers.py
from rest_framework import serializers
from django.conf import settings

from .models import (
    Equipo, MiembroEquipo, InvitacionEquipo, Proyecto, Lista,
    Tarea, TareaAsignada, NotificacionClickup, ReporteIncidencia, EvidenciaTarea,
)
from CrmConformidad.models import Usuario


class UsuarioMiniSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = ("id_usuario", "nombre", "apellidos", "correo", "usuario", "nombre_completo")

    def get_nombre_completo(self, obj):
        return f"{obj.nombre or ''} {obj.apellidos or ''}".strip()


class UsuarioSearchSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = ("id_usuario", "nombre", "apellidos", "correo", "usuario", "agencia", "nombre_completo")

    def get_nombre_completo(self, obj):
        return f"{obj.nombre or ''} {obj.apellidos or ''}".strip()


class EquipoSerializer(serializers.ModelSerializer):
    propietario = UsuarioMiniSerializer(read_only=True)

    class Meta:
        model = Equipo
        fields = ("id", "nombre", "descripcion", "propietario", "creado_en")
        read_only_fields = ("id", "propietario", "creado_en")


class MiembroEquipoSerializer(serializers.ModelSerializer):
    usuario = UsuarioMiniSerializer(read_only=True)

    class Meta:
        model = MiembroEquipo
        fields = ("id", "equipo", "usuario", "rol", "unido_en", "activo")
        read_only_fields = ("id", "unido_en")


class InvitacionEquipoSerializer(serializers.ModelSerializer):
    invitado_por = UsuarioMiniSerializer(read_only=True)
    aceptado_por = UsuarioMiniSerializer(read_only=True)
    usuario_invitado = UsuarioMiniSerializer(read_only=True)
    esta_expirada = serializers.SerializerMethodField()

    class Meta:
        model = InvitacionEquipo
        fields = (
            "id", "equipo", "correo", "usuario_invitado", "rol", "token",
            "estado", "invitado_por", "creado_en", "expira_en", "esta_expirada",
            "aceptado_en", "aceptado_por",
        )

    def get_esta_expirada(self, obj):
        return obj.esta_expirada()


class ProyectoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proyecto
        fields = ("id", "equipo", "nombre", "descripcion", "color", "creado_en")
        read_only_fields = ("id", "creado_en", "equipo")


class ListaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lista
        fields = ("id", "proyecto", "nombre", "orden")
        read_only_fields = ("id",)


class TareaAsignadaSerializer(serializers.ModelSerializer):
    usuario = UsuarioMiniSerializer(read_only=True)

    class Meta:
        model = TareaAsignada
        fields = ("id", "usuario")


class EvidenciaTareaSerializer(serializers.ModelSerializer):
    subido_por = UsuarioMiniSerializer(read_only=True)
    archivo_url = serializers.SerializerMethodField()
    proxy_url = serializers.SerializerMethodField()

    class Meta:
        model = EvidenciaTarea
        fields = ("id", "tipo", "comentario", "archivo", "archivo_url", "proxy_url", "subido_por", "creado_en")
        read_only_fields = ("id", "subido_por", "creado_en", "archivo_url", "proxy_url")

    def get_archivo_url(self, obj):
        request = self.context.get("request")
        if not obj.archivo:
            return None
        if request:
            return request.build_absolute_uri(obj.archivo.url)
        return obj.archivo.url

    def get_proxy_url(self, obj):
        request = self.context.get("request")
        if not obj.archivo or not request:
            return None
        return request.build_absolute_uri(f"/api/clickup/evidencias/{obj.id}/archivo/")


class ReporteIncidenciaMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReporteIncidencia
        fields = ("id", "tipo", "titulo", "descripcion", "estado", "creado_en", "actualizado_en", "resuelto_en")


class SubtareaListSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="titulo", read_only=True)
    done = serializers.BooleanField(source="completada", read_only=True)
    start_date = serializers.DateTimeField(source="inicio", read_only=True)
    due_date = serializers.DateTimeField(source="vence", read_only=True)

    class Meta:
        model = Tarea
        fields = ("id", "titulo", "title", "done", "completada", "start_date", "due_date")


class TareaSerializer(serializers.ModelSerializer):
    asignados = TareaAsignadaSerializer(many=True, read_only=True)
    evidencias = EvidenciaTareaSerializer(many=True, read_only=True)
    reporte = serializers.SerializerMethodField()
    bug_evidencias_count = serializers.SerializerMethodField()
    resolution_evidencias_count = serializers.SerializerMethodField()
    subtareas = serializers.SerializerMethodField()
    start_date = serializers.DateTimeField(source="inicio", read_only=True)
    due_date = serializers.DateTimeField(source="vence", read_only=True)

    class Meta:
        model = Tarea
        fields = (
            "id", "lista", "tarea_padre", "titulo", "descripcion", "estado",
            "prioridad", "creada", "vence", "inicio", "start_date", "due_date",
            "orden", "creado_por", "asignados", "evidencias", "reporte",
            "bug_evidencias_count", "resolution_evidencias_count",
            "descripcion_problema", "causa", "raiz",
            "desarrollo_estrategia", "resultados", "completada", "subtareas",
        )
        read_only_fields = ("id", "creado_por", "creada", "orden")

    def get_reporte(self, obj):
        if hasattr(obj, "reporte_incidencia"):
            return ReporteIncidenciaMiniSerializer(obj.reporte_incidencia).data
        return None

    def get_bug_evidencias_count(self, obj):
        return obj.evidencias.filter(tipo="BUG").count()

    def get_resolution_evidencias_count(self, obj):
        return obj.evidencias.filter(tipo="RESOLUTION").count()

    def get_subtareas(self, obj):
        if obj.tarea_padre is not None:
            return []
        hijas = obj.subtareas.all().order_by('id')
        return SubtareaListSerializer(hijas, many=True).data


class TareaCreateSerializer(serializers.ModelSerializer):
    asignados_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        write_only=True,
    )
    subtareas = serializers.JSONField(required=False, write_only=True)

    class Meta:
        model = Tarea
        fields = (
            "lista", "titulo", "descripcion", "prioridad", "inicio", "vence",
            "estado", "descripcion_problema", "causa", "raiz",
            "desarrollo_estrategia", "resultados", "asignados_ids", "subtareas",
        )

    def create(self, validated_data):
        subtareas_data = validated_data.pop("subtareas", []) or []
        validated_data.pop("asignados_ids", None)

        tarea_raiz = Tarea.objects.create(**validated_data)

        for sub in subtareas_data:
            titulo = str(sub.get("titulo") or sub.get("title") or "").strip()
            if not titulo:
                continue
            Tarea.objects.create(
                lista=tarea_raiz.lista,
                tarea_padre=tarea_raiz,
                titulo=titulo,
                descripcion="",
                completada=bool(sub.get("done", sub.get("completada", False))),
                creado_por=tarea_raiz.creado_por,
                estado=tarea_raiz.estado,
                prioridad=tarea_raiz.prioridad,
                inicio=sub.get("start_date") or sub.get("inicio") or None,
                vence=sub.get("due_date") or sub.get("vence") or None,
            )

        return tarea_raiz


class TareaUpdateSerializer(serializers.ModelSerializer):
    asignados_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        write_only=True,
    )
    subtareas = serializers.JSONField(required=False, write_only=True)

    class Meta:
        model = Tarea
        fields = (
            "titulo", "descripcion", "prioridad", "inicio", "vence", "lista",
            "estado", "descripcion_problema", "causa", "raiz",
            "desarrollo_estrategia", "resultados", "asignados_ids", "subtareas",
        )

    def update(self, instance, validated_data):
        subtareas_data = validated_data.pop("subtareas", None)
        validated_data.pop("asignados_ids", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if instance.lista and instance.lista.nombre in ["Por hacer", "En proceso", "Hecho"]:
            instance.estado = instance.lista.nombre

        instance.save()

        if subtareas_data is not None:
            instance.subtareas.all().delete()
            for sub in subtareas_data:
                titulo = str(sub.get("titulo") or sub.get("title") or "").strip()
                if not titulo:
                    continue
                Tarea.objects.create(
                    lista=instance.lista,
                    tarea_padre=instance,
                    titulo=titulo,
                    descripcion="",
                    completada=bool(sub.get("done", sub.get("completada", False))),
                    creado_por=instance.creado_por,
                    estado=instance.estado,
                    prioridad=instance.prioridad,
                    inicio=sub.get("start_date") or sub.get("inicio") or None,
                    vence=sub.get("due_date") or sub.get("vence") or None,
                )

        return instance


class NotificacionClickupSerializer(serializers.ModelSerializer):
    equipo_nombre = serializers.CharField(source="equipo.nombre", read_only=True)
    proyecto_nombre = serializers.CharField(source="proyecto.nombre", read_only=True)
    tarea_titulo = serializers.CharField(source="tarea.titulo", read_only=True)

    class Meta:
        model = NotificacionClickup
        fields = (
            "id", "tipo", "titulo", "mensaje", "estado", "creado_en", "leido_en",
            "equipo", "equipo_nombre", "proyecto", "proyecto_nombre",
            "tarea", "tarea_titulo", "invitacion",
        )


class ReporteIncidenciaCreateSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=["BUG", "SUGGESTION"])
    titulo = serializers.CharField(max_length=180)
    descripcion = serializers.CharField()
    imagenes = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        allow_empty=True,
        write_only=True,
    )

    def validate_titulo(self, value):
        value = str(value or "").strip()
        if not value:
            raise serializers.ValidationError("titulo es requerido.")
        return value

    def validate_descripcion(self, value):
        value = str(value or "").strip()
        if not value:
            raise serializers.ValidationError("descripcion es requerida.")
        return value


class ReporteIncidenciaDetailSerializer(serializers.ModelSerializer):
    reportado_por = UsuarioMiniSerializer(read_only=True)
    evidencias_bug = serializers.SerializerMethodField()
    evidencias_solucion = serializers.SerializerMethodField()

    class Meta:
        model = ReporteIncidencia
        fields = (
            "id", "tipo", "titulo", "descripcion", "estado", "reportado_por",
            "creado_en", "actualizado_en", "resuelto_en",
            "evidencias_bug", "evidencias_solucion",
        )

    def get_evidencias_bug(self, obj):
        qs = obj.evidencias.filter(tipo="BUG").order_by("-creado_en")
        return EvidenciaTareaSerializer(qs, many=True, context=self.context).data

    def get_evidencias_solucion(self, obj):
        qs = obj.evidencias.filter(tipo="RESOLUTION").order_by("-creado_en")
        return EvidenciaTareaSerializer(qs, many=True, context=self.context).data