from django.contrib import admin

from .models import TraficoPiso


@admin.register(TraficoPiso)
class TraficoPisoAdmin(admin.ModelAdmin):
    list_display = [
        "id_trafico",
        "agencia",
        "nombre_prospecto",
        "telefono",
        "asesor_ventas",
        "tipo_persona",
        "tiempo_compra",
        "presupuesto_estimado",
        "creado_en",
    ]
    search_fields = [
        "nombre_prospecto",
        "telefono",
        "email",
        "asesor_ventas",
        "agencia",
    ]
    list_filter = [
        "agencia",
        "tipo_persona",
        "deja_auto_cuenta",
        "comprueba_ingresos",
        "creado_en",
    ]
    ordering = ["-id_trafico"]