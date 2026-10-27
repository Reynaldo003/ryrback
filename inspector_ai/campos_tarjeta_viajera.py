"""Campos editables del PDF de Tarjeta Viajera (609 × 794.25 pt, origen superior izquierdo).
Los campos ya tomados automáticamente de HojaIngresos se siguen rellenando desde tarjeta_viajera.py.
Ajustar x/y sobre la plantilla Canva si se cambia su diseño.
"""

ANCHO_PDF = 609
ALTO_PDF = 794.25


def construir_campos():
    campos = []

    def texto(nombre, titulo, pagina, x, y, ancho, alto=12, seccion="General", tipo="texto"):
        campos.append({"nombre": nombre, "titulo": titulo, "pagina": pagina,
                       "x": x, "y": y, "ancho": ancho, "alto": alto,
                       "seccion": seccion, "tipo": tipo})

    def casilla(nombre, titulo, pagina, x, y, seccion):
        campos.append({"nombre": nombre, "titulo": titulo, "pagina": pagina,
                       "x": x, "y": y, "ancho": 8, "alto": 8,
                       "seccion": seccion, "tipo": "casilla"})

    def opcion(nombre, titulo, pagina, opciones, seccion):
        # Cada opción indica el centro de su casilla/círculo en coordenadas del PDF.
        campos.append({"nombre": nombre, "titulo": titulo, "pagina": pagina,
                       "seccion": seccion, "tipo": "opcion",
                       "opciones": [
                           {"valor": valor, "titulo": etiqueta, "x": x, "y": y}
                           for valor, etiqueta, x, y in opciones
                       ]})

    # PÁGINA 1 — Preparación de cita: conservar los datos CRM ya rellenados por el generador.
    opcion("campana_elsapro", "Campaña en ElsaPro", 1,
           [("si", "Sí", 233, 105), ("no", "No", 266, 105)], "Preparación de la cita")
    texto("numero_campana", "Número de campaña", 1, 222, 126, 58, 10, "Preparación de la cita")
    opcion("movilidad", "¿Requiere movilidad?", 1,
           [("si", "Sí", 502, 88), ("no", "No", 548, 88)], "Preparación de la cita")
    casilla("auto_movilidad", "Auto de movilidad", 1, 548, 105, "Preparación de la cita")
    casilla("taxi_transporte", "Taxi/transporte", 1, 548, 117, "Preparación de la cita")
    texto("otro_transporte", "Otro transporte", 1, 499, 126, 70, 10, "Preparación de la cita")
    casilla("tabla_mantenimiento_fisica", "Tabla de mantenimiento física", 1, 575, 183, "Preparación de la cita")
    casilla("tabla_mantenimiento_digital", "Tabla de mantenimiento digital", 1, 575, 192, "Preparación de la cita")

    # Inventario de auto: cada ítem se guarda de forma independiente.
    inventario_izquierda = [
        ("tapetes", "Tapetes"), ("instrumentos_tablero", "Instrumentos de tablero"),
        ("antena", "Antena"), ("emblemas", "Emblemas"), ("tapon_gasolina", "Tapón de gasolina"),
        ("placas", "Placas"), ("cables", "Cables"), ("llave_rueda", "Llave de rueda"),
        ("tapon_aceite", "Tapón de aceite"), ("vestiduras", "Vestiduras"),
        ("unidad_luces", "Unidad de luces"), ("llantas_cuatro", "Llantas (4)"),
        ("molduras", "Molduras"), ("llanta_refaccion", "Llanta de refacción"),
    ]
    inventario_derecha = [
        ("bateria", "Batería"), ("bocinas", "Bocinas"), ("espejo_retrovisor", "Espejo retrovisor"),
        ("bocas_claxon", "Bocas de claxon"), ("cuarto_luces", "1/4 luces"),
        ("cristales", "Cristales"), ("tapones_rueda", "Tapones de rueda"),
        ("limpiadores", "Limpiadores"), ("gato_hidraulico", "Gato hidráulico"),
        ("varilla_aceite", "Varilla de aceite"), ("radio", "Radio"), ("encendedor", "Encendedor")
    ]
    centros_izquierda = [263.4, 274.7, 286.0, 295.0, 303.3, 311.6, 319.1,
                         326.7, 335.0, 343.3, 351.6, 359.9, 368.2, 376.5]
    centros_derecha = [263.4, 272.4, 280.7, 289.0, 296.5, 304.1,
                       311.6, 319.4, 327.7, 335.3, 342.8, 351.1]
    for (clave, titulo), y in zip(inventario_izquierda, centros_izquierda):
        casilla(f"inv_{clave}", titulo, 1, 134.5, y, "Inventario de auto")
    for (clave, titulo), y in zip(inventario_derecha, centros_derecha):
        casilla(f"inv_{clave}", titulo, 1, 202.1, y, "Inventario de auto")

    opcion("nivel_gasolina", "Nivel de gasolina", 1,
           [("lleno", "Lleno", 247, 266), ("3/4", "3/4", 247, 287),
            ("1/2", "1/2", 247, 310), ("1/4", "1/4", 247, 334),
            ("reserva", "Reserva", 247, 374)], "Inventario de auto")
    opcion("limpiaparabrisas", "Limpiaparabrisas", 1,
           [("bien", "Bien", 476, 344), ("mal", "Mal", 509, 344)], "Recepción ideal")
    posiciones_ruedas = [
        ("delantera_derecha", "Delantera derecha", 371),
        ("delantera_izquierda", "Delantera izquierda", 388),
        ("trasera_izquierda", "Trasera izquierda", 404),
        ("trasera_derecha", "Trasera derecha", 421)
    ]
    for clave, nombre, y in posiciones_ruedas:
        casilla(f"pastillas_{clave}", f"Pastillas de freno - {nombre}", 1, 412, y, "Recepción ideal")
        casilla(f"disco_{clave}", f"Disco de freno - {nombre}", 1, 460, y, "Recepción ideal")
        casilla(f"llanta_{clave}", f"Llanta - {nombre}", 1, 544, y, "Recepción ideal")
        texto(f"profundidad_{clave}", f"Profundidad en mm - {nombre}", 1, 488, y - 5, 33, 9, "Recepción ideal", "numero")
    # Firmas se registran como nombres; para firmas manuscritas se requiere un pad de firma separado.
    texto("nombre_recepcion", "Nombre de quien recibe el vehículo", 1, 67, 402, 85, 10, "Recepción ideal")
    texto("nombre_entrega", "Nombre de quien entrega el vehículo", 1, 180, 402, 84, 10, "Recepción ideal")

    # Presupuesto de mano de obra: ocho renglones editables.
    for fila in range(1, 9):
        y = 482 + (fila - 1) * 12
        for clave, titulo, x, ancho, tipo in [
            ("posicion", "Posición", 65, 70, "texto"),
            ("descripcion", "Descripción", 143, 160, "texto"),
            ("tiempo", "Unidades de tiempo", 311, 78, "numero"),
            ("costo", "Costo", 397, 65, "numero"),
        ]:
            texto(f"mano_obra_{fila}_{clave}", f"Mano de obra {fila}: {titulo}",
                  1, x, y, ancho, 11, "Presupuesto de mano de obra", tipo)

    # Presupuesto de refacciones: siete renglones editables.
    for fila in range(1, 8):
        y = 625 + (fila - 1) * 12
        for clave, titulo, x, ancho, tipo in [
            ("numero_parte", "Número de parte", 66, 71, "texto"),
            ("descripcion", "Descripción", 143, 245, "texto"),
            ("costo", "Costo", 398, 65, "numero"),
        ]:
            texto(f"refaccion_{fila}_{clave}", f"Refacción {fila}: {titulo}",
                  1, x, y, ancho, 11, "Presupuesto de refacciones", tipo)

    for clave, titulo, x, y, ancho, alto, tipo in [
        ("numero_presupuesto", "Número de presupuesto", 480, 454, 93, 14, "texto"),
        ("fecha_presupuesto", "Fecha de elaboración", 480, 486, 93, 14, "fecha"),
        ("validacion_jefe_taller", "Validación del jefe de taller (nombre)", 480, 550, 93, 14, "texto"),
        ("inicio_trabajo", "Fecha y hora de inicio del trabajo", 481, 675, 91, 17, "texto"),
        ("fin_trabajo", "Fecha y hora de finalización del trabajo", 481, 732, 91, 16, "texto"),
        ("observaciones_taller", "Observaciones del taller", 74, 735, 389, 20, "texto"),
    ]:
        texto(clave, titulo, 1, x, y, ancho, alto, "Técnico mecánico", tipo)

    # PÁGINA 2 — Tres recorridos de prueba.
    for prueba, y in [(1, 93), (2, 172), (3, 252)]:
        for clave, titulo, x, dy, ancho, tipo in [
            ("fecha", "Fecha", 66, 0, 97, "fecha"),
            ("hora", "Hora", 167, 0, 76, "hora"),
            ("km_inicial", "Kilometraje inicial", 68, 22, 75, "numero"),
            ("km_final", "Kilometraje final", 165, 22, 76, "numero"),
            ("realizada_por", "Realizada por", 67, 47, 176, "texto"),
        ]:
            nombre_campo = (f"{clave}_prueba_1"
                            if prueba == 1 and clave in ("km_inicial", "km_final")
                            else f"prueba_{prueba}_{clave}")
            texto(nombre_campo, f"Prueba {prueba}: {titulo}",
                  2, x, y + dy, ancho, 12, "Pruebas de manejo", tipo)

    # Verificación del manejo, cada elemento puede marcarse para cada una de las 3 pruebas.
    verificaciones = [
        ("motor_potencia", "Motor: potencia, fallos de encendido y aceleración", 113.5),
        ("embrague", "Embrague y arranque", 122),
        ("cambio_manual", "Cambio manual", 130.5),
        ("cambio_automatico", "Cambio automático", 139),
        ("posicion_palanca", "Posición de la palanca", 146.8),
        ("shift_lock", "Shift Lock / bloqueo", 154.5),
        ("funcionamiento", "Funcionamiento", 163),
        ("cuadro_instrumentos", "Cuadro de instrumentos", 171.9),
        ("frenos", "Frenos de pie, mano y ABS", 180.4),
        ("direccion", "Dirección", 202.6),
        ("techo", "Techo deflector", 219.4),
        ("cinturones", "Cinturones de seguridad", 227.1),
        ("radio_navegacion", "Radio y navegación", 235.6),
        ("mfa", "Indicador multifuncional", 243.4),
        ("climatizador", "Climatizador", 251.1),
        ("deriva_vehiculo", "Tendencia a derivar", 266.4),
        ("desequilibrio", "Desequilibrio", 274.1),
        ("cojinete_ruedas", "Cojinete de ruedas", 282.6),
        ("motor_caliente", "Arranque en caliente", 290.4),
    ]
    for clave, titulo, y in verificaciones:
        for prueba, x in [(1, 288.9), (2, 315.4), (3, 342.0)]:
            casilla(f"verif_{clave}_{prueba}", f"Prueba {prueba}: {titulo}",
                    2, x, y, "Lista de verificación")

    controles = [
        ("plan_asistencia", "Plan de asistencia técnica", 361),
        ("luces", "Luces", 390.4),
        ("limpiaparabrisas", "Limpiaparabrisas", 422.7),
        ("fluidos_bateria", "Fluidos y batería", 447.6),
        ("puertas", "Puertas y levantacristales", 473.6),
        ("neumaticos_frenos", "Neumáticos y frenos", 496),
        ("bajos", "Bajos del vehículo", 528.4),
        ("trabajo_realizado", "Trabajo realizado correctamente", 561.9),
        ("mantenimiento", "Formato de mantenimiento", 597.5),
        ("intervalos_servicio", "Intervalos del próximo servicio", 633.6),
        ("ampliacion_orden", "Ampliación de la orden", 660.6),
        ("recorrido_documentado", "Prueba de manejo documentada", 687),
        ("limpieza_final", "Limpieza del vehículo", 713.3),
    ]
    for clave, titulo, y in controles:
        for responsable, x in [(1, 541.6), (2, 578.2)]:
            casilla(f"calidad_{clave}_{responsable}",
                    f"Control {responsable}: {titulo}", 2, x, y, "Control de calidad")
    texto("calidad_1_nombre", "Control de calidad 1: nombre y fecha", 2,
          92, 744, 190, 12, "Control de calidad")
    texto("calidad_2_nombre", "Control de calidad 2: nombre y fecha", 2,
          355, 744, 210, 12, "Control de calidad")

    # PÁGINA 3 — Preparación de entrega del vehículo.
    texto("entrega_fecha", "Fecha de entrega", 3, 155, 84, 90, 10, "Preparación de entrega", "fecha")
    texto("entrega_hora_termino", "Hora de término", 3, 268, 84, 80, 10, "Preparación de entrega", "hora")
    texto("entrega_hora_inicio", "Hora de inicio", 3, 390, 84, 80, 10, "Preparación de entrega", "hora")
    actividades = [
        ("limpieza_exterior", "Verificar limpieza y daños exterior", 160.6),
        ("condiciones_originales", "Verificar condiciones originales del vehículo", 193.9),
        ("limpieza_interior", "Verificar limpieza y daños interior", 222.6),
        ("proximo_servicio", "Verificar la indicación del próximo servicio", 257),
        ("ajustes_personalizados", "Verificar ajustes personalizados", 280.5),
        ("refacciones_usadas", "Reunir refacciones usadas", 304.3),
        ("hora_entrega_cliente", "Informar al cliente hora de entrega", 325.4),
        ("documentos_factura", "Recopilar documentos y preparar factura", 358.2),
    ]
    for clave, titulo, y in actividades:
        opcion(f"entrega_{clave}", titulo, 3,
               [("ok", "OK", 527, y), ("no_ok", "NO OK", 553, y),
                ("na", "N/A", 580, y)], "Verificación de entrega")
    texto("entrega_asesor_nombre", "Nombre del asesor que entrega", 3,
          157, 410, 270, 12, "Cierre de entrega")

    nombres = [campo["nombre"] for campo in campos]
    if len(nombres) != len(set(nombres)):
        raise ValueError("Existen nombres de campo duplicados en la configuración")
    return campos


CAMPOS_TARJETA_VIAJERA = construir_campos()
MAPA_CAMPOS_TARJETA = {campo["nombre"]: campo for campo in CAMPOS_TARJETA_VIAJERA}
