#Digitales/apps.py
from django.apps import AppConfig

class DigitalesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Digitales'

    def ready(self):
        from . import signals  # noqa: F401
