from __future__ import annotations

from functools import lru_cache
import json
import re
import unicodedata
from typing import Any, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from openai import OpenAI

from .sett import WHATSAPP_LINES
from citas.models import ClienteComercial, normaliza_tel_mx
from .models import ExpedienteDigital, MensajeWhatsApp
from .contacto import (
    enviar_texto_whatsapp,
    enviar_documento_whatsapp_por_link,
    enviar_imagen_whatsapp_por_link,
    replace_start,
)

CATALOGO_VEHICULOS = {
    "TRANSPORTER COMBI 5 ASIENTOS": {
        "precio_desde": "$783,529 MXN",
        "precio_lista_num": 783529,
        "precios": {"lista": "$783,529 MXN"},
        "pdf_relativo": "fichas/transporter/ficha-tecnica-transporter-pasajeros.pdf",
        "brochure_relativo": "fichas/transporter/brochure-transporter-pasajeros.pdf",
        "imagenes_relativas": ["fichas/transporter/transporter-combi-5-asientos.jpeg"],
        "resumen": (
            "Transporter Combi 5 Asientos es la version mas practica para quien necesita una unidad de trabajo agil, "
            "con espacio para pasajeros y posibilidad de llevar equipo o herramientas sin sacrificar comodidad. "
            "Motor 2.0 TDI Diesel, transmision manual de 6 velocidades."
        ),
        "ficha_tecnica": {
            "version_modelo": "Transporter Combi 2025",
            "configuracion_asientos": "5 asientos",
            "motor": "4 cilindros 2.0 TDI Diesel",
            "potencia": "120 Hp",
            "torque": "360 Nm",
            "transmision": "Manual de 6 velocidades",
            "traccion": "Delantera",
            "combustible": "Diesel",
            "garantia": "Hasta 5 años o 200,000 km",
            "equipamiento_destacado": [
                "Pantalla tactil 13 pulgadas", "Cuadro digital 13.2 pulgadas TFT",
                "App-Connect inalambrico", "Iluminacion interior LED",
            ],
            "seguridad_base": ["Front Assist", "Lane Assist", "ESP", "Light Assist"],
            "enfoque_de_uso": "Cuadrillas, servicios tecnicos, uso mixto",
        },
    },
    "TRANSPORTER COMBI 8 ASIENTOS": {
        "precio_desde": "$742,723 MXN",
        "precio_lista_num": 833203,
        "precios": {"lista": "$833,203 MXN", "contado": "$792,603 MXN", "financiado": "$742,723 MXN"},
        "pdf_relativo": "fichas/transporter/ficha-tecnica-transporter-pasajeros.pdf",
        "brochure_relativo": "fichas/transporter/brochure-transporter-pasajeros.pdf",
        "imagenes_relativas": ["fichas/transporter/transporter-combi-8-asientos.jpeg"],
        "resumen": (
            "Transporter Combi 8 Asientos: motor 2.0 TDI Diesel, transmision automatica 8 velocidades, 150 Hp y 360 Nm. "
            "Ideal para traslados de personal, hoteleria y turismo."
        ),
        "ficha_tecnica": {
            "version_modelo": "Transporte Combi 2025",
            "configuracion_asientos": "8 asientos",
            "motor": "4 cilindros 2.0 TDI Diesel",
            "potencia": "150 Hp",
            "torque": "360 Nm",
            "transmision": "Automatica de 8 velocidades",
            "traccion": "Delantera",
            "combustible": "Diesel",
            "garantia": "Hasta 5 años o 200,000 km",
            "equipamiento_destacado": [
                "Pantalla tactil 13 pulgadas", "6 altavoces",
                "App-Connect inalambrico", "Iluminacion interior LED",
            ],
            "seguridad_base": ["Front Assist", "Lane Assist", "ESP", "Light Assist"],
            "enfoque_de_uso": "Transporte de personal, hoteleria, turismo, traslados privados",
        },
    },
    "TRANSPORTER COMBI 9 ASIENTOS": {
        "precio_desde": "$870,000 MXN",
        "precio_lista_num": 870000,
        "precios": {"lista": "$870,000 MXN"},
        "pdf_relativo": "fichas/transporter/ficha-tecnica-transporter-pasajeros.pdf",
        "brochure_relativo": "fichas/transporter/brochure-transporter-pasajeros.pdf",
        "imagenes_relativas": ["fichas/transporter/transporter-combi-9-asientos.jpeg"],
        "resumen": (
            "Transporter Combi 9 Asientos: motor 2.0 TDI Diesel, automatica 8 velocidades, 150 Hp. "
            "Maxima capacidad de pasajeros en configuracion moderna."
        ),
        "ficha_tecnica": {
            "version_modelo": "Transporter Combi 2025",
            "configuracion_asientos": "9 asientos",
            "motor": "4 cilindros 2.0 TDI Diesel",
            "potencia": "150 Hp",
            "torque": "360 Nm",
            "transmision": "Automatica de 8 velocidades",
            "traccion": "Delantera",
            "combustible": "Diesel",
            "garantia": "Hasta 5 años o 200,000 km",
            "equipamiento_destacado": [
                "Pantalla tactil 13 pulgadas", "6 altavoces",
                "App-Connect inalambrico", "Iluminacion interior LED",
            ],
            "seguridad_base": ["Front Assist", "Lane Assist", "ESP", "Light Assist"],
            "enfoque_de_uso": "Empresas, grupos de trabajo, hoteleria",
        },
    },
    # ── Precios oficiales vw.com.mx mayo 2026 ──────────────────────────────────
    "POLO 2026": {
        "precio_desde": "$339,990 MXN",
        "precio_lista_num": 339990,
        "precios": {"lista": "$339,990 MXN"},
        "pdf_relativo": "fichas/Ficha_Tecnica_polo_2026.pdf",
        "brochure_relativo": "fichas/brochure-polo-2026.pdf",
        "imagenes_relativas": ["fichas/polo-2026.jpeg"],
        "resumen": "Volkswagen Polo 2026 Track. Motor 1.6L MPI 109 Hp, 16.7 km/L combinado, pantalla touch 10 pulgadas, 4 bolsas de aire.",
        "ficha_tecnica": {
            "version_modelo": "Polo 2026 Track",
            "motor": "1.6 L MPI",
            "potencia": "109 Hp",
            "torque": "155 Nm",
            "rendimiento": "16.7 km/L combinado",
            "seguridad_base": ["4 bolsas de aire", "HHC", "Testigo presion neumaticos"],
            "colores": ["Plata Sirius", "Blanco Candy", "Gris Platino", "Negro Ninja"],
            "enfoque_de_uso": "Movilidad urbana, primer auto, uso cotidiano",
        },
    },
    "VIRTUS 2026": {
        "precio_desde": "$351,490 MXN",
        "precio_lista_num": 351490,
        "precios": {
        "trendline_manual": "$351,490 MXN",
        "comfortline": "$423,490 MXN",
        "highline": "$449,490 MXN",
        "lista": "$351,490 MXN (Trendline) / $423,490 MXN (Comfortline) / $449,490 MXN (Highline)",
      },
        "pdf_relativo": "fichas/Ficha_Tecnica_virtus_2026.pdf",
        "brochure_relativo": "fichas/virtus/brochure-virtus-2026.pdf",
        "imagenes_relativas": ["fichas/virtus/virtus-2026.jpeg"],
        "resumen": "Virtus 2026: sedan subcompacto, versiones Trendline/Comfortline/Highline. Motor 1.0L TSI 114 Hp o 1.6L MPI 110 Hp. Cajuela 521 L, garantia 5 anos.",
        "ficha_tecnica": {
            "version_modelo": "Virtus 2026",
            "versiones": ["Trendline", "Comfortline", "Highline"],
            "motores": ["1.0L TSI 114 Hp / 178 Nm", "1.6L MPI 110 Hp / 152 Nm"],
            "transmision": "Manual 5v / Automatica Tiptronic 6v",
            "cajuela": "521 L",
            "garantia": "5 anos o 100,000 km",
            "enfoque_de_uso": "Sedan familiar, uso diario",
        },
    },
    "TERA 2026": {
        "precio_desde": "$387,990 MXN",
        "precio_lista_num": 387990,
        "precios": {
    "trendline": "$387,990 MXN",
    "comfortline": "$$428,990 MXN",
    "highline": "$$467,990 MXN",
    "lista": "$387,990 MXN (Trendline) / $428,990 MXN (Comfortline) / $467,990 MXN (Highline)",
     },
        "pdf_relativo": "fichas/Ficha_Tecnica_tera_2026.pdf",
        "brochure_relativo": "fichas/tera/brochure-tera-2026.pdf",
        "imagenes_relativas": ["fichas/tera/tera-2026.jpeg"],
        "resumen": "Tera 2026: SUV compacto, versiones Trendline/Comfortline/Highline. Motor 1.0L TSI, pantalla 10 pulgadas, faros LED, Keyless Access.",
        "ficha_tecnica": {
            "version_modelo": "Tera 2026",
            "versiones": ["Trendline", "Comfortline", "Highline"],
            "motor": "1.0 L TSI",
            "equipamiento_destacado": ["Pantalla touch 10 pulgadas", "Digital Cockpit", "Climatronic", "Keyless Access", "Faros LED"],
            "seguridad_base": ["ACC", "Lane Assist", "Camara trasera", "Sensores"],
            "enfoque_de_uso": "SUV urbano compacto, familia joven",
        },
    },
    "NUEVO NIVUS 2026": {
        "precio_desde": "$491,190 MXN",
        "precio_lista_num": 491190,
        "precios": {"lista": "$491,190 MXN"},
        "pdf_relativo": "fichas/Ficha_Tecnica_nuevo_nivus_2026.pdf",
        "brochure_relativo": "fichas/nivus/brochure-nivus-2026.pdf",
        "imagenes_relativas": ["fichas/nivus/nivus-2026.jpeg"],
        "resumen": "Nivus 2026 Highline: SUV coupe deportivo, motor 1.0L TSI 114 Hp/200 Nm, pantalla 10 pulgadas, Digital Cockpit, cargador inalambrico.",
        "ficha_tecnica": {
            "version_modelo": "Nuevo Nivus 2026 Highline",
            "motor": "1.0 L TSI",
            "potencia": "114 Hp",
            "torque": "200 Nm",
            "equipamiento_destacado": ["Pantalla 10 pulgadas", "Digital Cockpit", "Cargador inalambrico", "6 bolsas de aire"],
            "seguridad_base": ["ACC", "Lane Assist", "Monitoreo punto ciego", "Travel Assist"],
            "enfoque_de_uso": "SUV coupe urbano, diseno deportivo",
        },
    },
    "JETTA 2026": {
        "precio_desde": "$449,290 MXN",
        "precio_lista_num": 449290,
        "precios": {
    "trendline": "$449,490 MXN",
    "comfortline": "$498,290 MXN",
    "sportline": "$565,690 MXN",
    "lista": "$449,290 MXN (Trendline) / $498,290 MXN (Comfortline) / $565,690 MXN (Sportline)",
     },
        "pdf_relativo": "fichas/Ficha_Tecnica_jetta_2026.pdf",
        "brochure_relativo": "fichas/jetta/brochure-jetta-2026.pdf",
        "imagenes_relativas": ["fichas/jetta/jetta-2026.jpeg"],
        "resumen": "Jetta 2026: Trendline/Comfortline/Sportline. Motor 1.4L Turbo TSI 150 Hp/250 Nm, Tiptronic 8v, pantalla 10 pulgadas, sonido premium.",
        "ficha_tecnica": {
            "version_modelo": "Jetta 2026",
            "versiones": ["Trendline", "Comfortline", "Sportline"],
            "motor": "1.4 L Turbo TSI",
            "potencia": "150 Hp",
            "torque": "250 Nm",
            "transmision": "Tiptronic 8 velocidades",
            "equipamiento_destacado": ["Pantalla 10 pulgadas", "Cargador inalambrico", "Climatronic 2 zonas", "Sistema sonido premium"],
            "seguridad_base": ["6 bolsas de aire", "ACC", "Lane Assist", "Camara trasera"],
            "enfoque_de_uso": "Sedan premium, ejecutivo, familia",
        },
    },
    "GLI 2026": {
        "precio_desde": "$691,190 MXN",
        "precio_lista_num": 691190,
        "precios": {"lista": "$691,190 MXN"},
        "pdf_relativo": "fichas/Ficha_Tecnica_gli_2026.pdf",
        "brochure_relativo": "fichas/gli/brochure-gli-2026.pdf",
        "imagenes_relativas": ["fichas/gli/gli-2026.jpeg"],
        "resumen": "GLI 2026: sedan deportivo, motor 2.0L TSI 230 Hp/350 Nm, rines 18 pulgadas, escape doble cromo, pantalla 10 pulgadas.",
        "ficha_tecnica": {
            "version_modelo": "GLI 2026",
            "motor": "2.0 L TSI",
            "potencia": "230 Hp",
            "torque": "350 Nm",
            "equipamiento_destacado": ["Rines 18 pulgadas", "Escape doble deportivo", "Digital Cockpit", "Monitor de potencia"],
            "seguridad_base": ["6 bolsas de aire", "ACC", "Lane Assist"],
            "enfoque_de_uso": "Sedan deportivo, manejo apasionado",
        },
    },
    "GTI 2026": {
        "precio_desde": "$857,990 MXN",
        "precio_lista_num": 857990,
        "precios": {"lista": "$857,990 MXN"},
        "pdf_relativo": "fichas/Ficha_Tecnica_gti_2026.pdf",
        "brochure_relativo": "fichas/gti/brochure-gti-2026.pdf",
        "imagenes_relativas": ["fichas/gti/gti-2026.jpeg"],
        "resumen": "GTI 2026: hot hatch icónico, motor 2.0L TSI 261 Hp/370 Nm, DSG 7, faros LED Matrix, pantalla 12.9 pulgadas, Harman/Kardon.",
        "ficha_tecnica": {
            "version_modelo": "GTI 2026",
            "motor": "2.0 L TSI",
            "potencia": "261 Hp",
            "torque": "370 Nm",
            "transmision": "DSG 7 Shift by wire",
            "equipamiento_destacado": ["Pantalla 12.9 pulgadas", "Harman/Kardon subwoofer", "Asientos calefaccion y ventilacion", "Iluminacion ambiental 30 colores"],
            "seguridad_base": ["7 bolsas de aire", "ACC", "Lane Assist", "Monitoreo punto ciego"],
            "enfoque_de_uso": "Hot hatch, manejo deportivo extremo",
        },
    },
    "SAVEIRO 2026": {
        "precio_desde": "$342,490 MXN",
        "precio_lista_num": 342490,
        "precios": {"lista": "$342,490 MXN (Robust) / $432,990 MXN (Extreme)"},
        "pdf_relativo": "fichas/Ficha_Tecnica_saveiro_2026.pdf",
        "brochure_relativo": "fichas/saveiro/brochure-saveiro-2026.pdf",
        "imagenes_relativas": ["fichas/saveiro/saveiro-2026.jpeg"],
        "resumen": "Saveiro 2026: Robust (cabina sencilla, desde $342,490) y Extreme (cabina doble, desde $432,990). Motor 1.6L 109 Hp, carga util hasta 667 kg, bedliner, pantalla 9 pulgadas.",
        "ficha_tecnica": {
            "version_modelo": "Saveiro 2026",
            "versiones": {"Robust": {"cabina": "Sencilla", "precio_lista": "$342,490 MXN", "carga_util": "667 kg"}, "Extreme": {"cabina": "Doble", "precio_lista": "$432,990 MXN", "carga_util": "622 kg"}},
            "motor": "1.6 L",
            "potencia": "109 Hp",
            "infotainment_comun": ["Pantalla touch 9 pulgadas", "App-Connect"],
            "enfoque_de_uso": "Trabajo, carga ligera, negocio, uso rudo",
        },
    },
    "TAIGUN 2026": {
        "precio_desde": "$462,690 MXN",
        "precio_lista_num": 462690,
       "precios": {
        "comfortline_tsi": "$462,690 MXN",
        "highline_tsi": "$491,690 MXN",
        "lista": "$462,690 MXN (Comfortline TSI) / $491,690 MXN (Highline TSI)",
         },
        "pdf_relativo": "fichas/Ficha_Tecnica_taigun_2026.pdf",
        "brochure_relativo": "fichas/taigun/brochure-taigun-2026.pdf",
        "imagenes_relativas": ["fichas/taigun/taigun-2026.jpeg"],
        "resumen": "Taigun 2026: Comfortline TSI y Highline TSI. Motor 1.0L TSI 114 Hp, Tiptronic 6v, pantalla 10 pulgadas, Keyless Access, 5 estrellas Latin NCAP.",
        "ficha_tecnica": {
            "version_modelo": "Taigun 2026",
            "versiones": ["Comfortline TSI", "Highline TSI"],
            "motor": "1.0 L TSI",
            "potencia": "114 Hp",
            "transmision": "Tiptronic 6 velocidades",
            "seguridad_base": ["Camara trasera", "ESC", "ACC", "5 estrellas Latin NCAP"],
            "enfoque_de_uso": "SUV subcompacto, ciudad, familia pequena",
        },
    },
    "TAOS 2026": {
        "precio_desde": "$502,390 MXN",
        "precio_lista_num": 502390,
        "precios": {
    "trendline": "$502,390 MXN",
    "comfortline": "$554,990 MXN",
    "highline": "$616,190 MXN",
    "lista": "$502,390MXN (Trendline) / $554,990 MXN (Comfortline) / $616,190 MXN (Highline)",
},
        "pdf_relativo": "fichas/Ficha_Tecnica_taos_2026.pdf",
        "brochure_relativo": "fichas/taos/brochure-taos-2026.pdf",
        "imagenes_relativas": ["fichas/taos/taos-2026.jpeg"],
        "resumen": "Taos 2026: Trendline/Comfortline/Highline. Motor 1.4L TSI 150 Hp/250 Nm, Tiptronic 8v, pantalla 10 pulgadas semiflotante.",
        "ficha_tecnica": {
            "version_modelo": "Taos 2026",
            "versiones": ["Trendline", "Comfortline", "Highline"],
            "motor": "1.4 L TSI",
            "potencia": "150 Hp",
            "torque": "250 Nm",
            "transmision": "Tiptronic 8 velocidades",
            "seguridad_base": ["Lane Assist", "Monitoreo punto ciego", "ACC", "Camara trasera"],
            "enfoque_de_uso": "SUV compacto familiar, versatilidad",
        },
    },
    "TIGUAN 2026": {
        "precio_desde": "$613,190 MXN",
        "precio_lista_num": 613190,
        "precios": {
    "trendline": "$613,190 MXN",
    "comfortline": "$694,290 MXN",
    "r_line": "$795,790 MXN",
    "lista": "$613,190 MXN (Trendline) / $694,290 MXN (Comfortline) / $795,790 MXN (R-Line)",
},
        "pdf_relativo": "fichas/Ficha_Tecnica_tiguan_2026.pdf",
        "brochure_relativo": "fichas/tiguan/brochure-tiguan-2026.pdf",
        "imagenes_relativas": ["fichas/tiguan/tiguan-2026.jpeg"],
        "resumen": "Tiguan 2026: Trendline/Comfortline/R-Line. Motor 1.4L TSI 150 Hp, DSG 7, pantalla flotante hasta 15 pulgadas, asistente de voz, Digital Cockpit.",
        "ficha_tecnica": {
            "version_modelo": "Tiguan 2026",
            "versiones": ["Trendline", "Comfortline", "R-Line"],
            "motor": "1.4 L TSI",
            "potencia": "150 Hp",
            "torque": "250 Nm",
            "transmision": "DSG 7 velocidades",
            "equipamiento_destacado": ["Pantalla flotante 12.9-15 pulgadas", "Digital Cockpit", "ACC", "Asistente de voz"],
            "seguridad_base": ["ACC", "Lane Assist", "Detector punto ciego", "Travel Assist"],
            "enfoque_de_uso": "SUV mediano premium, familia, tecnologia avanzada",
        },
    },
    "TERAMONT 2026": {
        "precio_desde": "$901,190 MXN",
        "precio_lista_num": 901190,
        "precios": {
    "trendline": "$901,190 MXN",
    "peak_edition": "$1,082,190 MXN",
    "highline": "$1,152,190 MXN",
    "lista": "$901,190 MXN (Trendline) / $1,082,190 MXN (Peak Edition) / $1,152,190 MXN (Highline)",
},
        "pdf_relativo": "fichas/Ficha_Tecnica_teramont_2026.pdf",
        "brochure_relativo": "fichas/teramont/brochure-teramont-2026.pdf",
        "imagenes_relativas": ["fichas/teramont/teramont-2026.jpeg"],
        "resumen": "Teramont 2026: Trendline/Peak Edition/Highline. Motor 2.0L TSI 269 Hp, pantalla 12 pulgadas, 4MOTION en Peak y Highline.",
        "ficha_tecnica": {
            "version_modelo": "Teramont 2026",
            "versiones": ["Trendline", "Peak Edition", "Highline"],
            "motor": "2.0 L TSI",
            "potencia": "269 Hp",
            "enfoque_de_uso": "SUV grande premium, familia numerosa, viajes largos",
        },
    },
    "CROSS SPORT 2026": {
        "precio_desde": "$1,175,190 MXN",
        "precio_lista_num": 1175190,
        "precios": {"lista": "$1,175,190 MXN"},
        "pdf_relativo": "fichas/Ficha_Tecnica_cross_sport_2026.pdf",
        "brochure_relativo": "fichas/cross-sport/brochure-cross-sport-2026.pdf",
        "imagenes_relativas": ["fichas/cross-sport/cross-sport-2026.jpeg"],
        "resumen": "Cross Sport 2026 R-Line: SUV coupe premium, motor 2.0L TSI 269 Hp, 4MOTION, rines 21 pulgadas, Harman/Kardon 11 bocinas, head-up display.",
        "ficha_tecnica": {
            "version_modelo": "Cross Sport 2026 R-Line",
            "motor": "2.0 L TSI",
            "potencia": "269 Hp",
            "traccion": "4MOTION",
            "equipamiento_destacado": ["Rines 21 pulgadas", "Harman/Kardon 11 bocinas", "Head-up display", "Asientos masaje"],
            "enfoque_de_uso": "SUV coupe premium, aventura con lujo, traccion total",
        },
    },
}


# Sucursales y geolocalización por LADA 
SUCURSALES_VW: list[dict] = [
     {
        "nombre": "Agencia VW Cordoba",
        "ciudad": "cordoba, Veracruz",
        "direccion": "Av. No. 1, C. 26, 94550 Córdoba, Ver.",
        "telefono": "271-313-3332",
        "horario": "Lun-Sáb 9:00-19:00",
        "ladas_cercanas": ["271"], #271=Córdoba
        "google_maps": "https://maps.app.goo.gl/7zy5EiGe1N1wXzuC9",
    },
    {
        "nombre": "Agencia VW Orizaba",
        "ciudad": "Orizaba, Veracruz",
        "direccion": "Blvd. Sur 3, Orizaba, Ver.",
        "telefono": "272-111-1244",
        "horario": "Lun-Sáb 9:00-19:00",
        "ladas_cercanas": ["272"],  # 272=Orizaba
        "google_maps": "https://maps.app.goo.gl/7zy5EiGe1N1wXzuC9",
    },
    {
        "nombre": "Agencia VW Tuxtepec",
        "ciudad": "Tuxtepec, Oaxaca",
        "direccion": "Miguel Alemán Km 13, El Diamante, 68300 San Juan Bautista Tuxtepec, Oax.",
        "telefono": "287-123-2641",
        "horario": "Lun-Sáb 9:00-19:00",
        "ladas_cercanas": ["287"],  # 287=Tuxtepec
        "google_maps": "https://maps.app.goo.gl/7zy5EiGe1N1wXzuC9",
    },
    {
        "nombre": "Agencia VW Poza Rica",
        "ciudad": "Poza Rica, Veracruz",
        "direccion": "Carr. Poza Rica - Cazones 3702, La Rueda, 93306 Poza Rica de Hidalgo, Ver.",
        "telefono": "782-182-0706",
        "horario": "Lun-Sáb 9:00-19:00",
        "ladas_cercanas": ["782"],  # 782=Poza Rica
        "google_maps": "https://maps.app.goo.gl/9KNBE2ied2EL8S6y7",
    },
    {
        "nombre": "Agencia VW Tuxpan",
        "ciudad": "Tuxpan, Veracruz",
        "direccion": "Blvd. Independencia 144, Burocratica, 92870 Túxpam de Rodríguez Cano, Ver.",
        "telefono": "783-126-3814",
        "horario": "Lun-Sáb 9:00-19:00",
        "ladas_cercanas": ["783"],  # 783=Tuxpan
        "google_maps": "https://maps.app.goo.gl/fjP5JD6n3hqKiCsp9",
    },
]


def _lada_de_telefono(telefono: str) -> str:
    """Extrae la LADA (3 dígitos) de un número mexicano normalizado (10 dígitos sin +52)."""
    tel = re.sub(r"\D", "", telefono or "")
    if tel.startswith("52") and len(tel) == 12:
        tel = tel[2:]
    if len(tel) == 10:
        return tel[:3]
    return ""


def _sucursal_mas_cercana(telefono: str) -> dict:
    """Devuelve la sucursal más cercana según la LADA del teléfono del cliente."""
    lada = _lada_de_telefono(telefono)
    if lada:
        for sucursal in SUCURSALES_VW:
            if lada in sucursal.get("ladas_cercanas", []):
                return sucursal
    return SUCURSALES_VW[0] if SUCURSALES_VW else {}


def _texto_ubicacion(telefono: str) -> str:
    s = _sucursal_mas_cercana(telefono)
    if not s:
        return "Por favor contáctanos directamente para indicarte nuestra ubicación."
    lineas = [
        f"📍 *Ubicación de tu Agencia VW más cercana:*",
        f"",
        f"🏢 *Agencia:* {s['nombre']}",
        f"🏙️ *Ciudad:* {s['ciudad']}",
        f"🗺️ *Dirección:* {s['direccion']}",
        f"📞 *Teléfono:* {s['telefono']}",
        f"🕐 *Horario:* {s['horario']}",
    ]
    if s.get("google_maps"):
        lineas += [
            f"",
            f"🔗 *Cómo llegar:*",
            f"{s['google_maps']}",
        ]
    lineas += [
        f"",
        f"¡Te esperamos! 🚗",
    ]
    return "\n".join(lineas)


def _enganche_referencial(version: str) -> Optional[str]:
    """Calcula el enganche referencial (~20%) a partir del precio de lista oficial."""
    data = CATALOGO_VEHICULOS.get(version, {})
    precio_num = data.get("precio_lista_num")
    if not precio_num:
        return None
    enganche = round(precio_num * 0.20 / 1000) * 1000
    return f"${enganche:,} MXN aprox. (20% referencial)"



COMPARACION_DESEMPENO: dict[str, dict] = {
    "GTI 2026":                      {"hp": 261, "nm": 370, "motor": "2.0L TSI", "transmision": "DSG 7"},
    "GLI 2026":                      {"hp": 230, "nm": 350, "motor": "2.0L TSI", "transmision": "Automatica"},
    "CROSS SPORT 2026":              {"hp": 269, "nm": 350, "motor": "2.0L TSI", "transmision": "Automatica"},
    "TERAMONT 2026":                 {"hp": 269, "nm": 350, "motor": "2.0L TSI", "transmision": "Automatica"},
    "JETTA 2026":                    {"hp": 150, "nm": 250, "motor": "1.4L TSI", "transmision": "Tiptronic 8"},
    "TIGUAN 2026":                   {"hp": 150, "nm": 250, "motor": "1.4L TSI", "transmision": "DSG 7"},
    "TAOS 2026":                     {"hp": 150, "nm": 250, "motor": "1.4L TSI", "transmision": "Tiptronic 8"},
    "NUEVO NIVUS 2026":              {"hp": 114, "nm": 200, "motor": "1.0L TSI", "transmision": "Automatica"},
    "TAIGUN 2026":                   {"hp": 114, "nm": 200, "motor": "1.0L TSI", "transmision": "Tiptronic 6"},
    "TERA 2026":                     {"hp": 114, "nm": 200, "motor": "1.0L TSI", "transmision": "Automatica"},
    "VIRTUS 2026":                   {"hp": 114, "nm": 178, "motor": "1.0L TSI", "transmision": "Tiptronic 6"},
    "POLO 2026":                     {"hp": 109, "nm": 155, "motor": "1.6L MPI", "transmision": "Manual"},
    "SAVEIRO 2026":                  {"hp": 109, "nm": 145, "motor": "1.6L",     "transmision": "Manual"},
    "TRANSPORTER COMBI 5 ASIENTOS": {"hp": 120, "nm": 360, "motor": "2.0L TDI Diesel", "transmision": "Manual 6"},
    "TRANSPORTER COMBI 8 ASIENTOS": {"hp": 150, "nm": 360, "motor": "2.0L TDI Diesel", "transmision": "Automatica 8"},
    "TRANSPORTER COMBI 9 ASIENTOS": {"hp": 150, "nm": 360, "motor": "2.0L TDI Diesel", "transmision": "Automatica 8"},
}

# Perfilado / filtrado de leads
ENGANCHE_MINIMO_CALIFICADO = 69_000   # MXN

ETAPA_PERFILADO = {
    "sin_iniciar":    0,
    "pedir_nombre":   1,
    "pedir_enganche": 2,
    "pedir_buro":     3,
    "completado":     4,
}

SALUDO_BASE = (
    "¡Hola! Soy Vagen, tu asistente de Agencia Volkswagen Córdoba 🚗\n\n"
    "Tenemos toda la gama VW: Polo, Virtus, Tera, Nivus, Jetta, GLI, GTI, "
    "Saveiro, Taigun, Taos, Tiguan, Teramont, Cross Sport y Transporter Combi.\n\n"
    "Para orientarte mejor, ¿me puedes decir tu nombre?"
)

RESPUESTA_MEDIA = (
    "Por ahora te puedo apoyar por texto con informacion de todos nuestros modelos, "
    "ademas de precio, imagenes y ficha tecnica en PDF."
)

RESPUESTA_FALLBACK = (
    "Con gusto te ayudo. Tenemos Polo, Virtus, Tera, Nivus, Jetta, GLI, GTI, "
    "Saveiro, Taigun, Taos, Tiguan, Teramont, Cross Sport y Transporter Combi. "
    "Cuentame que modelo te interesa."
)

RESPUESTA_CONFIRMAR_ASESOR = (
    "Gracias. En un momento un asesor se comunicara contigo para darte atencion personalizada y seguimiento."
)

# Mensaje para autos no disponibles como nuevos
RESPUESTA_AUTO_NO_DISPONIBLE = (
    "El auto que comenta no está disponible para su comercialización como auto nuevo en nuestra agencia. "
    "¿Gusta saber si lo tenemos en nuestro inventario como auto seminuevo?"
)

STOPWORDS_NOMBRE = {
    "SI", "SIP", "OK", "OKEY", "VA", "CLARO", "EN", "PDF", "MANDAMELA", "MANDAME",
    "COMPARTELA", "COMPARTEME", "COMPARTEMELA", "FICHA", "TECNICA", "PRECIO",
    "QUIERO", "NECESITO", "PASAME", "PASAMELA", "LISTO", "PERFECTO", "SALE",
    "SERVICIO", "PUBLICO", "TRANSPORTE", "LINEA", "IMAGEN", "IMAGENES", "FOTO", "FOTOS",
    "FINANCIAMIENTO", "CREDITO", "MENSUALIDADES", "COTIZACION", "5", "8", "9",
}

PALABRAS_COTIZACION = {
    "COTIZACION", "COTIZAR", "COTIZA", "PROPUESTA", "PROPUESTA FORMAL",
    "CORRIDA", "CORRIDA FINANCIERA", "MENSUALIDADES", "MENSUALIDAD",
    "ENGANCHE", "PLAN DE PAGOS", "FINANCIAMIENTO", "CREDITO", "LEASING",
    "ARRENDAMIENTO", "NUMEROS", "PAGOS",
}

PALABRAS_COMPRA = {
    "COMPRAR", "ADQUIRIR", "APARTAR", "QUIERO LA UNIDAD", "QUIERO COMPRAR",
    "ME INTERESA COMPRAR", "QUIERO AVANZAR", "QUIERO QUE ME CONTACTEN",
    "QUIERO HABLAR CON VENTAS", "ATENCION PERSONALIZADA",
}

ACCIONES_OFRECIDAS_VALIDAS = {
    "saludo_inicial", "pedir_nombre", "pedir_necesidad", "compartir_precio",
    "compartir_pdf", "confirmar_canalizacion", "preguntar_tipo_cliente",
    "preguntar_forma_pago", "continuar_contexto", "pedir_enganche",
    "pedir_buro", "lead_calificado", "ninguna",
}

PALABRAS_CATALOGO_ANTERIOR = {
    "CRAFTER", "CRAFTER ELEMENTAL", "CRAFTER INSPIRE", "CRAFTER ELITE", "CRAFTER URBAN",
    "ELEMENTAL", "INSPIRE", "ELITE", "URBAN",
}

_ALIASES_VERSION: dict[str, list[str]] = {
    "TRANSPORTER COMBI 5 ASIENTOS": [
        "TRANSPORTER COMBI 5 ASIENTOS", "TRANSPORTER 5 ASIENTOS", "COMBI 5 ASIENTOS",
        "VERSION 5 ASIENTOS", "5 ASIENTOS", "CINCO ASIENTOS", "LA DE 5", "EL DE 5",
    ],
    "TRANSPORTER COMBI 8 ASIENTOS": [
        "TRANSPORTER COMBI 8 ASIENTOS", "TRANSPORTER 8 ASIENTOS", "COMBI 8 ASIENTOS",
        "VERSION 8 ASIENTOS", "8 ASIENTOS", "OCHO ASIENTOS", "LA DE 8", "EL DE 8",
    ],
    "TRANSPORTER COMBI 9 ASIENTOS": [
        "TRANSPORTER COMBI 9 ASIENTOS", "TRANSPORTER 9 ASIENTOS", "COMBI 9 ASIENTOS",
        "VERSION 9 ASIENTOS", "9 ASIENTOS", "NUEVE ASIENTOS", "LA DE 9", "EL DE 9",
    ],
    "POLO 2026":         ["POLO 2026", "POLO TRACK", "EL POLO", "POLO"],
    "VIRTUS 2026":       ["VIRTUS 2026", "EL VIRTUS", "VIRTUS"],
    "TERA 2026":         ["TERA 2026", "EL TERA", "TERA"],
    "NUEVO NIVUS 2026":  ["NUEVO NIVUS 2026", "NIVUS 2026", "EL NIVUS", "NIVUS"],
    "JETTA 2026":        ["JETTA 2026", "EL JETTA", "JETTA"],
    "GLI 2026":          ["GLI 2026", "EL GLI", "GLI"],
    "GTI 2026":          ["GTI 2026", "EL GTI", "GTI"],
    "SAVEIRO 2026":      ["SAVEIRO 2026", "EL SAVEIRO", "SAVEIRO", "SAVEIRO ROBUST", "SAVEIRO EXTREME"],
    "TAIGUN 2026":       ["TAIGUN 2026", "EL TAIGUN", "TAIGUN"],
    "TAOS 2026":         ["TAOS 2026", "EL TAOS", "TAOS"],
    "TIGUAN 2026":       ["TIGUAN 2026", "EL TIGUAN", "TIGUAN"],
    "TERAMONT 2026":     ["TERAMONT 2026", "EL TERAMONT", "TERAMONT", "TERAMONT PEAK", "TERAMONT HIGHLINE"],
    "CROSS SPORT 2026":  ["CROSS SPORT 2026", "CROSS SPORT", "EL CROSS SPORT", "CROSSSPORT"],
}


# Utilidades de texto
def _strip_accents(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )


def _normalizar_texto(texto: str) -> str:
    texto = _strip_accents(texto or "").upper().strip()
    texto = re.sub(r"[^A-Z0-9$@._ -]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto


def _media_base_url() -> str:
    base = getattr(settings, "PUBLIC_API_BASE_URL", "").rstrip("/")
    media_url = getattr(settings, "MEDIA_URL", "/media/")
    return f"{base}{media_url}"


def _build_media_url(relativo: str) -> str:
    return f"{_media_base_url()}{relativo}".replace(" ", "%20")


def _build_pdf_url(pdf_relativo: str) -> str:
    return _build_media_url(pdf_relativo)


def _limitar_texto(texto: str, max_len: int = 900) -> str:
    texto = re.sub(r"\n{3,}", "\n\n", (texto or "").strip())
    if len(texto) <= max_len:
        return texto
    return texto[: max_len - 3].rstrip() + "..."


def _es_email(texto: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", (texto or "").strip()))


def _limpiar_nombre_candidato(texto: str) -> str:
    texto = re.sub(r"[^a-zA-ZáéíóúÁÉÍÓÚüÜñÑ ]+", " ", texto or "").strip()
    return re.sub(r"\s+", " ", texto)


def _parece_nombre_solo(texto: str) -> bool:
    texto = (texto or "").strip()
    if not texto or _es_email(texto):
        return False
    texto_limpio = _limpiar_nombre_candidato(texto)
    if not texto_limpio:
        return False
    palabras = [p.upper() for p in texto_limpio.split() if p.strip()]
    if not palabras or len(palabras) > 3:
        return False
    if any(p in STOPWORDS_NOMBRE for p in palabras):
        return False
    if any(len(p) < 2 for p in palabras):
        return False
    return True


def _extraer_nombre_basico(profile_name: str, texto: str) -> str:
    pn = (profile_name or "").strip()
    if pn and not _es_email(pn) and _parece_nombre_solo(pn):
        return _limpiar_nombre_candidato(pn)
    texto = (texto or "").strip()
    for patron in [
        r"\bmi nombre es\s+([a-zA-ZáéíóúÁÉÍÓÚüÜñÑ ]{2,80})",
        r"\bme llamo\s+([a-zA-ZáéíóúÁÉÍÓÚüÜñÑ ]{2,80})",
        r"\bsoy\s+([a-zA-ZáéíóúÁÉÍÓÚüÜñÑ ]{2,80})",
    ]:
        m = re.search(patron, texto, flags=re.IGNORECASE)
        if m:
            nombre = _limpiar_nombre_candidato(re.sub(r"\s+", " ", m.group(1)).strip(" .,-"))
            if nombre and not _es_email(nombre):
                return nombre
    if _parece_nombre_solo(texto):
        return _limpiar_nombre_candidato(texto)
    return ""


def _json_seguro(texto: str) -> dict[str, Any]:
    """Parsea JSON robusto: maneja prefijos, markdown, trailing commas y JSON truncado."""
    texto = (texto or "").strip()
    if not texto:
        return {}
    try:
        return json.loads(texto)
    except Exception:
        pass
    texto_limpio = re.sub(r"```(?:json)?\s*", "", texto).strip()
    texto_limpio = re.sub(r"```\s*$", "", texto_limpio).strip()
    try:
        return json.loads(texto_limpio)
    except Exception:
        pass
    m = re.search(r"\{.*\}", texto_limpio, flags=re.DOTALL)
    if m:
        fragmento = m.group(0)
        try:
            return json.loads(fragmento)
        except Exception:
            pass
        fragmento_rep = re.sub(r",\s*([}\]])", r"\1", fragmento)
        try:
            return json.loads(fragmento_rep)
        except Exception:
            pass
        try:
            cierre = "]" * max(fragmento_rep.count("[") - fragmento_rep.count("]"), 0)
            cierre += "}" * max(fragmento_rep.count("{") - fragmento_rep.count("}"), 0)
            return json.loads(fragmento_rep + cierre)
        except Exception:
            pass
    return {}


def _normalizar_version_catalogo(version: Optional[str]) -> Optional[str]:
    v = (version or "").strip()
    return v if v in CATALOGO_VEHICULOS else None


def _texto_refiere_catalogo_anterior(texto: str) -> bool:
    t = _normalizar_texto(texto)
    return "CRAFTER" in t or any(f in t for f in PALABRAS_CATALOGO_ANTERIOR)


def _raw_refiere_catalogo_anterior(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    candidatos = [
        raw.get("version_contexto"), raw.get("filename"),
        raw.get("document_link"), raw.get("media_link"), raw.get("body"),
    ]
    d = raw.get("decision") or {}
    if isinstance(d, dict):
        candidatos += [d.get("selected_version"), d.get("reply_text")]
    return any(_texto_refiere_catalogo_anterior(str(c or "")) for c in candidatos)


def _mensaje_de_historial_vigente(*, body: str, raw: Any = None) -> bool:
    if _texto_refiere_catalogo_anterior(body or ""):
        return False
    if _raw_refiere_catalogo_anterior(raw):
        return False
    return True


def _limpiar_auto_interes_invalido(expediente: ExpedienteDigital) -> Optional[str]:
    ai = (expediente.auto_interes or "").strip()
    if not ai:
        return None
    if ai in CATALOGO_VEHICULOS:
        return ai
    expediente.auto_interes = ""
    expediente.save(update_fields=["auto_interes", "actualizado"])
    return None


def _buscar_version_en_texto(texto: str) -> Optional[str]:
    t = _normalizar_texto(texto)
    for version, aliases in _ALIASES_VERSION.items():
        for alias in aliases:
            if _normalizar_texto(alias) in t:
                return version
    return None


def _texto_precios_version(version: str) -> str:
    if version not in CATALOGO_VEHICULOS:
        return ""
    data = CATALOGO_VEHICULOS[version]
    precios = data.get("precios") or {}
    lineas = []
    if precios.get("lista"):
        lineas.append(f"- Lista: {precios['lista']}")
    if precios.get("contado"):
        lineas.append(f"- Contado: {precios['contado']}")
    if precios.get("financiado"):
        lineas.append(f"- Financiado desde: {precios['financiado']}")
    if not lineas and data.get("precio_desde"):
        lineas.append(f"- Desde: {data['precio_desde']}")
    if not lineas:
        lineas.append("- Precio disponible con asesor")
    enganche = _enganche_referencial(version)
    if enganche:
        lineas.append(f"- Enganche referencial: {enganche}")
    return "\n".join(lineas)


# ficha técnica estructurada
def _resumen_ficha_texto(version: str) -> str:
    if version not in CATALOGO_VEHICULOS:
        return ""
    data = CATALOGO_VEHICULOS[version]
    ficha = data.get("ficha_tecnica") or {}
    lineas = [f"🚗 *{version.title()}*", "", data.get("resumen", ""), ""]

    campos = [
        ("⚙️ Motor",       "motor"),
        ("💪 Potencia",    "potencia"),
        ("🔩 Torque",      "torque"),
        ("🔄 Transmisión", "transmision"),
        ("🛞 Tracción",    "traccion"),
        ("⛽ Combustible", "combustible"),
        ("🛡️ Garantía",   "garantia"),
        ("💺 Asientos",    "configuracion_asientos"),
    ]
    ficha_lineas = []
    for etiqueta, clave in campos:
        if ficha.get(clave):
            ficha_lineas.append(f"  • {etiqueta}: {ficha[clave]}")
    if isinstance(ficha.get("versiones"), list):
        ficha_lineas.append(f"  • 📋 Versiones: {', '.join(ficha['versiones'])}")
    if ficha_lineas:
        lineas.append("📋 *Especificaciones:*")
        lineas += ficha_lineas
        lineas.append("")

    destacados = (ficha.get("equipamiento_destacado") or [])[:5]
    if destacados:
        lineas.append("✨ *Equipamiento destacado:*")
        lineas += [f"  • {i}" for i in destacados]
        lineas.append("")

    seguridad = (ficha.get("seguridad_base") or [])[:4]
    if seguridad:
        lineas.append("🔒 *Seguridad:*")
        lineas += [f"  • {i}" for i in seguridad]
        lineas.append("")

    if ficha.get("enfoque_de_uso"):
        lineas.append(f"🎯 *Ideal para:* {ficha['enfoque_de_uso']}")
        lineas.append("")

    precios = _texto_precios_version(version)
    if precios:
        lineas.append("💰 *Precios:*")
        lineas.append(precios)
        lineas.append("")

    enganche = _enganche_referencial(version)
    if enganche:
        lineas.append(f"📊 *Enganche referencial:* {enganche}")
        lineas.append("_(puede variar según perfil del cliente)_")
        lineas.append("")

    lineas.append("📄 Te comparto también la ficha técnica en PDF.")
    return _limitar_texto("\n".join(lineas).strip())


def _respuesta_precio_version(version: str) -> str:
    return _limitar_texto(
        f"Precios de {version.title()}:\n\n{_texto_precios_version(version)}\n\n"
        "Si gustas, tambien te comparto la ficha tecnica en PDF."
    )


def _imagenes_de_version(version: str) -> list[str]:
    if version not in CATALOGO_VEHICULOS:
        return []
    return list(CATALOGO_VEHICULOS[version].get("imagenes_relativas") or [])


def _catalogo_para_prompt() -> str:
    catalogo_reducido = {}
    for v, d in CATALOGO_VEHICULOS.items():
        entry = {
            "precio_desde": d.get("precio_desde", ""),
            "precio_lista_num": d.get("precio_lista_num"),
            "precios": d.get("precios", {}),
            "resumen": d.get("resumen", ""),
            "ficha_tecnica": d.get("ficha_tecnica", {}),
        }
        enganche = _enganche_referencial(v)
        if enganche:
            entry["enganche_referencial_20pct"] = enganche
        catalogo_reducido[v] = entry
    return json.dumps(catalogo_reducido, ensure_ascii=False, indent=2)


def _detectar_intencion_minima(texto_usuario: str) -> dict[str, bool]:
    t = _normalizar_texto(texto_usuario)
    return {
        "pregunta_precio": any(k in t for k in [
            "PRECIO", "PRECIOS", "COSTO", "COSTOS", "CUANTO CUESTA", "CUANTO VALE",
            "CUANTO SALE", "CUANTO ESTA", "EN CUANTO", "A CUANTO",
            "VALE", "CUESTA", "SALE", "$", "MXN", "PESOS", "DESDE", "MONTO",
            "VERSION", "VERSIONES", "VERSIÓN", "TRIMS", "TRIM", "CUAL TIENE", "QUE VERSIONES",
        ]),
        "pregunta_pdf": any(k in t for k in [
            "PDF", "FICHA", "FICHA TECNICA", "ESPECIFICACIONES", "SPECS",
            "CATALOGO", "DETALLES", "BROCHURE", "INFO", "INFORMACION",
            "DATOS", "CARACTERISTICAS", "QUE TRAE", "QUE TIENE", "COMO ES",
            "CUENTAME", "DIME MAS",
        ]),
        "pregunta_imagenes": any(k in t for k in [
            "IMAGEN", "IMAGENES", "FOTO", "FOTOS", "FOTOGRAFIA",
            "PIC", "PICS", "VER", "COMO SE VE", "MUESTRAME",
        ]),
        "cotizacion_personalizada": any(k in t for k in PALABRAS_COTIZACION),
        "intencion_compra": any(k in t for k in PALABRAS_COMPRA),
        "pregunta_desempeno": any(k in t for k in [
            "RAPIDO", "MAS RAPIDO", "VELOZ", "POTENTE", "MAS POTENTE", "MAS HP",
            "CABALLOS", "HP", "TORQUE", "CUAL ES MEJOR", "COMPARAR",
            "DIFERENCIA", "VS", "VERSUS", "ENTRE EL", "ENTRE LA",
        ]),
        "pregunta_catalogo": any(k in t for k in [
            "QUE MODELOS", "CUALES TIENES", "CUALES SON", "QUE TIENEN", "CATALOGO",
            "QUE AUTOS", "QUE CARROS", "QUE VEHICULOS", "OPCIONES TIENES",
            "TIENEN", "MANEJAN", "VENDEN",
        ]),
        "pregunta_arrendamiento": any(k in t for k in [
            "ARRENDAMIENTO", "ARRENDAR", "LEASING", "RENTA", "RENTA LARGA",
        ]),
        #señal de ubicación ────────────────────────────────────
        "pregunta_ubicacion": any(k in t for k in [
            "UBICACION", "DONDE ESTAN", "DONDE QUEDAN", "DONDE SE ENCUENTRAN",
            "DIRECCION", "COMO LLEGAR", "MAPA", "MAPS", "AGENCIA", "SUCURSAL",
            "DONDE PUEDO IR", "EN PERSONA", "VISITAR", "DONDE ES",
        ]),
    }

# Perfilado de leads
_NUMEROS_LETRAS_MONTO: dict[str, int] = {
    "DIEZ": 10, "ONCE": 11, "DOCE": 12, "TRECE": 13, "CATORCE": 14, "QUINCE": 15,
    "VEINTE": 20, "TREINTA": 30, "CUARENTA": 40, "CINCUENTA": 50,
    "SESENTA": 60, "SETENTA": 70, "OCHENTA": 80, "NOVENTA": 90,
    "CIEN": 100, "CIENTO": 100, "CIENTO CINCUENTA": 150, "DOSCIENTOS": 200,
    "TRESCIENTOS": 300, "CUATROCIENTOS": 400, "QUINIENTOS": 500,
}

def _extraer_monto_pesos(texto: str) -> Optional[int]:
    """Extrae monto en pesos. Soporta digitos, sufijos K/MIL y numeros en letras."""
    if not texto:
        return None
    t = _normalizar_texto(texto)
    t = re.sub(r"[$,]", "", t)
    m = re.search(r"(\d[\d\s\.]*)(\s*(?:MIL|K)\b)?", t)
    if m:
        try:
            num = int(float(re.sub(r"[\s\.]", "", m.group(1))))
            if (m.group(2) or "").strip() in ("MIL", "K"):
                num *= 1000
            elif num < 1000 and any(k in t for k in ["MIL", "K", "PESOS", "MXN"]):
                num *= 1000
            if num > 0:
                return num
        except Exception:
            pass
    for palabra, valor in sorted(_NUMEROS_LETRAS_MONTO.items(), key=lambda x: -len(x[0])):
        if palabra in t and "MIL" in t:
            return valor * 1000
    return None


def _evaluar_buro(texto: str) -> str:
    t = _normalizar_texto(texto)
    if any(k in t for k in ["BUENO", "BUEN BURO", "BUEN HISTORIAL", "EXCELENTE", "MUY BIEN", "LIMPIO"]):
        return "bueno"
    if any(k in t for k in ["REGULAR", "MAS O MENOS", "MEDIO", "NO TAN BUENO"]):
        return "regular"
    if any(k in t for k in ["INICIANDO", "INICIO", "SIN HISTORIAL", "NO TENGO", "NUEVO", "NULO", "NUNCA"]):
        return "iniciando"
    return "desconocido"


def _lead_es_calificado(enganche: Optional[int], buro: str) -> bool:
    return (enganche is not None) and (enganche >= ENGANCHE_MINIMO_CALIFICADO) and (buro != "iniciando")


def _obtener_etapa_perfilado(expediente: ExpedienteDigital) -> int:
    pauta = expediente.pauta or ""
    for nombre, numero in sorted(ETAPA_PERFILADO.items(), key=lambda x: -x[1]):
        if f"etapa_perfilado:{nombre}" in pauta:
            return numero
    return ETAPA_PERFILADO["sin_iniciar"]


def _leer_dato_pauta(pauta: str, clave: str) -> str:
    m = re.search(rf"{re.escape(clave)}:([^\n]+)", pauta or "")
    return m.group(1).strip() if m else ""


def _actualizar_pauta(pauta: str, clave: str, valor: str) -> str:
    nueva = f"{clave}:{valor}"
    if re.search(rf"{re.escape(clave)}:[^\n]*", pauta or ""):
        return re.sub(rf"{re.escape(clave)}:[^\n]*", nueva, pauta)
    return (pauta.strip() + "\n" + nueva).strip()


def _determinar_accion_ofrecida(
    *, reply_text: str, send_pdf: bool, handoff_advisor: bool,
    selected_version: Optional[str], texto_usuario: str,
) -> str:
    if handoff_advisor:
        return "confirmar_canalizacion"
    if send_pdf and selected_version:
        return "compartir_pdf"
    rn = _normalizar_texto(reply_text)
    if "TU NOMBRE" in rn or "COMO TE LLAMAS" in rn:
        return "pedir_nombre"
    if any(k in rn for k in ["PARA QUE USO", "QUE USO LE DARAS"]):
        return "pedir_necesidad"
    return "continuar_contexto" if selected_version else "ninguna"


@lru_cache(maxsize=1)
def _get_openai_client() -> OpenAI:
    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY")
    return OpenAI(api_key=api_key, timeout=25.0, max_retries=2)

# Motor de decisión principal (IA)
def _decision_conversacional_ia(
    *,
    telefono: str,
    nombre_cliente: str,
    texto_usuario: str,
    auto_interes_actual: Optional[str],
    ultimo_mensaje_saliente: str,
    historial_reciente: list[dict[str, str]],
    accion_ofrecida_previa: Optional[str],
    etapa_perfilado: int,
    enganche_registrado: Optional[int],
    buro_registrado: str,
    es_primer_mensaje: bool,
) -> dict[str, Any]:
    auto_interes_actual = _normalizar_version_catalogo(auto_interes_actual)
    client = _get_openai_client()

    versiones_validas = sorted(CATALOGO_VEHICULOS.keys())
    versiones_str = "\n".join(f"- {v}" for v in versiones_validas)

    # ANTI-LOOP: contar intentos consecutivos sin avance 
    def _contar_intentos_sin_avance(historial: list[dict], pregunta_clave: str) -> int:
        count = 0
        for msg in reversed(historial):
            if msg.get("role") == "assistant":
                if pregunta_clave.upper() in (msg.get("content") or "").upper():
                    count += 1
                else:
                    break
            elif msg.get("role") == "user":
                break
        return count

    intentos_enganche = _contar_intentos_sin_avance(historial_reciente, "enganche")
    intentos_buro     = _contar_intentos_sin_avance(historial_reciente, "buró")

    enganches_info = {v: _enganche_referencial(v) for v in versiones_validas}
    from datetime import date as _date
    _hoy = _date.today()
    _meses_es = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
                 7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
    _ultimo_dia = [31,28,31,30,31,30,31,31,30,31,30,31][_hoy.month - 1]
    _vigencia = f"al {_ultimo_dia} de {_meses_es[_hoy.month]} de {_hoy.year}"

    contexto = {
        "telefono": telefono,
        "nombre_cliente": nombre_cliente,
        "mensaje_usuario": texto_usuario,
        "ultimo_mensaje_saliente": ultimo_mensaje_saliente,
        "auto_interes_actual": auto_interes_actual,
        "historial_reciente": historial_reciente,
        "accion_ofrecida_previa": accion_ofrecida_previa,
        "es_primer_mensaje": es_primer_mensaje,
        "perfilado": {
            "etapa_actual": etapa_perfilado,
            "etapa_nombres": ETAPA_PERFILADO,
            "enganche_registrado": enganche_registrado,
            "buro_registrado": buro_registrado,
            "enganche_minimo_calificado": ENGANCHE_MINIMO_CALIFICADO,
        },
        "anti_loop": {
            "intentos_pregunta_enganche_sin_respuesta": intentos_enganche,
            "intentos_pregunta_buro_sin_respuesta": intentos_buro,
            "regla": "Si intentos >= 2 para una pregunta, NO repetirla en este turno.",
        },
        "senales_minimas": _detectar_intencion_minima(texto_usuario),
        "catalogo": json.loads(_catalogo_para_prompt()),
        "enganches_referenciales_20pct": enganches_info,
        "desempeno_modelos": COMPARACION_DESEMPENO,
        "ubicacion_sucursal": _sucursal_mas_cercana(telefono),
        "regla_contexto": {
            "ignorar_catalogo_anterior": True,
            "catalogo_anterior": sorted(PALABRAS_CATALOGO_ANTERIOR),
            "catalogo_actual": versiones_validas,
        },
    }

    instrucciones = f"""
Eres Vagen, asistente virtual comercial por WhatsApp de Agencia Volkswagen Córdoba.
Tu objetivo es atender con calidez, informar con precisión y canalizar leads calificados con asesores.

═══ CATÁLOGO ACTUAL ═══════════════════════════════════════════════════════════
{versiones_str}

═══ REGLA CRÍTICA — VEHÍCULOS FUERA DE CATÁLOGO ══════════════════════════════
Si el cliente pregunta por cualquier auto que NO esté en el catálogo actual (ejemplos: Crafter, T-Cross,
Golf estándar, Amarok, ID.4, Caravelle, Beetle, Tiguan Allspace, u otro modelo no listado):
• reply_text DEBE incluir EXACTAMENTE: "El auto que comenta no está disponible para su comercialización
  como auto nuevo en nuestra agencia."
• Luego preguntar: "¿Gusta saber si lo tenemos en nuestro inventario como auto seminuevo?"
• selected_version = null

═══ PRECIOS OFICIALES — FUENTE: vw.com.mx ════════════════════════════════════
Los precios de lista en el catálogo son los precios oficiales de vw.com.mx.
Úsalos siempre. NO inventes ni modifiques precios.
SIEMPRE que cites un precio, agrega al final de la respuesta:
"💡 Precios vigentes {_vigencia}. Pueden cambiar sin previo aviso."

═══ ENGANCHE REFERENCIAL ═════════════════════════════════════════════════════
El enganche es aproximadamente el 20% del precio de lista (ver campo enganche_referencial_20pct).
IMPORTANTE: Es solo referencial; el monto real depende del perfil del cliente, historial crediticio
y condiciones de la agencia. Menciona siempre "aproximado" o "referencial" al citarlo.
Cuando el cliente pregunte por enganche o mensualidad, comparte el referencial e invita al asesor
para una cotización personalizada.

═══ FINANCIAMIENTO Y ARRENDAMIENTO ═══════════════════════════════════════════
Volkswagen ofrece dos esquemas principales:
1. CRÉDITO / FINANCIAMIENTO: el cliente adquiere el vehículo a plazos y al terminar es suyo.
2. ARRENDAMIENTO (LEASING): el cliente paga una renta mensual por el uso del vehículo,
   con opción de compra al final. Es ideal para empresas o personas que prefieren pagos menores
   y flexibilidad.
Cuando el cliente pregunte por mensualidades, pagos o financiamiento, menciona SIEMPRE ambas opciones
(crédito y arrendamiento) e invita a hablar con un asesor para una cotización personalizada según su perfil.

═══ AUTONOMÍA DE LA IA — RESPONDE SIEMPRE ════════════════════════════════════
Tienes TOTAL libertad para responder cualquier pregunta técnica, de comparación, estilo de vida,
uso, rendimiento, equipamiento, colores, garantías, etc. Nunca digas "no puedo responder eso".
Si la información está en el catálogo o en tu conocimiento de VW, respóndela.
Solo canaliza al asesor cuando: el cliente quiera una cotización personalizada formal,
quiera comprar/apartar, o el perfilado esté completo.

═══ UBICACIÓN Y HORARIOS ════════════════════════════════════════════════════
Cuando el cliente pregunte por ubicación, dirección o cómo llegar a la agencia:
- Usa EXACTAMENTE los datos del campo "ubicacion_sucursal" del contexto.
- NO inventes direcciones, teléfonos ni links.
- Muestra: nombre de la agencia, ciudad, dirección, teléfono, horario y link de Google Maps.

Horarios oficiales (NUNCA uses otros):
- Ventas: Lun-Sáb 9:00 am - 6:00 pm
- Servicio: Lun-Sáb 8:00 am - 6:00 pm
Si preguntan por horario de servicio, cita SOLO el de servicio.
Si preguntan por horario de la agencia o de ventas, cita el de ventas.

═══ SALUDO INICIAL ════════════════════════════════════════════════════════════
Cuando es_primer_mensaje = true:
• Saluda calurosamente, preséntate como Vagen de Agencia Volkswagen Córdoba.
• Menciona brevemente la gama de modelos.
• Pregunta el nombre del cliente.
• Aplica aunque el primer mensaje sea "Hola", "Info", "Precio", etc.

Cuando hay historial Y auto_interes_actual definido Y es_primer_mensaje = false:
• Saluda recordando el interés: "¡Hola de nuevo {{nombre}}! ¿Sigues interesado en el {{modelo}}?"

═══ FLUJO DE PERFILADO — 4 ETAPAS ═══════════════════════════════════════════
Etapa 0/1 → pedir_nombre: Espera que el cliente diga su nombre.
  - Si responde otra cosa: PRIMERO responde su pregunta brevemente, LUEGO pide el nombre.

Etapa 2 → pedir_enganche:
  - "¡Mucho gusto {{nombre}}! Para orientarte mejor, ¿cuánto tienes contemplado para el enganche
    o qué mensualidad mensual te gustaría lograr? También tenemos esquemas de arrendamiento."
  - Si no responde: atiende su pregunta y luego insiste.
  - Al captar monto → detected_profile.enganche_monto = entero → nueva_etapa_perfilado = 3.

Etapa 3 → pedir_buro:
  - "Perfecto. ¿Cómo te encuentras en buró de crédito? (bueno, regular o iniciando historial)"
  - Al captar → detected_profile.buro_estado → nueva_etapa_perfilado = 4.
  - Si enganche >= 69000 y buro != "iniciando" → lead_calificado, handoff_advisor = true.
  - Si no califica → confirmar_canalizacion, handoff_advisor = true.

Etapa 4 (completado): responde con total libertad.

═══ PREGUNTAS DE DESEMPEÑO ═══════════════════════════════════════════════════
SIEMPRE responde. Usa desempeno_modelos del contexto.
- "¿Cuál es el más rápido/potente?" → compara HP, da respuesta clara.
- "GTI vs GLI" → compara directamente.

═══ COMPARACIONES ENTRE MODELOS ══════════════════════════════════════════════
Cuando comparan dos modelos: diferencias clave, recomendación según perfil, ofrece PDFs de ambos.

═══ CATÁLOGO POR SEGMENTO ════════════════════════════════════════════════════
- SUVs compactos: Tera, Taigun, Nivus, Taos
- SUVs medianos/grandes: Tiguan, Teramont, Cross Sport
- Sedanes: Polo, Virtus, Jetta, GLI, GTI
- Comerciales: Saveiro, Transporter Combi (5, 8 y 9 asientos)

═══ RECOMENDACIONES POR PERFIL ═══════════════════════════════════════════════
- Cuadrillas/herramientas → Transporter Combi 5 o Saveiro
- Transporte personal/hotelería → Transporter Combi 8 o 9
- Auto compacto económico → Polo o Virtus
- Sedán ejecutivo → Jetta, GLI o GTI
- SUV compacto → Taigun, Taos, Tera o Nivus
- SUV mediano premium → Tiguan
- SUV grande/lujo → Teramont o Cross Sport

═══ MEDIA ═══════════════════════════════════════════════════════════════════
- send_pdf = true SIEMPRE que compartas ficha técnica o especificaciones de un modelo, automáticamente, sin que el cliente lo pida.
- send_images = true SOLO si el cliente pidió imágenes explícitamente y hay versión clara.

═══ PRECIOS — REGLA CRÍTICA ══════════════════════════════════════════════════
Cada versión tiene su propio precio de lista en el catálogo. NUNCA uses el precio
de una versión para responder sobre otra versión distinta.
Antes de citar cualquier precio, verifica que el campo precio_lista_num del
catálogo corresponda EXACTAMENTE a la versión que el cliente preguntó.
Si el cliente pregunta por un trim específico (Trendline, Comfortline, Highline)
que no está como clave separada, indica el precio base de la línea y aclara:
"El precio puede variar según versión; un asesor te da el precio exacto."

REGLA AUTOMÁTICA DE PRECIO — SIEMPRE aplica sin que el cliente lo pida:
- Si el cliente pregunta qué versiones tiene un modelo (ej. "¿qué versiones tiene
  el Jetta?", "¿cuáles son los Taos?"), incluye el precio de lista en la respuesta.
- Si menciona un modelo por primera vez o pregunta cómo es, incluye su precio desde.
- Si pregunta por un trim específico (Sportline, Robust, Extreme, etc.), da el precio
  base de esa línea y aclara que puede variar; invita a un asesor para el precio final.

═══ ANTI-LOOP — REGLA CRÍTICA ════════════════════════════════════════════════
NUNCA repitas exactamente el mismo mensaje que ya enviaste (revisa
ultimo_mensaje_saliente e historial_reciente antes de responder).
Si el cliente ya no respondió a una pregunta de perfilado (enganche o buró) y
vuelve a preguntar algo de producto, PRIMERO responde su pregunta de producto
y AL FINAL agrega la pregunta de perfilado en UNA sola línea corta.
El campo anti_loop.intentos_pregunta_enganche_sin_respuesta indica cuántas veces
consecutivas preguntaste por enganche sin que el cliente respondiera. Si es >= 2,
NO preguntes enganche en este turno.
Lo mismo para anti_loop.intentos_pregunta_buro_sin_respuesta >= 2.

═══ ESTILO ═══════════════════════════════════════════════════════════════════
- Español natural, cálido, comercial. Sin markdown complejo.
- Usa el nombre del cliente siempre que lo tengas.
- No pongas URLs en reply_text.
- Máximo 700 caracteres en reply_text. MENOS ES MÁS.
- Sé directo y concreto. Evita frases largas, introducciones innecesarias
  y explicaciones de más. La gente lee en WhatsApp, no en una web.
- Nunca uses más de 2 frases seguidas sin un salto de línea o bullet.
- Cuando compartas detalles técnicos de un auto, SIEMPRE usa listas con bullet •,
  una línea por dato, con etiqueta y valor. Ejemplo:
  • ⚙️ Motor: 1.4L TSI
  • 💪 Potencia: 150 Hp
  • 🔄 Transmisión: Tiptronic 8v
- Nunca en párrafo corrido cuando sea información técnica.
- Las respuestas de catálogo, comparación o recomendación: máximo 6 bullets.
  Si hay más datos, di "¿Quieres que te cuente más de algún punto?"

═══ SALIDA — JSON ESTRICTO ═══════════════════════════════════════════════════
{{
  "reply_text": "texto listo para WhatsApp",
  "selected_version": "nombre exacto del catálogo o null",
  "send_pdf": false,
  "send_images": false,
  "handoff_advisor": false,
  "accion_ofrecida": "saludo_inicial|pedir_nombre|pedir_necesidad|compartir_precio|compartir_pdf|confirmar_canalizacion|preguntar_tipo_cliente|preguntar_forma_pago|continuar_contexto|pedir_enganche|pedir_buro|lead_calificado|ninguna",
  "nueva_etapa_perfilado": 0,
  "detected_profile": {{
    "nombre_detectado": "",
    "enganche_monto": null,
    "buro_estado": "",
    "tipo_cliente": "persona_fisica|persona_moral|desconocido",
    "forma_pago": "credito|arrendamiento|contado|desconocido",
    "uso_detectado": "",
    "interes_principal": "precio|ficha|comparacion|recomendacion|especificaciones|asesoria|cotizacion|compra|general"
  }},
  "reasoning_tags": ["etiquetas", "breves"]
}}

RESTRICCIONES ABSOLUTAS:
- selected_version: nombre EXACTO del catálogo o null.
- send_pdf / send_images no pueden ser true si selected_version es null.
- handoff_advisor = true cuando pidan cotización formal, quieran comprar, o perfilado completo.
- nueva_etapa_perfilado: entero 0-4. Solo avanzar o mantener, nunca retroceder.
- detected_profile.enganche_monto: entero en pesos si mencionó monto, null si no.
- detected_profile.buro_estado: "bueno", "regular", "iniciando" o "" si no mencionó.
- Si el vehículo no está en catálogo: selected_version = null, reply_text con mensaje de no disponible + oferta seminuevo.
"""

    try:
        respuesta = client.responses.create(
            model="gpt-4.1",
            instructions=instrucciones,
            input=json.dumps(contexto, ensure_ascii=False),
        )
        salida = _json_seguro(getattr(respuesta, "output_text", "") or "")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error OpenAI: {e}", exc_info=True)
        return {}

    salida.setdefault("reply_text", "")
    salida.setdefault("selected_version", None)
    salida.setdefault("send_pdf", False)
    salida.setdefault("send_images", False)
    salida.setdefault("handoff_advisor", False)
    salida.setdefault("accion_ofrecida", "ninguna")
    salida.setdefault("nueva_etapa_perfilado", etapa_perfilado)
    salida.setdefault("detected_profile", {})
    salida.setdefault("reasoning_tags", [])

    version = _normalizar_version_catalogo(salida.get("selected_version"))
    salida["selected_version"] = version

    accion = (salida.get("accion_ofrecida") or "ninguna").strip()
    salida["accion_ofrecida"] = accion if accion in ACCIONES_OFRECIDAS_VALIDAS else "ninguna"

    salida["send_pdf"] = bool(salida.get("send_pdf")) and bool(version)
    salida["send_images"] = bool(salida.get("send_images")) and bool(version)
    salida["handoff_advisor"] = bool(salida.get("handoff_advisor"))
    salida["reply_text"] = _limitar_texto(salida.get("reply_text") or "")

    try:
        nueva_etapa = max(etapa_perfilado, min(4, int(salida.get("nueva_etapa_perfilado", etapa_perfilado))))
    except (TypeError, ValueError):
        nueva_etapa = etapa_perfilado
    salida["nueva_etapa_perfilado"] = nueva_etapa

    dp = salida.get("detected_profile") or {}
    if dp.get("enganche_monto") is not None:
        try:
            dp["enganche_monto"] = int(dp["enganche_monto"])
        except (TypeError, ValueError):
            dp["enganche_monto"] = None
    salida["detected_profile"] = dp

    if salida["handoff_advisor"]:
        salida["send_pdf"] = False
        salida["send_images"] = False
        if salida["accion_ofrecida"] not in ("lead_calificado", "confirmar_canalizacion"):
            salida["accion_ofrecida"] = "confirmar_canalizacion"

    return salida


# Historial y persistencia
def _obtener_ultimo_mensaje_saliente(cliente: ClienteComercial, numero_asesor: str) -> str:
    mensajes = (
        MensajeWhatsApp.objects
        .filter(cliente=cliente, numero_asesor=numero_asesor, direction="out")
        .order_by("-id").only("body", "raw")
    )[:25]
    for m in mensajes:
        body = (m.body or "").strip()
        if _mensaje_de_historial_vigente(body=body, raw=m.raw):
            return body
    return ""


def _obtener_ultima_accion_ofrecida(cliente: ClienteComercial, numero_asesor: str) -> Optional[str]:
    mensajes = (
        MensajeWhatsApp.objects
        .filter(cliente=cliente, numero_asesor=numero_asesor, direction="out")
        .order_by("-id").only("body", "raw")
    )[:25]
    for m in mensajes:
        raw = m.raw or {}
        body = (m.body or "").strip()
        if not _mensaje_de_historial_vigente(body=body, raw=raw):
            continue
        accion = (
            raw.get("conversation_meta", {}).get("accion_ofrecida")
            or raw.get("accion_ofrecida") or ""
        ).strip()
        if accion in ACCIONES_OFRECIDAS_VALIDAS:
            return accion
    return None


def _contar_mensajes_entrantes(cliente: ClienteComercial, numero_asesor: str) -> int:
    return MensajeWhatsApp.objects.filter(
        cliente=cliente, numero_asesor=numero_asesor, direction="in"
    ).count()


def _serializar_historial(cliente: ClienteComercial, numero_asesor: str, limite: int = 12) -> list[dict[str, str]]:
    mensajes = (
        MensajeWhatsApp.objects
        .filter(cliente=cliente, numero_asesor=numero_asesor)
        .order_by("-id").only("direction", "body", "raw")
    )[: max(limite * 4, 24)]
    historial = []
    for m in reversed(list(mensajes)):
        body = (m.body or "").strip()
        if not body:
            continue
        if not _mensaje_de_historial_vigente(body=body, raw=m.raw):
            continue
        historial.append({"role": "assistant" if m.direction == "out" else "user", "content": body})
    return historial[-limite:]


def _guardar_salida(
    *, telefono: str, numero_asesor: str, cliente: ClienteComercial,
    texto: str, wa_message_id: str = "", raw: Optional[dict] = None,
    status_msg: str = "accepted",
) -> MensajeWhatsApp:
    return MensajeWhatsApp.objects.create(
        telefono=telefono, numero_asesor=numero_asesor, cliente=cliente,
        direction="out", body=texto, wa_message_id=wa_message_id or "",
        status=status_msg, raw=raw or {},
    )


# Cliente / expediente

@transaction.atomic
def _get_or_create_cliente_y_expediente(
    *, telefono: str, numero_asesor: str,
    profile_name: str = "", texto_entrante: str = "",
) -> tuple[ClienteComercial, ExpedienteDigital]:
    telefono = normaliza_tel_mx(telefono)
    numero_asesor = normaliza_tel_mx(numero_asesor)
    if not telefono:
        raise ValueError("Telefono invalido")

    nombre_detectado = _extraer_nombre_basico(profile_name, texto_entrante)
    cliente, _ = ClienteComercial.objects.get_or_create(
        telefono=telefono, defaults={"nombre": nombre_detectado},
    )
    if nombre_detectado and not (cliente.nombre or "").strip():
        cliente.nombre = nombre_detectado
        cliente.save(update_fields=["nombre", "actualizado_en"])

    cfg_linea = WHATSAPP_LINES.get(numero_asesor, {})
    agencia_linea = (cfg_linea.get("agencia") or "").strip()
    business_linea = (cfg_linea.get("business") or "Comerciales").strip()
    asesor_digital_linea = (cfg_linea.get("asesor_digital") or "").strip()

    expediente, _ = ExpedienteDigital.objects.get_or_create(
        cliente=cliente,
        defaults={"agencia": agencia_linea, "business": business_linea,
                  "asesor_digital": asesor_digital_linea,
                  "canal_contacto": "WhatsApp", "estado": "Contactado"},
    )

    cambios = []
    for campo, valor in [
        ("agencia", agencia_linea), ("business", business_linea),
        ("asesor_digital", asesor_digital_linea),
    ]:
        if valor and getattr(expediente, campo) != valor:
            setattr(expediente, campo, valor); cambios.append(campo)
    if expediente.canal_contacto != "WhatsApp":
        expediente.canal_contacto = "WhatsApp"; cambios.append("canal_contacto")
    if not (expediente.estado or "").strip():
        expediente.estado = "Contactado"; cambios.append("estado")

    version_detectada = _buscar_version_en_texto(texto_entrante)
    if version_detectada and expediente.auto_interes != version_detectada:
        expediente.auto_interes = version_detectada; cambios.append("auto_interes")
    if expediente.auto_interes and expediente.auto_interes not in CATALOGO_VEHICULOS:
        expediente.auto_interes = ""; cambios.append("auto_interes")

    now = timezone.now()
    if not expediente.primer_contacto_at:
        expediente.primer_contacto_at = now; cambios.append("primer_contacto_at")
    expediente.ultimo_contacto_at = now; cambios.append("ultimo_contacto_at")

    if cambios:
        cambios.append("actualizado")
        expediente.save(update_fields=list(dict.fromkeys(cambios)))

    return cliente, expediente


def _guardar_datos_detectados_en_cliente_y_expediente(
    *, cliente: ClienteComercial, expediente: ExpedienteDigital,
    profile_name: str, detected_profile: dict[str, Any],
    version_detectada: Optional[str], nueva_etapa_perfilado: int,
) -> None:
    cambios_cliente: list[str] = []
    cambios_expediente: list[str] = []

    nombre_detectado = (
        (detected_profile or {}).get("nombre_detectado")
        or _extraer_nombre_basico(profile_name, "") or ""
    ).strip()
    if nombre_detectado and not (cliente.nombre or "").strip():
        cliente.nombre = nombre_detectado
        cambios_cliente.extend(["nombre", "actualizado_en"])

    version_detectada = _normalizar_version_catalogo(version_detectada)
    if version_detectada and expediente.auto_interes != version_detectada:
        expediente.auto_interes = version_detectada; cambios_expediente.append("auto_interes")

    pauta = expediente.pauta or ""

    # Guardar etapa
    etapa_str = {v: k for k, v in ETAPA_PERFILADO.items()}.get(nueva_etapa_perfilado, "sin_iniciar")
    pauta = _actualizar_pauta(pauta, "etapa_perfilado", etapa_str)

    # Guardar enganche si se capturó
    eng = (detected_profile or {}).get("enganche_monto")
    if eng is not None:
        try:
            pauta = _actualizar_pauta(pauta, "enganche_monto", str(int(eng)))
        except (TypeError, ValueError):
            pass

    # Guardar buró si se capturó
    buro = ((detected_profile or {}).get("buro_estado") or "").strip()
    if buro:
        pauta = _actualizar_pauta(pauta, "buro_estado", buro)

    # Guardar uso detectado
    uso = ((detected_profile or {}).get("uso_detectado") or "").strip()
    if uso:
        uso_n = f"Uso detectado: {uso}"
        if uso_n not in pauta:
            pauta = (pauta.strip() + "\n" + uso_n).strip()

    if pauta != (expediente.pauta or ""):
        expediente.pauta = pauta[:2000]
        cambios_expediente.append("pauta")

    # Evaluar calificacion de lead
    eng_str = _leer_dato_pauta(pauta, "enganche_monto")
    buro_str = _leer_dato_pauta(pauta, "buro_estado")
    try:
        eng_val: Optional[int] = int(eng_str) if eng_str else None
    except ValueError:
        eng_val = None

    if _lead_es_calificado(eng_val, buro_str) and expediente.estado not in ("Lead Calificado", "Seguimiento"):
        expediente.estado = "Lead Calificado"; cambios_expediente.append("estado")

    if cambios_cliente:
        cliente.save(update_fields=list(dict.fromkeys(cambios_cliente)))
    if cambios_expediente:
        cambios_expediente.append("actualizado")
        expediente.save(update_fields=list(dict.fromkeys(cambios_expediente)))


def _ya_se_respondio_a_entrada(numero_asesor: str, wa_message_id_entrante: str) -> bool:
    numero_asesor = normaliza_tel_mx(numero_asesor)
    wa_message_id_entrante = (wa_message_id_entrante or "").strip()
    if not numero_asesor or len(wa_message_id_entrante) < 5:
        return False
    return MensajeWhatsApp.objects.filter(
        numero_asesor=numero_asesor, direction="out",
        raw__reply_to=wa_message_id_entrante,
    ).exists()


# Fallback si OpenAI falla
def _fallback_respuesta(
    *, texto_usuario: str, profile_name: str, version_contexto: Optional[str],
    es_primer_mensaje: bool, etapa_perfilado: int, nombre_cliente: str,
    telefono: str = "",
) -> dict[str, Any]:
    version_contexto = _normalizar_version_catalogo(version_contexto)
    senales = _detectar_intencion_minima(texto_usuario)
    version_directa = _normalizar_version_catalogo(_buscar_version_en_texto(texto_usuario))
    version_final = version_directa or version_contexto
    nombre = nombre_cliente or _extraer_nombre_basico(profile_name, texto_usuario)

    if es_primer_mensaje or not (texto_usuario or "").strip():
        return {
            "reply_text": SALUDO_BASE, "selected_version": None,
            "send_pdf": False, "send_images": False, "handoff_advisor": False,
            "detected_profile": {"nombre_detectado": nombre},
            "reasoning_tags": ["fallback_saludo_inicial"],
            "accion_ofrecida": "pedir_nombre",
            "nueva_etapa_perfilado": ETAPA_PERFILADO["pedir_nombre"],
        }

    #ubicación en fallback
    if senales.get("pregunta_ubicacion"):
        return {
            "reply_text": _texto_ubicacion(telefono),
            "selected_version": version_final,
            "send_pdf": False, "send_images": False, "handoff_advisor": False,
            "detected_profile": {}, "reasoning_tags": ["fallback_ubicacion"],
            "accion_ofrecida": "ninguna", "nueva_etapa_perfilado": etapa_perfilado,
        }

    if etapa_perfilado == ETAPA_PERFILADO["pedir_enganche"]:
        pfx = f"Hola {nombre}! " if nombre else ""
        return {
            "reply_text": (
                f"{pfx}Para orientarte mejor, ¿cuánto tienes para el enganche o qué mensualidad buscas? "
                "También contamos con planes de arrendamiento. ¿Me lo puedes decir?"
            ),
            "selected_version": version_final, "send_pdf": False, "send_images": False,
            "handoff_advisor": False, "detected_profile": {},
            "reasoning_tags": ["fallback_insistir_enganche"],
            "accion_ofrecida": "pedir_enganche",
            "nueva_etapa_perfilado": ETAPA_PERFILADO["pedir_enganche"],
        }

    if etapa_perfilado == ETAPA_PERFILADO["pedir_buro"]:
        pfx = f"Hola {nombre}! " if nombre else ""
        return {
            "reply_text": f"{pfx}Solo me falta saber cómo estás en buró de crédito (bueno, regular o iniciando) para enviarte una propuesta real.",
            "selected_version": version_final, "send_pdf": False, "send_images": False,
            "handoff_advisor": False, "detected_profile": {},
            "reasoning_tags": ["fallback_insistir_buro"],
            "accion_ofrecida": "pedir_buro",
            "nueva_etapa_perfilado": ETAPA_PERFILADO["pedir_buro"],
        }

    if version_final and any([
        senales["pregunta_pdf"],
        any(k in _normalizar_texto(texto_usuario) for k in [
            "FICHA", "ESPECIFICACIONES", "COMO ES", "QUE TRAE", "QUE TIENE",
            "DIME MAS", "CUENTAME", "INFO", "INFORMACION", "DATOS", 
        ]),
    ]):
        return {
            "reply_text": _resumen_ficha_texto(version_final), "selected_version": version_final,
            "send_pdf": True, "send_images": False, "handoff_advisor": False,
            "detected_profile": {}, "reasoning_tags": ["fallback_pdf"],
            "accion_ofrecida": "compartir_pdf", "nueva_etapa_perfilado": etapa_perfilado,
        }
        return {
            "reply_text": _resumen_ficha_texto(version_final), "selected_version": version_final,
            "send_pdf": True, "send_images": False, "handoff_advisor": False,
            "detected_profile": {}, "reasoning_tags": ["fallback_pdf"],
            "accion_ofrecida": "compartir_pdf", "nueva_etapa_perfilado": etapa_perfilado,
        }

    if version_final and senales["pregunta_imagenes"]:
        return {
            "reply_text": f"Claro, te comparto imágenes de {version_final.title()}.",
            "selected_version": version_final, "send_pdf": False, "send_images": True,
            "handoff_advisor": False, "detected_profile": {},
            "reasoning_tags": ["fallback_imagenes"],
            "accion_ofrecida": "continuar_contexto", "nueva_etapa_perfilado": etapa_perfilado,
        }

    if version_final and senales["pregunta_precio"]:
        return {
            "reply_text": _respuesta_precio_version(version_final), "selected_version": version_final,
            "send_pdf": False, "send_images": False, "handoff_advisor": False,
            "detected_profile": {}, "reasoning_tags": ["fallback_precio"],
            "accion_ofrecida": "compartir_precio", "nueva_etapa_perfilado": etapa_perfilado,
        }

    if senales["cotizacion_personalizada"] or senales["intencion_compra"]:
        return {
            "reply_text": RESPUESTA_CONFIRMAR_ASESOR, "selected_version": version_final,
            "send_pdf": False, "send_images": False, "handoff_advisor": True,
            "detected_profile": {}, "reasoning_tags": ["fallback_asesor"],
            "accion_ofrecida": "confirmar_canalizacion", "nueva_etapa_perfilado": etapa_perfilado,
        }

    if version_directa:
        return {
            "reply_text": (
                f"Claro, te comparto información de {version_directa.title()}. "
                "Puedo ayudarte con precio, imágenes y ficha técnica en PDF."
            ),
            "selected_version": version_directa, "send_pdf": False, "send_images": False,
            "handoff_advisor": False, "detected_profile": {},
            "reasoning_tags": ["fallback_version_directa"],
            "accion_ofrecida": "continuar_contexto", "nueva_etapa_perfilado": etapa_perfilado,
        }

    return {
        "reply_text": RESPUESTA_FALLBACK, "selected_version": None,
        "send_pdf": False, "send_images": False, "handoff_advisor": False,
        "detected_profile": {}, "reasoning_tags": ["fallback_generico"],
        "accion_ofrecida": "pedir_necesidad", "nueva_etapa_perfilado": etapa_perfilado,
    }


def construir_respuesta_informativa(
    *, telefono: str, profile_name: str, texto_usuario: str,
    auto_interes_actual: Optional[str] = None, ultimo_mensaje_saliente: str = "",
    historial_reciente: Optional[list[dict[str, str]]] = None,
    accion_ofrecida_previa: Optional[str] = None,
    etapa_perfilado: int = 0, enganche_registrado: Optional[int] = None,
    buro_registrado: str = "", es_primer_mensaje: bool = False,
    nombre_cliente: str = "",
) -> tuple[str, Optional[str], bool, bool, bool, dict[str, Any], dict[str, Any], str, int]:
    texto_usuario = (texto_usuario or "").strip()
    historial_reciente = historial_reciente or []

    if texto_usuario.upper() in {"[IMAGE]", "[VIDEO]", "[AUDIO]", "[DOCUMENT]", "[STICKER]"}:
        return RESPUESTA_MEDIA, auto_interes_actual, False, False, False, {}, {"reasoning_tags": ["media_placeholder"]}, "ninguna", etapa_perfilado

    auto_interes_actual = _normalizar_version_catalogo(auto_interes_actual)

    decision: dict[str, Any] = {}
    try:
        decision = _decision_conversacional_ia(
            telefono=telefono,
            nombre_cliente=nombre_cliente or profile_name,
            texto_usuario=texto_usuario,
            auto_interes_actual=auto_interes_actual,
            ultimo_mensaje_saliente=ultimo_mensaje_saliente,
            historial_reciente=historial_reciente,
            accion_ofrecida_previa=accion_ofrecida_previa,
            etapa_perfilado=etapa_perfilado,
            enganche_registrado=enganche_registrado,
            buro_registrado=buro_registrado,
            es_primer_mensaje=es_primer_mensaje,
        )
    except Exception:
        decision = {}

    if not decision:
        decision = _fallback_respuesta(
            texto_usuario=texto_usuario, profile_name=profile_name,
            version_contexto=auto_interes_actual, es_primer_mensaje=es_primer_mensaje,
            etapa_perfilado=etapa_perfilado, nombre_cliente=nombre_cliente,
            telefono=telefono,
        )

    selected_version = _normalizar_version_catalogo(
        decision.get("selected_version") or _buscar_version_en_texto(texto_usuario) or auto_interes_actual
    )
    handoff_advisor = bool(decision.get("handoff_advisor"))
    send_pdf = bool(decision.get("send_pdf")) and bool(selected_version) and not handoff_advisor
    send_images = bool(decision.get("send_images")) and bool(selected_version) and not handoff_advisor
    detected_profile = decision.get("detected_profile") or {}
    reply_text = _limitar_texto((decision.get("reply_text") or RESPUESTA_FALLBACK).strip())

    accion_ofrecida = (decision.get("accion_ofrecida") or "ninguna").strip()
    if accion_ofrecida not in ACCIONES_OFRECIDAS_VALIDAS:
        accion_ofrecida = _determinar_accion_ofrecida(
            reply_text=reply_text, send_pdf=send_pdf, handoff_advisor=handoff_advisor,
            selected_version=selected_version, texto_usuario=texto_usuario,
        )

    try:
        nueva_etapa = max(etapa_perfilado, min(4, int(decision.get("nueva_etapa_perfilado", etapa_perfilado))))
    except (TypeError, ValueError):
        nueva_etapa = etapa_perfilado

    raw_decision = dict(decision)
    raw_decision.update({
        "selected_version": selected_version, "send_pdf": send_pdf,
        "send_images": send_images, "handoff_advisor": handoff_advisor,
        "accion_ofrecida": accion_ofrecida, "reply_text": reply_text,
        "nueva_etapa_perfilado": nueva_etapa,
    })

    return reply_text, selected_version, send_pdf, send_images, handoff_advisor, detected_profile, raw_decision, accion_ofrecida, nueva_etapa


# Respuesta automática completa

def responder_mensaje_automatico(
    *, wa_from: str, numero_asesor: str, profile_name: str = "",
    texto_usuario: str = "", wa_message_id_entrante: str = "",
    raw_message: Optional[dict] = None,
) -> dict:
    telefono = normaliza_tel_mx(replace_start(wa_from))
    numero_asesor = normaliza_tel_mx(numero_asesor)
    wa_message_id_entrante = (wa_message_id_entrante or "").strip()

    if not telefono:
        raise ValueError("Numero invalido para responder automaticamente")
    if not numero_asesor:
        raise ValueError("Numero de asesor invalido")

    if _ya_se_respondio_a_entrada(numero_asesor, wa_message_id_entrante):
        return {
            "ok": True, "skipped": True, "reason": "ya_se_respondio_a_esta_entrada",
            "telefono": telefono, "numero_asesor": numero_asesor,
            "wa_message_id_entrante": wa_message_id_entrante,
        }

    cliente, expediente = _get_or_create_cliente_y_expediente(
        telefono=telefono, numero_asesor=numero_asesor,
        profile_name=profile_name, texto_entrante=texto_usuario,
    )

    auto_interes_actual = _limpiar_auto_interes_invalido(expediente)
    nombre_contexto = (cliente.nombre or "").strip() or _extraer_nombre_basico(profile_name, "") or ""
    ultimo_mensaje_saliente = _obtener_ultimo_mensaje_saliente(cliente, numero_asesor)
    historial_reciente = _serializar_historial(cliente, numero_asesor)
    accion_ofrecida_previa = _obtener_ultima_accion_ofrecida(cliente, numero_asesor)

    total_entrantes = _contar_mensajes_entrantes(cliente, numero_asesor)
    es_primer_mensaje = total_entrantes <= 1

    etapa_perfilado = _obtener_etapa_perfilado(expediente)
    pauta = expediente.pauta or ""
    eng_str = _leer_dato_pauta(pauta, "enganche_monto")
    buro_str = _leer_dato_pauta(pauta, "buro_estado")
    try:
        enganche_registrado: Optional[int] = int(eng_str) if eng_str else None
    except ValueError:
        enganche_registrado = None

    (
        respuesta_texto, version_contexto, enviar_pdf, enviar_imagenes,
        handoff_advisor, detected_profile, raw_decision, accion_ofrecida,
        nueva_etapa_perfilado,
    ) = construir_respuesta_informativa(
        telefono=telefono, profile_name=profile_name, texto_usuario=texto_usuario,
        auto_interes_actual=auto_interes_actual, ultimo_mensaje_saliente=ultimo_mensaje_saliente,
        historial_reciente=historial_reciente, accion_ofrecida_previa=accion_ofrecida_previa,
        etapa_perfilado=etapa_perfilado, enganche_registrado=enganche_registrado,
        buro_registrado=buro_str, es_primer_mensaje=es_primer_mensaje,
        nombre_cliente=nombre_contexto,
    )

    _guardar_datos_detectados_en_cliente_y_expediente(
        cliente=cliente, expediente=expediente, profile_name=profile_name,
        detected_profile=detected_profile, version_detectada=version_contexto,
        nueva_etapa_perfilado=nueva_etapa_perfilado,
    )

    wa_res = enviar_texto_whatsapp(to=telefono, text=respuesta_texto, numero_asesor=numero_asesor)

    wa_message_id_salida = ""
    try:
        wa_message_id_salida = (wa_res.get("messages") or [{}])[0].get("id", "") or ""
    except Exception:
        pass

    _guardar_salida(
        telefono=telefono, numero_asesor=numero_asesor, cliente=cliente,
        texto=respuesta_texto, wa_message_id=wa_message_id_salida,
        raw={
            "openai_model": "gpt-4.1", "reply_to": wa_message_id_entrante,
            "numero_asesor": numero_asesor, "version_contexto": version_contexto,
            "handoff_advisor": handoff_advisor, "detected_profile": detected_profile,
            "decision": raw_decision, "accion_ofrecida": accion_ofrecida,
            "nueva_etapa_perfilado": nueva_etapa_perfilado,
            "conversation_meta": {
                "accion_ofrecida": accion_ofrecida,
                "accion_ofrecida_previa": accion_ofrecida_previa,
                "etapa_perfilado": nueva_etapa_perfilado,
            },
            "wa_response": wa_res, "raw_message": raw_message or {},
        },
        status_msg="accepted",
    )

    # Envio de imagenes
    image_results: list = []
    image_errors: list = []
    if enviar_imagenes and version_contexto:
        for imagen_relativa in _imagenes_de_version(version_contexto):
            image_url = _build_media_url(imagen_relativa)
            filename = imagen_relativa.rsplit("/", 1)[-1]
            image_error = ""
            try:
                image_res = enviar_imagen_whatsapp_por_link(
                    to=telefono, link=image_url, numero_asesor=numero_asesor,
                    caption=f"Imagen de {version_contexto.title()}",
                )
            except Exception as exc:
                image_error = str(exc)
                image_res = {"ok": False, "error": image_error}

            image_message_id = ""
            try:
                image_message_id = (image_res.get("messages") or [{}])[0].get("id", "") or ""
            except Exception:
                pass

            _guardar_salida(
                telefono=telefono, numero_asesor=numero_asesor, cliente=cliente,
                texto=f"[FILE:{filename}]", wa_message_id=image_message_id,
                raw={"reply_to": wa_message_id_entrante, "version_contexto": version_contexto,
                     "meta_type": "image", "filename": filename, "media_link": image_url,
                     "accion_ofrecida": "continuar_contexto",
                     "conversation_meta": {"accion_ofrecida": "continuar_contexto"},
                     "wa_response": image_res, "image_error": image_error},
                status_msg="accepted" if image_message_id else "failed",
            )
            image_results.append(image_res)
            if image_error:
                image_errors.append(image_error)

    # Envio de PDF
    pdf_res = None
    pdf_error = ""
    if enviar_pdf and version_contexto:
        data = CATALOGO_VEHICULOS[version_contexto]
        pdf_url = _build_pdf_url(data["pdf_relativo"])
        try:
            pdf_res = enviar_documento_whatsapp_por_link(
                to=telefono, link=pdf_url, numero_asesor=numero_asesor,
                caption=f"Ficha tecnica de {version_contexto}",
                filename=f"{version_contexto.lower().replace(' ', '-')}.pdf",
            )
        except Exception as exc:
            pdf_error = str(exc)
            pdf_res = {"ok": False, "error": pdf_error}

        pdf_message_id = ""
        try:
            pdf_message_id = (pdf_res.get("messages") or [{}])[0].get("id", "") or ""
        except Exception:
            pass

        _guardar_salida(
            telefono=telefono, numero_asesor=numero_asesor, cliente=cliente,
            texto=f"[FILE:{version_contexto}.pdf]", wa_message_id=pdf_message_id,
            raw={"reply_to": wa_message_id_entrante, "version_contexto": version_contexto,
                 "meta_type": "document",
                 "filename": f"{version_contexto.lower().replace(' ', '-')}.pdf",
                 "document_link": pdf_url, "accion_ofrecida": "compartir_pdf",
                 "conversation_meta": {"accion_ofrecida": "compartir_pdf"},
                 "wa_response": pdf_res, "pdf_error": pdf_error},
            status_msg="accepted" if pdf_message_id else "failed",
        )

    # Actualizar expediente
    cambios = ["ultimo_contacto_at"]
    expediente.ultimo_contacto_at = timezone.now()

    if version_contexto and expediente.auto_interes != version_contexto:
        expediente.auto_interes = version_contexto; cambios.append("auto_interes")

    if handoff_advisor and expediente.estado not in ("Lead Calificado", "Seguimiento"):
        expediente.estado = "Seguimiento"; cambios.append("estado")

    cfg_linea = WHATSAPP_LINES.get(numero_asesor, {})
    for campo, valor in [
        ("agencia", (cfg_linea.get("agencia") or "").strip()),
        ("business", (cfg_linea.get("business") or "Comerciales").strip()),
    ]:
        if valor and getattr(expediente, campo) != valor:
            setattr(expediente, campo, valor); cambios.append(campo)

    if expediente.canal_contacto != "WhatsApp":
        expediente.canal_contacto = "WhatsApp"; cambios.append("canal_contacto")

    cambios.append("actualizado")
    expediente.save(update_fields=list(dict.fromkeys(cambios)))

    return {
        "ok": True, "telefono": telefono, "numero_asesor": numero_asesor,
        "cliente_id": cliente.id_cliente, "expediente_id": expediente.pk,
        "respuesta": respuesta_texto, "version_detectada": version_contexto,
        "pdf_enviado": enviar_pdf, "imagenes_enviadas": enviar_imagenes,
        "handoff_advisor": handoff_advisor, "accion_ofrecida": accion_ofrecida,
        "accion_ofrecida_previa": accion_ofrecida_previa,
        "etapa_perfilado_anterior": etapa_perfilado,
        "etapa_perfilado_nueva": nueva_etapa_perfilado,
        "detected_profile": detected_profile, "decision": raw_decision,
        "wa_response": wa_res, "pdf_response": pdf_res, "pdf_error": pdf_error,
        "image_responses": image_results, "image_errors": image_errors,
    }