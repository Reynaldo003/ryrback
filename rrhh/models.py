from django.db import models
from django.utils import timezone


class VacanteReclutamiento(models.Model):
    id_vacante = models.AutoField(primary_key=True)

    estatus = models.CharField(max_length=50, default="Publicada")
    puesto = models.CharField(max_length=150)
    dealer = models.CharField(max_length=150)
    fuente_reclutamiento = models.CharField(
        max_length=80,
        default="Base de datos",
    )
    solicitado_por = models.CharField(max_length=150)

    fecha_publicacion = models.DateTimeField(default=timezone.now)
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    creado_at = models.DateTimeField(auto_now_add=True)
    actualizado_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rrhh_vacantes_reclutamiento"
        ordering = ["-id_vacante"]
        verbose_name = "Vacante de reclutamiento"
        verbose_name_plural = "Vacantes de reclutamiento"

    def __str__(self):
        return f"{self.id_vacante} - {self.puesto}"

    def save(self, *args, **kwargs):
        if self.estatus == "Cerrada":
            if not self.fecha_cierre:
                self.fecha_cierre = timezone.now()
        else:
            self.fecha_cierre = None

        super().save(*args, **kwargs)


class CandidatoReclutamiento(models.Model):
    id_candidato = models.AutoField(primary_key=True)

    vacante = models.ForeignKey(
        VacanteReclutamiento,
        related_name="candidatos",
        on_delete=models.CASCADE,
    )

    nombre = models.CharField(max_length=180)
    sexo = models.CharField(max_length=50)
    telefono = models.CharField(max_length=30)
    correo = models.EmailField(max_length=180)
    ubicacion = models.CharField(max_length=180)

    puesto_postulado = models.CharField(max_length=150)
    fuente = models.CharField(max_length=80)

    estatus = models.CharField(max_length=50, default="Nuevo")

    fecha_entrevista_do = models.DateField(null=True, blank=True)
    fecha_entrevista_gerente = models.DateField(null=True, blank=True)
    fecha_respuesta_gerente = models.DateField(null=True, blank=True)

    fecha_alta_khor = models.DateField(null=True, blank=True)
    fecha_realizacion_khor = models.DateField(null=True, blank=True)
    fecha_entrega_resultados_khor = models.DateField(null=True, blank=True)

    tipo_validacion_socioeconomica = models.CharField(
        max_length=80,
        default="No aplica",
    )

    fecha_solicitud_estudio_socioeconomico = models.DateField(null=True, blank=True)
    fecha_entrega_reporte_socioeconomico = models.DateField(null=True, blank=True)

    fecha_solicitud_referencias_laborales = models.DateField(null=True, blank=True)
    fecha_entrega_referencias_laborales = models.DateField(null=True, blank=True)

    fecha_solicitud_alta = models.DateField(null=True, blank=True)
    fecha_respuesta_alta = models.DateField(null=True, blank=True)
    fecha_ingreso = models.DateField(null=True, blank=True)

    cv = models.FileField(
        upload_to="reclutamiento/cvs/",
        null=True,
        blank=True,
    )

    comentarios = models.TextField(blank=True, default="")

    creado_at = models.DateTimeField(auto_now_add=True)
    actualizado_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rrhh_candidatos_reclutamiento"
        ordering = ["-id_candidato"]
        verbose_name = "Candidato de reclutamiento"
        verbose_name_plural = "Candidatos de reclutamiento"

    def __str__(self):
        return f"{self.nombre} - {self.puesto_postulado}"

    def save(self, *args, **kwargs):
        if self.fecha_ingreso:
            self.estatus = "Contratado"

        super().save(*args, **kwargs)

    # ========== MODELOS PARA PUESTOS Y EVALUACIONES ==========
# Agregado para el módulo de Evaluación de Puestos
# No modifica nada existente

class Puesto(models.Model):
    id_puesto = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=200)
    categoria = models.CharField(max_length=100, blank=True, null=True)
    activo = models.BooleanField(default=True)
    creado_at = models.DateTimeField(auto_now_add=True)
    actualizado_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rrhh_puestos"
        ordering = ["nombre"]
        verbose_name = "Puesto"
        verbose_name_plural = "Puestos"

    def __str__(self):
        return self.nombre


class EvaluacionPuesto(models.Model):
    MOTIVOS = [
        ('A', 'Análisis de desempeño'),
        ('D', 'Desarrollo del trabajador'),
        ('E', 'Evaluación directa'),
    ]

    id_evaluacion = models.AutoField(primary_key=True)
    puesto = models.ForeignKey(Puesto, on_delete=models.CASCADE, related_name='evaluaciones')
    
    # Datos del colaborador evaluado
    colaborador_nombre = models.CharField(max_length=200)
    periodo = models.CharField(max_length=100, blank=True, null=True)
    concesionario = models.CharField(max_length=200, blank=True, null=True)
    antiguedad = models.CharField(max_length=50, blank=True, null=True)
    
    # Datos del evaluador
    evaluador_nombre = models.CharField(max_length=200)
    evaluador_puesto = models.CharField(max_length=200, blank=True, null=True)
    motivo = models.CharField(max_length=1, choices=MOTIVOS, default='A')
    
    # Evaluación
    respuestas = models.JSONField(default=dict)
    calificacion = models.IntegerField()
    comentarios = models.TextField(blank=True, null=True)
    
    fecha = models.DateField(auto_now_add=True)
    creado_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rrhh_evaluaciones_puestos"
        ordering = ["-fecha"]
        verbose_name = "Evaluación de puesto"
        verbose_name_plural = "Evaluaciones de puestos"

    def __str__(self):
        return f"{self.puesto.nombre} - {self.colaborador_nombre} - {self.fecha}"
    
class Colaborador(models.Model):
    id_colaborador = models.AutoField(primary_key=True)

    agencia = models.CharField(max_length=100)
    nombre = models.CharField(max_length=200)
    puesto = models.CharField(max_length=200)

    fecha_alta = models.DateField()

    fecha_baja = models.DateField(
        null=True,
        blank=True
    )

    nss = models.CharField(
        max_length=20,
        blank=True,
        default=""
    )

    curp = models.CharField(
        max_length=18,
        blank=True,
        default=""
    )

    fecha_nacimiento = models.DateField(
        null=True,
        blank=True
    )

    creado_at = models.DateTimeField(auto_now_add=True)
    actualizado_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rrhh_colaboradores"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre