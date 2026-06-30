# flujo/models.py

import unicodedata
import uuid

from django.core.exceptions import ValidationError
from django.db import models

from CrmConformidad.models import Usuario


def normalizar_texto(valor):
    texto = str(valor or "").strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto


class DiagramaFlujo(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="diagramas_flujo",
    )

    nombre = models.CharField(max_length=180)
    descripcion = models.TextField(blank=True, default="")

    # Estructura visual y tabular del diseñador.
    pasos = models.JSONField(default=list, blank=True)
    nodos = models.JSONField(default=list, blank=True)
    conexiones = models.JSONField(default=list, blank=True)
    metadatos = models.JSONField(default=dict, blank=True)

    total_pasos = models.PositiveIntegerField(default=0)
    total_nodos = models.PositiveIntegerField(default=0)
    total_conexiones = models.PositiveIntegerField(default=0)
    total_decisiones = models.PositiveIntegerField(default=0)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "flujo_diagramas_flujo"
        ordering = ["-actualizado_en"]
        indexes = [
            models.Index(fields=["usuario", "-actualizado_en"]),
            models.Index(fields=["nombre"]),
        ]

    def __str__(self):
        return self.nombre

    def clean(self):
        if not str(self.nombre or "").strip():
            raise ValidationError({"nombre": "El nombre del diagrama es obligatorio."})

        if not isinstance(self.pasos, list):
            raise ValidationError({"pasos": "pasos debe ser una lista."})

        if not isinstance(self.nodos, list):
            raise ValidationError({"nodos": "nodos debe ser una lista."})

        if not isinstance(self.conexiones, list):
            raise ValidationError({"conexiones": "conexiones debe ser una lista."})

        if not isinstance(self.metadatos, dict):
            raise ValidationError({"metadatos": "metadatos debe ser un objeto JSON."})

    def recalcular_estadisticas(self):
        pasos = self.pasos if isinstance(self.pasos, list) else []
        nodos = self.nodos if isinstance(self.nodos, list) else []
        conexiones = self.conexiones if isinstance(self.conexiones, list) else []

        self.total_pasos = len(pasos)
        self.total_nodos = len(nodos)
        self.total_conexiones = len(conexiones)

        self.total_decisiones = sum(
            1
            for paso in pasos
            if normalizar_texto(paso.get("tipo")) == "decision"
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        self.recalcular_estadisticas()
        super().save(*args, **kwargs)