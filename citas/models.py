# citas/models.py
from django.db import models
from django.utils import timezone

class Citas(models.Model):
    nombre = models.CharField(max_length=200, blank=True, default="")
    telefono = models.CharField(max_length=32, db_index=True, unique=False)
    correo = models.CharField(max_length=200, blank=True, default="")
    auto_interes = models.CharField(max_length=255, blank=True, default="")
    agencia = models.CharField(max_length=120, blank=True, default="")
    fecha_hora_cita = models.DateTimeField(null=True, blank=True)
    fuerza = models.CharField(max_length=120, blank=True, default="")
    asistencia = models.BooleanField(default=False)
    be_back = models.BooleanField(default=False)

    tipo_cita = models.CharField(max_length=120, blank=True, default="")
    fuente_prospeccion = models.CharField(max_length=120, blank=True, default="")
    asesor_digital = models.CharField(max_length=200, blank=True, default="")
    asesor_solicita = models.CharField(max_length=200, blank=True, default="")
    asesor_asignado = models.CharField(max_length=200, blank=True, default="") 
    asesor_atendio = models.CharField(max_length=200, blank=True, default="")
    
    folio_venta = models.CharField(max_length=200, blank=True, default="")
    num_serie = models.CharField(max_length=200, blank=True, default="")
    estado_ingreso = models.CharField(max_length=120, blank=True, default="")
    tipo_venta = models.CharField(max_length=200, blank=True, default="")
    registro_salesforce = models.BooleanField(default=False)
    comentarios = models.CharField(max_length=2000, blank=True, default="")
    comentarios_cliente = models.CharField(max_length=2000, blank=True, default="")
    
    class Meta:
        db_table = "citas"
        managed = True

    def __str__(self):
        return f"{self.nombre} ({self.telefono})".strip()

