from django.db import models
from django.utils import timezone
from citas.models import ClienteComercial


class SolicitudCredito(models.Model):
    cliente = models.ForeignKey(
        ClienteComercial,
        db_column="id_cliente",
        on_delete=models.PROTECT,
        related_name="solicitud_credito",
    )

    agencia = models.CharField(max_length=120, default="", null=True)
    id_soli_cred = models.CharField(max_length=120, default="")
    producto_financiero = models.CharField(max_length=120, default="")
    plazo_meses = models.CharField(max_length=50, default="", null=True, blank=True)
    monto_financiero = models.CharField(max_length=120, default="", null=True, blank=True)
    auto_interes = models.CharField(max_length=255, default="")
    canal_origen = models.CharField(max_length=200, default="", blank=True)
    asesor_ventas = models.CharField(max_length=200, default="", null=True, blank=True)
    estado_financiamiento = models.CharField(max_length=200, default="")
    estado_compra = models.CharField(max_length=200, default="")
    fecha_respuesta = models.DateTimeField(null=True)
    comentarios = models.TextField(max_length=2000, default="", null=True, blank=True)

    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "solicitud_credito"
        managed = True
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.cliente.nombre or 'Cliente'} - {self.cliente.telefono}"

class LongDrive(models.Model):
    # Formato nuevo Long Drive
    requiere_factura = models.CharField(max_length=20, default="", blank=True)
    forma_pago = models.CharField(max_length=120, default="", blank=True)
    numero_certificado = models.CharField(
        max_length=40, default="", blank=True, db_index=True
    )
    compania = models.CharField(max_length=120, default="", blank=True)
    numero_contrato = models.CharField(max_length=40, default="", blank=True)
    numero_cliente = models.CharField(max_length=40, default="", blank=True)

    modelo = models.CharField(max_length=120, default="", blank=True)
    version = models.CharField(max_length=255, default="", blank=True)
    clave_comercial = models.CharField(max_length=50, default="", blank=True)
    numero_serie = models.CharField(
        max_length=50, default="", blank=True, db_index=True
    )
    concesionario = models.CharField(
        max_length=30, default="", blank=True, db_index=True
    )

    fecha_creacion = models.DateTimeField(null=True, blank=True)
    fecha_saga = models.DateField(null=True, blank=True)

    precio_sin_iva = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    precio_con_iva = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    cobertura = models.CharField(
        max_length=150, default="", blank=True, db_index=True
    )
    tipo_cliente = models.CharField(max_length=80, default="", blank=True)
    nombre_razon_social = models.CharField(
        max_length=255, default="", blank=True
    )

    fecha_nacimiento_constitucion = models.DateField(null=True, blank=True)
    nacionalidad = models.CharField(max_length=80, default="", blank=True)
    pais_nacimiento_constitucion = models.CharField(
        max_length=120, default="", blank=True
    )
    genero = models.CharField(max_length=50, default="", blank=True)

    rfc = models.CharField(
        max_length=30, default="", blank=True, db_index=True
    )
    regimen_fiscal = models.CharField(max_length=255, default="", blank=True)

    calle_numero = models.CharField(max_length=255, default="", blank=True)
    codigo_postal = models.CharField(max_length=20, default="", blank=True)
    colonia = models.CharField(max_length=150, default="", blank=True)
    municipio_delegacion = models.CharField(
        max_length=150, default="", blank=True
    )
    entidad_federativa_estado = models.CharField(
        max_length=150, default="", blank=True
    )

    estatus_certificado = models.CharField(
        max_length=100, default="", blank=True
    )
    estatus_pago = models.CharField(max_length=100, default="", blank=True)
    terminos_condiciones = models.CharField(
        max_length=100, default="", blank=True
    )
    aviso_privacidad = models.CharField(
        max_length=100, default="", blank=True
    )
    autorizacion_cargo_cuenta_bancaria = models.CharField(
        max_length=100, default="", blank=True
    )

    estatus_link_openpay = models.CharField(
        max_length=100, default="", blank=True
    )
    estatus_pago_openpay = models.CharField(
        max_length=100, default="", blank=True
    )

    # En el reporte puede contener fecha o textos como "No aplica".
    fecha_pago_openpay = models.CharField(
        max_length=100, default="", blank=True
    )
    meses_sin_intereses = models.CharField(
        max_length=50, default="", blank=True
    )

    condicion = models.CharField(max_length=80, default="", blank=True)
    marca = models.CharField(max_length=80, default="", blank=True)
    anio = models.PositiveIntegerField(null=True, blank=True)
    kilometraje = models.PositiveIntegerField(null=True, blank=True)
    tipo_uso = models.CharField(max_length=100, default="", blank=True)
    motor = models.CharField(max_length=80, default="", blank=True)
    uso_cfdi = models.CharField(max_length=150, default="", blank=True)

    correo_electronico = models.EmailField(
        max_length=254, default="", blank=True
    )
    telefono_celular = models.CharField(
        max_length=30, default="", blank=True
    )

    primer_nombre_usuario_1 = models.CharField(
        max_length=150, default="", blank=True
    )
    segundo_nombre_usuario_1 = models.CharField(
        max_length=150, default="", blank=True
    )
    apellido_paterno_usuario_1 = models.CharField(
        max_length=150, default="", blank=True
    )
    apellido_materno_usuario_1 = models.CharField(
        max_length=150, default="", blank=True
    )
    correo_electronico_usuario_1 = models.EmailField(
        max_length=254, default="", blank=True
    )

    primer_nombre_usuario_2 = models.CharField(
        max_length=150, default="", blank=True
    )
    segundo_nombre_usuario_2 = models.CharField(
        max_length=150, default="", blank=True
    )
    apellido_paterno_usuario_2 = models.CharField(
        max_length=150, default="", blank=True
    )
    apellido_materno_usuario_2 = models.CharField(
        max_length=150, default="", blank=True
    )
    correo_electronico_usuario_2 = models.EmailField(
        max_length=254, default="", blank=True
    )

    primer_nombre_representante_legal = models.CharField(
        max_length=150, default="", blank=True
    )
    segundo_nombre_representante_legal = models.CharField(
        max_length=150, default="", blank=True
    )
    apellido_paterno_representante_legal = models.CharField(
        max_length=150, default="", blank=True
    )
    apellido_materno_representante_legal = models.CharField(
        max_length=150, default="", blank=True
    )
    fecha_nacimiento_representante_legal = models.DateField(
        null=True,
        blank=True,
    )

    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "long_drive"
        managed = True
        ordering = ["-creado"]

        def __str__(self):
            identificador = self.numero_certificado or self.numero_serie or "Long Drive"
            cliente = self.nombre_razon_social or "Sin cliente"
            return f"{identificador} - {cliente}"
