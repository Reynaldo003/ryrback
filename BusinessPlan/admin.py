#
from django.contrib import admin
from .models import EstadoBusinessPlan


@admin.register(EstadoBusinessPlan)
class EstadoBusinessPlanAdmin(admin.ModelAdmin):
    list_display = ("id", "revision", "actualizado_por", "actualizado_en")
    readonly_fields = ("revision", "actualizado_por", "actualizado_en")

    # Evitamos modificar manualmente los JSON y saltarnos la revisión.
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
