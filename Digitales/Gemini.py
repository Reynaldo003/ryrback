from google import genai
from google.genai import types

client = genai.Client(api_key="")

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

versiones_validas = sorted(CATALOGO_VEHICULOS.keys())
versiones_str = "\n".join(f"- {v}" for v in versiones_validas)

from datetime import date as _date
_hoy = _date.today()
_meses_es = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
                7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
_ultimo_dia = [31,28,31,30,31,30,31,31,30,31,30,31][_hoy.month - 1]
_vigencia = f"al {_ultimo_dia} de {_meses_es[_hoy.month]} de {_hoy.year}"

instrucciones = (
    f"""
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
)
while True:
    pregunta = str(input("Ingresa tu pregunta: "))
    chat = client.chats.create(
        model="gemini-3.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=instrucciones,
            temperature=0.8
        )
    )
    response = chat.send_message(pregunta)

    print(response.text)
