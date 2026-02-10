from django.db import models


class Rol(models.Model):
    id_rol = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=200)

    class Meta:
        db_table = "roles"
        managed = False

    def __str__(self):
        return self.nombre


class Usuario(models.Model):
    id_usuario = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=50)
    apellidos = models.CharField(max_length=70, blank=True, null=True)
    usuario = models.CharField(max_length=10)
    correo = models.EmailField(max_length=255)
    contrasena = models.CharField(max_length=255)
    rol = models.ForeignKey(Rol, db_column="rol", on_delete=models.PROTECT)
    agencia = models.CharField(max_length=100)

    class Meta:
        db_table = "usuarios"
        managed = False

    def __str__(self):
        return f"{self.nombre} {self.apellidos or ''}".strip()


class Cliente(models.Model):
    id_cliente = models.AutoField(primary_key=True)
    chasis = models.CharField(max_length=255)
    nombre = models.CharField(max_length=50)
    apellidos = models.CharField(max_length=70)
    telefono = models.CharField(max_length=20)
    correo = models.EmailField(max_length=255)
    os_exp = models.IntegerField()
    agencia = models.CharField(max_length=100)

    class Meta:
        db_table = "clientes"
        managed = False

    def __str__(self):
        return f"{self.nombre} {self.apellidos}".strip()


class ExpedienteConformidad(models.Model):
    id_exp = models.AutoField(primary_key=True)
    linea = models.CharField(max_length=255)
    fecha_atencion = models.DateField()
    fecha_reclamacion = models.DateField()
    origen = models.CharField(max_length=100)
    estado = models.CharField(max_length=70)
    problema = models.TextField()
    calificacion = models.DecimalField(max_digits=2, decimal_places=1, default=0, null=True, blank=True)
    recopilacion = models.TextField()
    caso = models.CharField(max_length=255)
    raiz = models.CharField(max_length=100)
    obs_contacto_1 = models.TextField(blank=True, null=True)
    fecha_contacto_1 = models.DateTimeField(blank=True, null=True)

    obs_contacto_2 = models.TextField(blank=True, null=True)
    fecha_contacto_2 = models.DateTimeField(blank=True, null=True)

    obs_contacto_3 = models.TextField(blank=True, null=True)
    fecha_contacto_3 = models.DateTimeField(blank=True, null=True)

    obs_contacto_cierre = models.TextField(blank=True, null=True)
    fecha_contacto_cierre = models.DateTimeField(blank=True, null=True)
    cliente = models.ForeignKey(
        Cliente,
        db_column="id_cliente",
        on_delete=models.CASCADE,
        related_name="expedientes",
    )

    class Meta:
        db_table = "expediente_conformidad"
        managed = False

    def __str__(self):
        return f"Exp {self.id_exp} - Cliente {self.cliente_id}"


class ExpedienteDocumento(models.Model):
    id_doc = models.AutoField(primary_key=True)

    expediente = models.ForeignKey(
        ExpedienteConformidad,
        db_column="id_exp",
        related_name="documentos",
        on_delete=models.CASCADE,
    )

    # La tabla guarda un varchar(500) con la ruta.
    archivo = models.FileField(upload_to="crm_docs/%Y/%m/")
    nombre_original = models.CharField(max_length=255)
    mime = models.CharField(max_length=100, blank=True, null=True)
    size = models.IntegerField(blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "expediente_documento"
        managed = False
