# documentacion/models.py
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify
from .requisitos import obtener_plantilla_solicitud

def generar_folio(): return f"SF-{timezone.now():%y%m%d}-{uuid.uuid4().hex[:6].upper()}"


def ruta_documento(instance, filename):
    agencia = slugify(instance.expediente.agencia) or "dealer"
    return f"documentacion/{agencia}/{instance.expediente.folio}/{instance.requisito_id}-{uuid.uuid4().hex[:8]}.pdf"

def ruta_solicitud_pdf(instance, filename):
    agencia = slugify(instance.agencia) or "dealer"

    return (
        f"documentacion/"
        f"{agencia}/"
        f"{instance.folio}/"
        f"solicitud/"
        f"{filename}"
    )

def validar_pdf_real(archivo):
    posicion = archivo.tell() if hasattr(archivo, "tell") else 0
    cabecera = archivo.read(5)
    if hasattr(archivo, "seek"): archivo.seek(posicion)
    if cabecera != b"%PDF-": raise ValidationError("El archivo seleccionado no es un PDF válido.")


class Expediente(models.Model):
    TIPO_PERSONA_CHOICES = [
        ("fisica_asalariada", "Persona Física Asalariada"),
        ("fisica_profesionista", "Persona Física Profesionista"),
        ("moral", "Persona Moral"),
    ]

    FINANCIAMIENTO_CHOICES = [
        ("credit", "Credit"),
        ("leasing", "Leasing"),
    ]

    id_expediente = models.AutoField(primary_key=True)
    folio = models.CharField(max_length=30, unique=True, default=generar_folio, editable=False)
    cliente = models.CharField(max_length=250)
    agencia = models.CharField(max_length=150, db_index=True)
    asesor_nombre = models.CharField(max_length=200, db_index=True, default="")
    creado_por = models.CharField(max_length=200, blank=True, default="")
    tipo_persona = models.CharField(max_length=30, choices=TIPO_PERSONA_CHOICES)
    financiamiento = models.CharField(max_length=20, choices=FINANCIAMIENTO_CHOICES)

    solicitud_pdf_plantilla = models.CharField(max_length=100,blank=True,default="",)
    solicitud_pdf = models.FileField(upload_to=ruta_solicitud_pdf,validators=[FileExtensionValidator(["pdf"]),validar_pdf_real,],null=True,blank=True,)
    solicitud_pdf_campos = models.JSONField(default=dict,blank=True,)
    solicitud_pdf_actualizado = models.DateTimeField(null=True,blank=True,)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.tipo_persona and self.financiamiento:
            plantilla = obtener_plantilla_solicitud(
                self.tipo_persona,
                self.financiamiento,
            )

            if not plantilla:
                raise ValidationError(
                    "La combinación de tipo de persona y financiamiento no es válida."
                )

            self.solicitud_pdf_plantilla = plantilla["value"]

        super().save(*args, **kwargs)

    class Meta:
        db_table = "documentacion_expedientes"
        managed = True
        ordering = ["-creado", "-id_expediente"]
        indexes = [
            models.Index(fields=["asesor_nombre", "creado"], name="doc_exp_asesor_idx"),
            models.Index(fields=["agencia", "creado"], name="doc_exp_agencia_idx"),
        ]

    def __str__(self): return f"{self.folio} - {self.cliente} - {self.asesor_nombre}"


class DocumentoExpediente(models.Model):
    id_documento = models.AutoField(primary_key=True)
    expediente = models.ForeignKey(
        Expediente,
        on_delete=models.CASCADE,
        related_name="documentos",
    )

    requisito_id = models.CharField(max_length=100, db_index=True)
    requisito_nombre = models.CharField(max_length=250)

    archivo = models.FileField(
        upload_to=ruta_documento,
        validators=[
            FileExtensionValidator(["pdf"]),
            validar_pdf_real,
        ],
    )

    nombre_original = models.CharField(max_length=255)
    tipo_mime = models.CharField(max_length=150, default="application/pdf")
    tamano_bytes = models.PositiveBigIntegerField(default=0)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "documentacion_expedientes_documentos"
        managed = True
        ordering = ["id_documento"]
        constraints = [
            models.UniqueConstraint(
                fields=["expediente", "requisito_id"],
                name="doc_unico_por_requisito",
            ),
        ]
        indexes = [
            models.Index(fields=["expediente", "requisito_id"], name="doc_exp_req_idx"),
        ]

    def __str__(self): return self.nombre_original or f"Documento {self.id_documento}"


@receiver(post_delete, sender=DocumentoExpediente)
def eliminar_archivo_fisico(sender, instance, **kwargs):
    if instance.archivo:
        try: instance.archivo.delete(save=False)
        except Exception: pass

@receiver(post_delete, sender=Expediente)
def eliminar_solicitud_pdf_fisica(sender, instance, **kwargs):
    if instance.solicitud_pdf:
        try:
            instance.solicitud_pdf.delete(save=False)
        except Exception:
            pass