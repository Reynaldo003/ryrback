# clickup/serializers.py
from rest_framework import serializers
from django.utils import timezone

from .models import Equipo, MiembroEquipo, InvitacionEquipo, Proyecto, Lista, Tarea, TareaAsignada
from CrmConformidad.models import Usuario


class UsuarioMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ("id_usuario", "nombre", "apellidos", "correo")


class EquipoSerializer(serializers.ModelSerializer):
    propietario = UsuarioMiniSerializer(read_only=True)

    class Meta:
        model = Equipo
        fields = ("id", "nombre", "descripcion", "propietario", "creado_en")


class MiembroEquipoSerializer(serializers.ModelSerializer):
    usuario = UsuarioMiniSerializer(read_only=True)

    class Meta:
        model = MiembroEquipo
        fields = ("id", "equipo", "usuario", "rol", "unido_en", "activo")
        read_only_fields = ("id", "unido_en")


class InvitacionEquipoSerializer(serializers.ModelSerializer):
    invitado_por = UsuarioMiniSerializer(read_only=True)
    esta_expirada = serializers.SerializerMethodField()

    class Meta:
        model = InvitacionEquipo
        fields = (
            "id", "equipo", "correo", "rol", "token",
            "estado", "invitado_por", "creado_en", "expira_en",
            "esta_expirada", "aceptado_en", "aceptado_por"
        )
        read_only_fields = ("id", "token", "estado", "creado_en", "aceptado_en", "aceptado_por")

    def get_esta_expirada(self, obj):
        return obj.esta_expirada()

    def validate_correo(self, value):
        return value.strip().lower()

    def validate_expira_en(self, value):
        if value and value <= timezone.now():
            raise serializers.ValidationError("expira_en debe ser futura.")
        return value


class ProyectoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proyecto
        fields = ("id", "equipo", "nombre", "descripcion", "creado_en")
        read_only_fields = ("id", "creado_en")


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


class TareaSerializer(serializers.ModelSerializer):
    asignados = TareaAsignadaSerializer(many=True, read_only=True)

    class Meta:
        model = Tarea
        fields = (
            "id", "lista", "titulo", "descripcion",
            "prioridad", "vence_en", "orden",
            "creado_por", "creado_en", "asignados",
        )
        read_only_fields = ("id", "creado_por", "creado_en")