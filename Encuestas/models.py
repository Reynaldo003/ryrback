#Encuestas/models.py
from django.db import models

class EncuestaSatisfaccion(models.Model):
    id_encuesta = models.AutoField(primary_key=True)
    creado = models.DateTimeField(auto_now_add=True)
    agencia = models.CharField(max_length=200, blank=True, default="")
    nombre_cliente = models.CharField(max_length=200, blank=True, default="")
    asesor_atendio = models.CharField(max_length=200, blank=True, default="")
    motivo_visita = models.CharField(max_length=200, blank=True, default="")
    atencion_asesor = models.IntegerField(blank=True, default=0)
    seguimiento_asesor = models.IntegerField(blank=True, default=0)
    tiempo_entrega_unidad = models.IntegerField(blank=True, default=0)
    experiencia_recepcion = models.IntegerField(blank=True, default=0)
    comentario = models.CharField(max_length=1000, blank=True, null=True, default="")

    class Meta:
        db_table = "encuestas_satisfaccion"
        managed = True

class EncuestaServicio(models.Model):
    id_encuesta = models.AutoField(primary_key=True)
    creado = models.DateTimeField(auto_now_add=True)
    agencia = models.CharField(max_length=200, blank=True, default="")
    nombre_OS_cliente = models.CharField(max_length=200, blank=True, default="")
    asesor_atendio = models.CharField(max_length=200, blank=True, default="")
    satisfaccion_agenda_cita = models.CharField(max_length=200, blank=True, default="")
    satisfaccion_atencion_asesor = models.IntegerField(blank=True, default=0)
    percepcion_calidad_precio = models.IntegerField(blank=True, default=0)
    satisfaccion_servicio_ryr = models.IntegerField(blank=True, default=0)
    comentario = models.CharField(max_length=1000, blank=True, null=True, default="")

    class Meta:
        db_table = "encuestas_servicio"
        managed = True
