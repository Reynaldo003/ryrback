from rest_framework import serializers
from .models import Tablero, Tema, ColaboradorTablero, ColaboradorTema, DatosTemaAnual
from .permisos import puede_editar_tablero, puede_editar_tema


class TableroSerializer(serializers.ModelSerializer):
    propietario_nombre = serializers.CharField(source="propietario.usuario", read_only=True)
    puede_editar = serializers.SerializerMethodField()
    es_propietario = serializers.SerializerMethodField()

    class Meta:
        model = Tablero
        fields = [
            "id", "nombre", "propietario", "propietario_nombre",
            "es_propietario", "puede_editar", "creado_en", "actualizado_en"
        ]
        read_only_fields = ["propietario", "creado_en", "actualizado_en"]

    def get_es_propietario(self, obj):
        return obj.propietario_id == self.context["request"].user.pk

    def get_puede_editar(self, obj):
        return puede_editar_tablero(self.context["request"].user, obj)

    def validate_nombre(self, valor):
        nombre = valor.strip()
        if not nombre:
            raise serializers.ValidationError("Indica un nombre.")
        if "::" in nombre:
            raise serializers.ValidationError('El nombre no puede contener "::".')
        return nombre

    def validate(self, attrs):
        nombre = attrs.get("nombre")
        if nombre:
            propietario = self.instance.propietario if self.instance else self.context["request"].user
            duplicado = Tablero.objects.filter(
                propietario=propietario, nombre__iexact=nombre, eliminado_en__isnull=True
            )
            if self.instance:
                duplicado = duplicado.exclude(pk=self.instance.pk)
            if duplicado.exists():
                raise serializers.ValidationError({"nombre": "Ya tienes un tablero con ese nombre."})
        return attrs


class TemaSerializer(serializers.ModelSerializer):
    propietario_nombre = serializers.CharField(source="propietario.usuario", read_only=True)
    puede_editar = serializers.SerializerMethodField()

    class Meta:
        model = Tema
        fields = ["id", "tablero", "propietario", "propietario_nombre", "nombre", "subtitulo", "puede_editar"]
        read_only_fields = ["propietario"]

    def get_puede_editar(self, obj):
        return puede_editar_tema(self.context["request"].user, obj)

    def validate_nombre(self, valor):
        nombre = valor.strip()
        if not nombre:
            raise serializers.ValidationError("Indica un nombre de tema.")
        return nombre

    def validate(self, attrs):
        tablero = attrs.get("tablero", self.instance.tablero if self.instance else None)
        nombre = attrs.get("nombre", self.instance.nombre if self.instance else None)
        if tablero and nombre:
            consulta = Tema.objects.filter(tablero=tablero, nombre__iexact=nombre)
            if self.instance:
                consulta = consulta.exclude(pk=self.instance.pk)
            if consulta.exists():
                raise serializers.ValidationError({"nombre": "Ya existe ese tema dentro del tablero."})
        return attrs


class InvitarSerializer(serializers.Serializer):
    id_usuario = serializers.IntegerField(min_value=1)
    rol = serializers.ChoiceField(choices=["editor", "lector"], default="lector")


class AccesoTableroSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.CharField(source="usuario.usuario", read_only=True)

    class Meta:
        model = ColaboradorTablero
        fields = ["id", "tablero", "usuario", "usuario_nombre", "rol", "estado", "invitado_por", "creado_en"]


class AccesoTemaSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.CharField(source="usuario.usuario", read_only=True)

    class Meta:
        model = ColaboradorTema
        fields = ["id", "tema", "usuario", "usuario_nombre", "rol", "estado", "invitado_por", "creado_en"]


class DatosTemaAnualSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0)
    filas = serializers.ListField(child=serializers.DictField(), allow_empty=True)
    columnas = serializers.ListField(child=serializers.DictField(), allow_empty=True)

    def validate(self, attrs):
        ids_filas = set()
        ids_columnas = set()
        for columna in attrs["columnas"]:
            ident = columna.get("id")
            if not isinstance(ident, (str, int)) or ident == "":
                raise serializers.ValidationError({"columnas": "Cada columna requiere id."})
            if str(ident) in ids_columnas:
                raise serializers.ValidationError({"columnas": "Hay columnas duplicadas."})
            ids_columnas.add(str(ident))
            if not isinstance(columna.get("nombre", ""), str):
                raise serializers.ValidationError({"columnas": "El nombre debe ser texto."})

        for fila in attrs["filas"]:
            ident = fila.get("id")
            if not isinstance(ident, (str, int)) or ident == "":
                raise serializers.ValidationError({"filas": "Cada KPI requiere id."})
            if str(ident) in ids_filas:
                raise serializers.ValidationError({"filas": "Hay KPI duplicados."})
            ids_filas.add(str(ident))
            if not isinstance(fila.get("kpi", ""), str) or not isinstance(fila.get("descripcion", ""), str):
                raise serializers.ValidationError({"filas": "KPI y descripción deben ser texto."})
            valores = fila.get("valores")
            if not isinstance(valores, list) or len(valores) != 12:
                raise serializers.ValidationError({"filas": "Cada KPI necesita exactamente 12 meses."})
            if any(not isinstance(valor, str) for valor in valores):
                raise serializers.ValidationError({"filas": "Los valores mensuales deben ser texto."})
            extras = fila.get("extras", {})
            if not isinstance(extras, dict):
                raise serializers.ValidationError({"filas": "El campo extras debe ser un objeto."})
        return attrs
