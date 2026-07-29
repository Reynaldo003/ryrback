from django.core.management.base import BaseCommand
from rrhh.models import CategoriaAmbienteLaboral, DominioAmbienteLaboral

DATA = [
    ("Ambiente de trabajo", [
        "Condiciones peligrosas e inseguras",
        "Condiciones deficientes e insalubres",
        "Trabajos peligrosos",
    ]),
    ("Factores propios de la actividad", [
        "Carga de trabajo",
        "Falta de control sobre el trabajo",
    ]),
    ("Organización del tiempo de trabajo", [
        "Jornada de trabajo",
        "Interferencia en la relación trabajo-familia",
    ]),
    ("Liderazgo y relaciones en el trabajo", [
        "Liderazgo",
        "Relaciones en el trabajo",
        "Violencia",
    ]),
]

class Command(BaseCommand):
    help = "Siembra el catálogo de categorías/dominios de Ambiente laboral"

    def handle(self, *args, **kwargs):
        for orden_cat, (nombre_cat, dominios) in enumerate(DATA):
            cat, _ = CategoriaAmbienteLaboral.objects.get_or_create(
                nombre=nombre_cat, defaults={"orden": orden_cat}
            )
            for orden_dom, nombre_dom in enumerate(dominios):
                DominioAmbienteLaboral.objects.get_or_create(
                    categoria=cat, nombre=nombre_dom, defaults={"orden": orden_dom}
                )
        self.stdout.write(self.style.SUCCESS("Catálogo cargado correctamente."))
