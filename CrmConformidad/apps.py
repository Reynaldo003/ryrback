# CrmConformidad/apps.py
from django.apps import AppConfig


class CrmconformidadConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'CrmConformidad'

    def ready(self):
        # Este import conecta el escuchador automático cuando el servidor enciende
        import CrmConformidad.signals