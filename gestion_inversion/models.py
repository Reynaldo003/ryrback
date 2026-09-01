#gestion_inversion/models.py
import uuid
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone


CLASIFICACIONES = [
    ("Social Media", "Social Media"),
    ("Posicionamiento", "Posicionamiento"),
    ("Consumo Interno", "Consumo Interno"),
    ("Eventos y Prospección", "Eventos y Prospección"),
]

DEALERS = [
    ("VW Cordoba", "VW Cordoba"),
    ("VW Orizaba", "VW Orizaba"),
    ("VW Tuxpan", "VW Tuxpan"),
    ("VW Poza Rica", "VW Poza Rica"),
    ("VW Tuxtepec", "VW Tuxtepec"),
]

DEPARTAMENTOS = [
    ("Nuevos", "Nuevos"),
    ("Usados", "Usados"),
    ("Comerciales", "Comerciales"),
    ("Servicio", "Servicio"),
    ("HyP", "HyP"),
]

SITIOS_POR_CLASIFICACION = {
    "Social Media": [
        "Google ADS",
        "MetaADS",
        "MercadoLibre",
        "TikTok",
        "YouTube",
        "ChatGPT",
    ],
    "Posicionamiento": [
        "Costo de Producción Multimedios",
        "Publicitarios Físicos",
        "Folletos",
        "Cartas",
    ],
    "Consumo Interno": [
        "Consumo de alimentos",
        "Instalación",
        "Amenidades",
    ],
    "Eventos y Prospección": [
        "Eventos",
    ],
}


def validar_pdf_real(archivo):
    posicion = archivo.tell() if hasattr(archivo, "tell") else 0

    cabecera = archivo.read(5)

    if hasattr(archivo, "seek"):
        archivo.seek(posicion)

    if cabecera != b"%PDF-":
        raise ValidationError(
            "El archivo seleccionado no es un PDF válido."
        )


def ruta_factura(instance, filename):
    ahora = timezone.now()

    return (f"gestion-inversion/" f"{ahora:%Y}/" f"{ahora:%m}/" f"{uuid.uuid4().hex}.pdf")


class FacturaMarketing(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        PROCESANDO = "procesando", "Procesando"
        PROCESADA = "procesada", "Procesada"
        ERROR = "error", "Error"

    id_factura = models.AutoField(primary_key=True)

    archivo = models.FileField(upload_to=ruta_factura, validators=[FileExtensionValidator(["pdf"]), validar_pdf_real,],)
    nombre_original = models.CharField(max_length=255,)
    tipo_mime = models.CharField(max_length=150, default="application/pdf",)
    tamano_bytes = models.PositiveBigIntegerField(default=0,)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True,)
    error_analisis = models.TextField(blank=True, default="",)
    creado_por = models.CharField(max_length=200, blank=True, default="", db_index=True,)
    dealer = models.CharField(max_length=100, choices=DEALERS, blank=True, default="", db_index=True)
    departamento = models.CharField(max_length=100, choices=DEPARTAMENTOS, blank=True, default="", db_index=True)

    emisor_razon_social = models.CharField(max_length=300,blank=True,default="",)
    emisor_rfc = models.CharField(max_length=30,blank=True,default="",db_index=True,)
    emisor_regimen_fiscal = models.CharField(max_length=300,blank=True,default="",)
    emisor_domicilio = models.TextField(blank=True,default="",)

    receptor_razon_social = models.CharField(max_length=300,blank=True,default="",)
    receptor_rfc = models.CharField(max_length=30,blank=True,default="",db_index=True,)
    receptor_uso_cfdi = models.CharField(max_length=200,blank=True,default="",)
    
    uuid_cfdi = models.CharField(max_length=100,blank=True,default="",db_index=True,)
    folio = models.CharField(max_length=100,blank=True,default="",db_index=True,)
    fecha_factura = models.DateField(null=True,blank=True,db_index=True,)
    moneda = models.CharField(max_length=20,blank=True,default="MXN",)
    metodo_pago = models.CharField(max_length=100,blank=True,default="",)
    forma_pago = models.CharField(max_length=200,blank=True,default="",)

    subtotal = models.DecimalField(max_digits=18,decimal_places=2,default=0,)
    impuestos = models.DecimalField(max_digits=18,decimal_places=2,default=0,)
    total = models.DecimalField(max_digits=18,decimal_places=2,default=0,)
    # Respuesta original estructurada de openai.
    resultado_ia = models.JSONField(default=dict,blank=True,)
    analizado = models.DateTimeField(null=True,blank=True,)
    creado = models.DateTimeField(auto_now_add=True,)
    actualizado = models.DateTimeField(auto_now=True,)

    class Meta:
        db_table = "analisis_facturas"
        managed = True
        ordering = ["-creado","-id_factura",]
        indexes = [
            models.Index(fields=["estado", "creado"],name="fact_estado_creado_idx",),
            models.Index(fields=["emisor_rfc", "fecha_factura"],name="fact_emisor_fecha_idx",),
            models.Index(fields=["receptor_rfc", "fecha_factura"],name="fact_receptor_fecha_idx",),
            models.Index(fields=["dealer", "departamento", "fecha_factura"], name="fact_dealer_depto_idx"),
        ]

    def __str__(self):
        return (self.nombre_original or f"Factura {self.id_factura}")

class ConceptoFactura(models.Model):
    id_concepto = models.AutoField(primary_key=True,)
    factura = models.ForeignKey(FacturaMarketing,on_delete=models.CASCADE,related_name="conceptos",)
    orden = models.PositiveIntegerField(default=1,)
    clave = models.CharField(max_length=100,blank=True,default="",)
    descripcion = models.TextField(blank=True,default="",)
    cantidad = models.DecimalField(max_digits=14,decimal_places=4,default=0,)
    unidad = models.CharField(max_length=100,blank=True,default="",)
    precio_unitario = models.DecimalField(max_digits=18,decimal_places=4,default=0,)

    importe = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
    )

    # =========================================================
    # DATOS CAPTURADOS MANUALMENTE POR MARKETING
    # =========================================================

    clasificacion = models.CharField(
        max_length=100,
        choices=CLASIFICACIONES,
        blank=True,
        default="",
        db_index=True,
    )

    sitio = models.CharField(
        max_length=150,
        blank=True,
        default="",
        db_index=True,
    )

    motivo = models.TextField(
        blank=True,
        default="",
    )

    creado = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "analisis_facturas_conceptos"
        managed = True
        ordering = [
            "orden",
            "id_concepto",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["factura", "orden"],
                name="fact_concepto_orden_unico",
            ),
        ]
        indexes = [
            models.Index(
                fields=["factura", "orden"],
                name="fact_concepto_fact_idx",
            ),
            models.Index(
                fields=["clasificacion", "sitio"],
                name="fact_concepto_clas_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if not self.sitio:
            return

        if not self.clasificacion:
            raise ValidationError({
                "sitio":
                    "Selecciona primero una clasificación."
            })

        opciones = SITIOS_POR_CLASIFICACION.get(
            self.clasificacion,
            [],
        )

        if self.sitio not in opciones:
            raise ValidationError({
                "sitio":
                    "El sitio/rubro no pertenece a la clasificación seleccionada."
            })

    def __str__(self):
        return (
            f"{self.factura_id} - "
            f"{self.orden} - "
            f"{self.descripcion[:60]}"
        )


@receiver(post_delete, sender=FacturaMarketing)
def eliminar_pdf_factura(sender, instance, **kwargs):
    if not instance.archivo:
        return

    try:
        instance.archivo.delete(
            save=False,
        )
    except Exception:
        pass