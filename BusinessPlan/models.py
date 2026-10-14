from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from CrmConformidad.models import Usuario


# Se conserva exclusivamente como respaldo si ya aplicaste la implementación anterior.
# No se consulta desde las nuevas vistas ni se crean negocios predeterminados.
class EstadoBusinessPlan(models.Model):
    negocios = models.JSONField(default=list)
    tableros = models.JSONField(default=dict)
    temas_por_negocio = models.JSONField(default=dict)
    papelera = models.JSONField(default=list)
    revision = models.PositiveIntegerField(default=0)
    actualizado_por = models.CharField(max_length=150, blank=True, default="")
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "business_plan_estado"
        verbose_name = "Estado antiguo de Business Plan (respaldo)"


class Tablero(models.Model):
    nombre = models.CharField(max_length=120)
    propietario = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, db_column="id_propietario",
        related_name="bp_tableros_propios",
    )
    eliminado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bp_tableros"
        constraints = [
            models.UniqueConstraint(
                Lower("nombre"), "propietario",
                condition=Q(eliminado_en__isnull=True),
                name="bp_tablero_prop_nombre_activo_uniq",
            ),
        ]

    def __str__(self):
        return self.nombre


class ColaboradorTablero(models.Model):
    ROLES = [("editor", "Editor"), ("lector", "Lector")]
    ESTADOS = [("pendiente", "Pendiente"), ("aceptada", "Aceptada")]

    tablero = models.ForeignKey(Tablero, on_delete=models.CASCADE, related_name="colaboraciones")
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="bp_tableros_compartidos")
    invitado_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="bp_invitaciones_tablero_enviadas"
    )
    rol = models.CharField(max_length=10, choices=ROLES, default="lector")
    estado = models.CharField(max_length=10, choices=ESTADOS, default="pendiente")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bp_colaboradores_tablero"
        constraints = [models.UniqueConstraint(fields=["tablero", "usuario"], name="bp_col_tab_unique")]


class Tema(models.Model):
    tablero = models.ForeignKey(Tablero, on_delete=models.CASCADE, related_name="temas")
    propietario = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, db_column="id_propietario",
        related_name="bp_temas_propios",
    )
    nombre = models.CharField(max_length=80)
    subtitulo = models.CharField(max_length=220, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bp_temas"
        constraints = [models.UniqueConstraint(Lower("nombre"), "tablero", name="bp_tema_tab_nombre_unique")]

    def __str__(self):
        return f"{self.tablero.nombre}: {self.nombre}"


class ColaboradorTema(models.Model):
    ROLES = ColaboradorTablero.ROLES
    ESTADOS = ColaboradorTablero.ESTADOS

    tema = models.ForeignKey(Tema, on_delete=models.CASCADE, related_name="colaboraciones")
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="bp_temas_compartidos")
    invitado_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="bp_invitaciones_tema_enviadas"
    )
    rol = models.CharField(max_length=10, choices=ROLES, default="lector")
    estado = models.CharField(max_length=10, choices=ESTADOS, default="pendiente")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bp_colaboradores_tema"
        constraints = [models.UniqueConstraint(fields=["tema", "usuario"], name="bp_col_tema_unique")]


class DatosTemaAnual(models.Model):
    tema = models.ForeignKey(Tema, on_delete=models.CASCADE, related_name="periodos")
    anio = models.PositiveSmallIntegerField()
    filas = models.JSONField(default=list)
    columnas = models.JSONField(default=list)
    revision = models.PositiveIntegerField(default=0)
    actualizado_por = models.ForeignKey(
        Usuario, null=True, on_delete=models.SET_NULL,
        related_name="bp_periodos_actualizados",
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bp_datos_tema_anual"
        constraints = [models.UniqueConstraint(fields=["tema", "anio"], name="bp_datos_tema_anio_unique")]
        indexes = [models.Index(fields=["anio"], name="bp_datos_anio_idx")]
