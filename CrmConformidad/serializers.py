from rest_framework import serializers
from .models import Cliente, ExpedienteConformidad, ExpedienteDocumento, Usuario, Rol
from django.contrib.auth.hashers import make_password, check_password
from django.core import signing

DEALERS_VALIDOS = [
    "VW Cordoba",
    "VW Orizaba",
    "VW Poza Rica",
    "VW Tuxtepec",
    "VW Tuxpan",
    "Chirey",
    "JAECOO R&R",
]

class ExpedienteDocumentoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ExpedienteDocumento
        fields = ["id_doc", "nombre_original", "mime", "size", "url", "creado_en"]

    def get_url(self, obj):
        request = self.context.get("request")
        if not request:
            return obj.archivo.url
        return request.build_absolute_uri(obj.archivo.url)


class CasoSerializer(serializers.Serializer):
    # Cliente
    id_cliente = serializers.IntegerField(required=False)
    chasis = serializers.CharField(required=True)
    os_exp = serializers.IntegerField(required=True)
    agencia = serializers.ChoiceField(choices=DEALERS_VALIDOS)
    cliente_nombre = serializers.CharField(required=True)
    cliente_apellidos = serializers.CharField(required=True)
    telefono = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    correo = serializers.EmailField(required=False, allow_blank=True, allow_null=True)

    # Expediente
    id_exp = serializers.IntegerField(required=False)
    linea = serializers.CharField(required=True)
    fecha_atencion = serializers.DateField(required=True)
    fecha_reclamacion = serializers.DateField(required=True)
    origen = serializers.CharField(required=True)
    estado = serializers.CharField(required=True)
    problema = serializers.CharField(required=True)
    calificacion = serializers.DecimalField(max_digits=2,decimal_places=1,required=False,allow_null=True,min_value=0,max_value=5)
    recopilacion = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    causa = serializers.CharField(required=False, allow_blank=True)
    raiz = serializers.CharField(required=False, allow_blank=True)
    obs_contacto_1 = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    fecha_contacto_1 = serializers.DateTimeField(required=False, allow_null=True)
    obs_contacto_2 = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    fecha_contacto_2 = serializers.DateTimeField(required=False, allow_null=True)
    obs_contacto_3 = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    fecha_contacto_3 = serializers.DateTimeField(required=False, allow_null=True)
    obs_contacto_cierre = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    fecha_contacto_cierre = serializers.DateTimeField(required=False, allow_null=True)

    def to_representation(self, instance: ExpedienteConformidad):
        c = instance.cliente
        return {
            "id_exp": instance.id_exp,
            "id_cliente": c.id_cliente,
            "chasis": c.chasis,
            "os_exp": c.os_exp,
            "agencia": c.agencia,
            "cliente_nombre": c.nombre,
            "cliente_apellidos": c.apellidos,
            "telefono": c.telefono,
            "correo": c.correo,

            "linea": instance.linea,
            "fecha_atencion": instance.fecha_atencion,
            "fecha_reclamacion": instance.fecha_reclamacion,
            "origen": instance.origen,
            "estado": instance.estado,
            "problema": instance.problema,
            "calificacion": instance.calificacion,
            "recopilacion": instance.recopilacion,
            "causa": instance.caso,
            "raiz": instance.raiz,
            "obs_contacto_1": instance.obs_contacto_1,
            "fecha_contacto_1": instance.fecha_contacto_1,
            "obs_contacto_2": instance.obs_contacto_2,
            "fecha_contacto_2": instance.fecha_contacto_2,
            "obs_contacto_3": instance.obs_contacto_3,
            "fecha_contacto_3": instance.fecha_contacto_3,
            "obs_contacto_cierre": instance.obs_contacto_cierre,
            "fecha_contacto_cierre": instance.fecha_contacto_cierre,
            "documentacion": ExpedienteDocumentoSerializer(
                instance.documentos.all(),
                many=True,
                context=self.context
            ).data,
        }

    def create(self, validated):
        # Cliente
        cliente = Cliente.objects.create(
            chasis=validated["chasis"],
            os_exp=validated["os_exp"],
            agencia=validated["agencia"],
            nombre=validated["cliente_nombre"],
            apellidos=validated["cliente_apellidos"],
            telefono=validated.get("telefono") or "",
            correo=validated.get("correo") or "",
        )

        # Expediente
        exp = ExpedienteConformidad.objects.create(
            cliente=cliente,
            linea=validated["linea"],
            fecha_atencion=validated["fecha_atencion"],
            fecha_reclamacion=validated["fecha_reclamacion"],
            origen=validated["origen"],
            estado=validated["estado"],
            problema=validated["problema"],
            calificacion=validated.get("calificacion"),
            recopilacion=validated.get("recopilacion", ""),
            caso=validated.get("causa", ""),
            raiz=validated.get("raiz", ""),
            obs_contacto_1=validated.get("obs_contacto_1"),
            fecha_contacto_1=validated.get("fecha_contacto_1"),
            obs_contacto_2=validated.get("obs_contacto_2"),
            fecha_contacto_2=validated.get("fecha_contacto_2"),
            obs_contacto_3=validated.get("obs_contacto_3"),
            fecha_contacto_3=validated.get("fecha_contacto_3"),
            obs_contacto_cierre=validated.get("obs_contacto_cierre"),
            fecha_contacto_cierre=validated.get("fecha_contacto_cierre"),
        )
        return exp

    def update(self, instance: ExpedienteConformidad, validated):
        # Cliente
        c = instance.cliente
        c.chasis = validated.get("chasis", c.chasis)
        c.os_exp = validated.get("os_exp", c.os_exp)
        c.agencia = validated.get("agencia", c.agencia)
        c.nombre = validated.get("cliente_nombre", c.nombre)
        c.apellidos = validated.get("cliente_apellidos", c.apellidos)
        c.telefono = validated.get("telefono", c.telefono)
        c.correo = validated.get("correo", c.correo)
        c.save()

        # Expediente
        instance.linea = validated.get("linea", instance.linea)
        instance.fecha_atencion = validated.get("fecha_atencion", instance.fecha_atencion)
        instance.fecha_reclamacion = validated.get("fecha_reclamacion", instance.fecha_reclamacion)
        instance.origen = validated.get("origen", instance.origen)
        instance.estado = validated.get("estado", instance.estado)
        instance.problema = validated.get("problema", instance.problema)
        instance.calificacion = validated.get("calificacion", instance.calificacion)
        instance.recopilacion = validated.get("recopilacion", instance.recopilacion)
        instance.caso = validated.get("causa", instance.caso)
        instance.raiz = validated.get("raiz", instance.raiz)
        instance.obs_contacto_1 = validated.get("obs_contacto_1", instance.obs_contacto_1)
        instance.fecha_contacto_1 = validated.get("fecha_contacto_1", instance.fecha_contacto_1)
        instance.obs_contacto_2 = validated.get("obs_contacto_2", instance.obs_contacto_2)
        instance.fecha_contacto_2 = validated.get("fecha_contacto_2", instance.fecha_contacto_2)
        instance.obs_contacto_3 = validated.get("obs_contacto_3", instance.obs_contacto_3)
        instance.fecha_contacto_3 = validated.get("fecha_contacto_3", instance.fecha_contacto_3)
        instance.obs_contacto_cierre = validated.get("obs_contacto_cierre", instance.obs_contacto_cierre)
        instance.fecha_contacto_cierre = validated.get("fecha_contacto_cierre", instance.fecha_contacto_cierre)

        instance.save()
        return instance

class UsuarioRegisterSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=50)
    apellidos = serializers.CharField(max_length=70, required=False, allow_blank=True, allow_null=True)
    usuario = serializers.CharField(max_length=10)
    correo = serializers.EmailField(max_length=255)
    contrasena = serializers.CharField(write_only=True)
    agencia = serializers.ChoiceField(choices=DEALERS_VALIDOS)

    def validate_usuario(self, value):
        if Usuario.objects.filter(usuario=value).exists():
            raise serializers.ValidationError("Ese usuario ya existe.")
        return value

    def validate_correo(self, value):
        if Usuario.objects.filter(correo=value).exists():
            raise serializers.ValidationError("Ese correo ya existe.")
        return value

    def create(self, validated_data):
        # Rol por defecto: EMPLEADO
        # Recomendación: crea el rol "Empleado" en tu tabla roles.
        rol_empleado = (
            Rol.objects.filter(nombre__iexact="Empleado").first()
            or Rol.objects.filter(id_rol=2).first()
        )
        if not rol_empleado:
            raise serializers.ValidationError("No existe el rol 'Empleado' (crea el registro en roles).")

        u = Usuario.objects.create(
            nombre=validated_data["nombre"],
            apellidos=validated_data.get("apellidos") or "",
            usuario=validated_data["usuario"],
            correo=validated_data["correo"],
            contrasena=make_password(validated_data["contrasena"]),  # hash seguro
            rol=rol_empleado,
            agencia=validated_data["agencia"],
        )
        return u


class UsuarioLoginSerializer(serializers.Serializer):
    usuario = serializers.CharField()
    contrasena = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = Usuario.objects.filter(usuario=attrs["usuario"]).select_related("rol").first()
        if not user:
            raise serializers.ValidationError("Usuario o contraseña inválidos.")

        if not check_password(attrs["contrasena"], user.contrasena):
            raise serializers.ValidationError("Usuario o contraseña inválidos.")

        attrs["user"] = user
        return attrs
    
class AdminUsuarioCreateSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=50)
    apellidos = serializers.CharField(max_length=70, required=False, allow_blank=True, allow_null=True)
    usuario = serializers.CharField(max_length=10)
    correo = serializers.EmailField(max_length=255)
    contrasena = serializers.CharField(write_only=True)
    agencia = serializers.ChoiceField(choices=DEALERS_VALIDOS)
    id_rol = serializers.IntegerField()

    def validate_usuario(self, value):
        if Usuario.objects.filter(usuario=value).exists():
            raise serializers.ValidationError("Ese usuario ya existe.")
        return value

    def validate_correo(self, value):
        if Usuario.objects.filter(correo=value).exists():
            raise serializers.ValidationError("Ese correo ya existe.")
        return value

    def validate_id_rol(self, value):
        if not Rol.objects.filter(id_rol=value).exists():
            raise serializers.ValidationError("Rol inválido.")
        return value

    def create(self, validated_data):
        rol = Rol.objects.get(id_rol=validated_data["id_rol"])
        u = Usuario.objects.create(
            nombre=validated_data["nombre"],
            apellidos=validated_data.get("apellidos") or "",
            usuario=validated_data["usuario"],
            correo=validated_data["correo"],
            contrasena=make_password(validated_data["contrasena"]),
            rol=rol,
            agencia=validated_data["agencia"],
        )
        return u

def generar_token_usuario(id_usuario: int) -> str:
    signer = signing.TimestampSigner()
    return signer.sign(str(id_usuario))