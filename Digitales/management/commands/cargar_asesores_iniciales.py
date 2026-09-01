from django.core.management.base import BaseCommand
from django.db import transaction

from Digitales.models import Asesor


def asesor_inicial(
    nombre,
    tipo_asesor,
    agencia="",
    telefono="",
):
    return {
        "nombre": nombre,
        "telefono": telefono,
        "tipo_asesor": tipo_asesor,
        "area": "",
        "agencia": agencia,
        "activo": True,
    }


ASESORES_DIGITALES_INICIALES = [
    asesor_inicial(
        "Lizbeth Cano Clara",
        "Digital",
        "VW Orizaba",
        "522721111244",
    ),
    asesor_inicial(
        "Erendira Santos Coyotzi",
        "Digital",
        "VW Cordoba",
        "522713133332",
    ),
    asesor_inicial(
        "Marelly Tenorio Salinas",
        "Digital",
        "VW Tuxtepec",
    ),
    asesor_inicial(
        "Julio Ramirez Lopez",
        "Digital",
        "VW Tuxtepec",
    ),
    asesor_inicial(
        "Edgar Omar Noguera Solis",
        "Digital",
        "VW Tuxpan",
        "527831263814",
    ),
    asesor_inicial(
        "Dulce Abigail Garcia Olivares",
        "Digital",
        "VW Poza Rica",
        "527821820706",
    ),
    asesor_inicial(
        "Bianca Chavez Alarcon",
        "Digital",
        "VW Cordoba",
        "522712837999",
    ),
    asesor_inicial(
        "Candy Denisse Marquez",
        "Digital",
        "VW Orizaba",
        "522721986539",
    ),
]


ASESORES_PISO_INICIALES = [
    asesor_inicial(
        "Adrian Galvez Roldan",
        "Piso",
        "VW Tuxtepec",
    ),
    asesor_inicial(
        "Aura Marlizeth Fernandez Lopez",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Blanca Patricia Hernandez Hernandez",
        "Piso",
        "VW Tuxpan",
    ),
    asesor_inicial(
        "Carlos Arturo Garces Venegas",
        "Piso",
        "VW Tuxpan",
    ),
    asesor_inicial(
        "Cesar Ivan Salazar Reyes",
        "Piso",
        "VW Poza Rica",
    ),
    asesor_inicial(
        "Cristian Fernando Rivera Godinez",
        "Piso",
    ),
    asesor_inicial(
        "David Uriel Garcia Navarro",
        "Piso",
    ),
    asesor_inicial(
        "Delmar Javier Illescas Dominguez",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Edgar Jesus Gomez Perez",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Elia Ines Arano Reyes",
        "Piso",
        "VW Tuxtepec",
    ),
    asesor_inicial(
        "Estefano Marlom De Azcue Aparicio",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Felix Emmanuel Solis Angeles",
        "Piso",
        "VW Poza Rica",
    ),
    asesor_inicial(
        "Geovani Nava Diaz",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "German Jarith Salazar Miranda",
        "Piso",
        "VW Poza Rica",
    ),
    asesor_inicial(
        "Gustavo Chontal Romero",
        "Piso",
    ),
    asesor_inicial(
        "Hector Rodriguez",
        "Piso",
    ),
    asesor_inicial(
        "Idalmy Jimenez Sanchez",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Irene Del Carmen Guiza Lopez",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Iris Yazmin Gomez Velazquez",
        "Piso",
        "VW Poza Rica",
    ),
    asesor_inicial(
        "Israel Garcia Juarez",
        "Piso",
        "VW Poza Rica",
    ),
    asesor_inicial(
        "Ivan Juarez Ortega",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Javier Perez Meraz",
        "Piso",
        "VW Tuxpan",
    ),
    asesor_inicial(
        "Jessica Olivares Campos",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Jesus Xitlama Gomez",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Jorge Antonio Rodriguez Martinez",
        "Piso",
    ),
    asesor_inicial(
        "Jorge Luis Alamillo Rodriguez",
        "Piso",
        "VW Tuxtepec",
    ),
    asesor_inicial(
        "Jose Alberto Sedas Flores",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Jose Alfredo Barranca Reyes",
        "Piso",
        "VW Tuxtepec",
    ),
    asesor_inicial(
        "Jose De Jesus Garcia Roman",
        "Piso",
        "VW Poza Rica",
    ),
    asesor_inicial(
        "Juan Jesus Marquez Aquino",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Juan Manuel Sobrevilla Vicencio",
        "Piso",
    ),
    asesor_inicial(
        "Luis Alberto Ramirez Santamaria",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Luis Alfonso Coria Marroquin",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Luis Armando Almora Perez",
        "Piso",
        "VW Tuxpan",
    ),
    asesor_inicial(
        "Luis Manuel Alvarez Martinez",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Luis Manuel Hernandez Espejo",
        "Piso",
    ),
    asesor_inicial(
        "Luis Manuel Palomares Olayo",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Mara Erubey Soto Villegas",
        "Piso",
        "VW Tuxpan",
    ),
    asesor_inicial(
        "Marcos Raul Diaz Ramos",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Maria De Guadalupe Vanvollenhoven Diaz",
        "Piso",
    ),
    asesor_inicial(
        "Maria Del Carmen Zavala Velazquez",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Maria Monserrath Zarate Gamboa",
        "Piso",
    ),
    asesor_inicial(
        "Mario Alberto Lopez Ramos",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Marisol Lagunes Gonzalez",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Miguel Capitanachi Paredes",
        "Piso",
        "VW Poza Rica",
    ),
    asesor_inicial(
        "Nallely Hernandez Garcia",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Octavio Bruno Gonzalez",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Olimpia Vazquez Mendez",
        "Piso",
        "VW Poza Rica",
    ),
    asesor_inicial(
        "Omar Villiers Mondragon",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Paul Serrano Vera",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Roberto Ramses Luna Fajardo",
        "Piso",
        "VW Poza Rica",
    ),
    asesor_inicial(
        "Rogelio Vazquez Sanchez",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Ruben Alberto Tosquy Adriano",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Ruben Romero Valdes",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Saja Azzam Mohammad Jamous",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Sandra Luz Prieto Perez",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Sergio Ivan Quintana Martinez",
        "Piso",
        "VW Tuxpan",
    ),
    asesor_inicial(
        "Sergio Rene Delgado Sarmiento",
        "Piso",
        "VW Tuxpan",
    ),
    asesor_inicial(
        "Valeria Zilli Durante",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Vanessa Jimenez Medina",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Veronica Castillo Fuentes",
        "Piso",
        "VW Orizaba",
    ),
    asesor_inicial(
        "Yamil Misael Rodriguez Aguilar",
        "Piso",
        "VW Cordoba",
    ),
    asesor_inicial(
        "Yoseth Ruiz Castellanos",
        "Piso",
        "VW Tuxpan",
    ),
    asesor_inicial(
        "Zeila Navarro Contreras",
        "Piso",
        "VW Tuxtepec",
    ),
]


ASESORES_INICIALES = [
    *ASESORES_DIGITALES_INICIALES,
    *ASESORES_PISO_INICIALES,
]


class Command(BaseCommand):
    help = "Carga inicial del catalogo de asesores del CRM."

    @transaction.atomic
    def handle(self, *args, **options):
        creados = 0
        existentes = 0

        for datos in ASESORES_INICIALES:
            nombre = datos["nombre"].strip()

            asesor_existente = (
                Asesor.objects
                .filter(nombre__iexact=nombre)
                .order_by("id")
                .first()
            )

            if asesor_existente is not None:
                existentes += 1

                self.stdout.write(
                    f"EXISTENTE: {nombre}"
                )

                continue

            Asesor.objects.create(**datos)
            creados += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"CREADO: {nombre}"
                )
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Carga terminada | "
                f"Creados: {creados} | "
                f"Existentes: {existentes}"
            )
        )