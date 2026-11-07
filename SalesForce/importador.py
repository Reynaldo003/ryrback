"""Importación manual de reportes Salesforce: validación y UPSERT por lotes."""
import csv
import hashlib
import io
import re
import unicodedata
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as ErrorModelo
from django.db import models, transaction
from django.utils import timezone
from openpyxl import load_workbook

from .models import (
    ActividadProceso, ActividadProspecto, EntregaComercial, FacturaComercial,
    ProcesoComercial, ProcesoComercialDetalle, Prospecto,
)

TAMANO_MAXIMO = 60 * 1024 * 1024
TAMANO_LOTE = 400

# El orden importa para la primera carga: prospectos y procesos antes de sus hijos.
TABLAS = {
    "prospectos": {"nombre": "Prospectos", "modelo": Prospecto, "clave": "Id. de prospecto", "firmas": ["Horas Hasta Primer Contacto"]},
    "procesos": {"nombre": "Procesos comerciales", "modelo": ProcesoComercial, "clave": "Id. del proceso comercial", "firmas": ["Ingresos previstos", "Lead ID"]},
    "procesos-detalle": {"nombre": "Detalles de procesos (Py)", "modelo": ProcesoComercialDetalle, "clave": "Id. del proceso comercial", "firmas": ["Cuenta personal: Sexo", "Forma de Pago"]},
    "actividades-prospectos": {"nombre": "Actividades de prospectos", "modelo": ActividadProspecto, "clave": "Id. de actividad", "firmas": ["No.Concesionaria Virtual Aplicada"]},
    "actividades-procesos": {"nombre": "Actividades de procesos", "modelo": ActividadProceso, "clave": "Id. de actividad", "firmas": ["Número de Concesionaria (Interfaz)"]},
    "facturas": {"nombre": "Facturadas", "modelo": FacturaComercial, "clave": "Factura Id.", "firmas": ["Fecha de Facturación", "Nombre de Factura"], "prohibidas": ["Cliente de Venta: Nombre de la cuenta"]},
    "entregas": {"nombre": "Entregados al 100%", "modelo": EntregaComercial, "clave": "Factura Id.", "firmas": ["Estatus", "Cliente de Venta: Nombre de la cuenta"]},
}

# Mapeos: nombre_del_campo_modelo -> columna del reporte original.
# Las demás columnas se conservan completas en datos_origen (JSONB de PostgreSQL).
MAPEOS = {
    "prospectos": {
        "numero_concesionaria": "No.Concesionaria (Interfaces)",
        "concesionaria": "Concesionaria o Marca Propietaria",
        "fecha_creacion": "Fecha de creación", "nombre": "Nombre",
        "apellido_paterno": "Apellido paterno", "modelo_interes": "Modelo de Interés",
        "telefono": "Teléfono", "email": "Email", "ciudad": "Ciudad", "calle": "Calle",
        "fuente_primaria": "Fuente primaria", "propietario": "Propietario del prospecto",
        "alias_propietario": "Alias del propietario del prospecto",
        "creado_por": "Creado por", "modificado_por": "Última modificación por",
        "tipo_registro": "Tipo de registro de prospecto", "estado": "Estado de prospecto",
        "calificado": "Calificado", "contactado": "Contactado",
        "fecha_contacto": "Fecha de contacto", "ultima_actividad": "Última actividad",
        "canal": "Canal", "medio_origen": "Medio por el cual se enteró",
        "periodo_compra": "Periodo de Compra", "motivo_descalificacion": "Motivo de Descalificación",
        "tipo_prospecto": "Tipo de Prospecto", "permiso_marketing": "Permiso de Contacto Marketing",
        "prospeccion": "Prospección", "prueba_manejo_antes_calificacion": "Prueba de Manejo antes de Calificación",
        "tiempo_atencion_horas": "Tiempo de atención en horas", "horas_primer_contacto": "Horas Hasta Primer Contacto",
        "cotizaciones": "Conteo de Cotizaciones", "fecha_hora_descalificado": "Fecha/Hora Descalificado",
        "fecha_hora_nuevo": "Fecha/Hora de Nuevo o Creacion",
    },
    "procesos": {
        "numero_concesionaria": "Número de Concesionaria", "concesionaria": "Concesionaria",
        "fecha_creacion": "Fecha de creación", "propietario": "Propietario del proceso comercial",
        "nombre_cuenta": "Nombre de la cuenta", "nombre_proceso": "Nombre del proceso comercial",
        "etapa": "Etapa", "periodo_fiscal": "Periodo fiscal", "importe": "Importe",
        "ingresos_previstos": "Ingresos previstos", "probabilidad": "Probabilidad (%)",
        "antiguedad": "Antigüedad", "siguiente_paso": "Siguiente paso",
        "fuente_primaria": "Fuente primaria", "tipo": "Tipo",
        "tipo_registro": "Tipo de registro del proceso comercial", "id_cuenta": "Id. de la cuenta",
        "contact_id": "Contact ID", "id_cliente_sf_dms": "ID Cliente SF - DMS",
        "id_cliente_dms": "Id Cliente DMS", "unidades_vendidas": "Cantidad de unidades vendidas",
        "ultima_actividad": "Última actividad", "creado_por": "Creado por",
        "modificado_por": "Última modificación por", "cerrado": "Cerrado",
        "fecha_cierre": "Fecha de cierre (2)", "calificados": "Calificados",
        "canal_cuenta": "Canal de Cuenta", "canal": "Canal",
        "estado_facturacion": "Estado de Facturación", "prueba_manejo": "Prueba de manejo",
        "prueba_manejo_realizada": "Prueba de Manejo realizada",
        "email_titular": "Email Titular", "telefono": "Teléfono",
        "lead_id": "Lead ID", "fecha_modificacion": "Fecha de la última modificación",
        "duracion_etapa": "Duración de la etapa",
    },
    "procesos-detalle": {
        "forma_pago": "Forma de Pago", "direccion_facturacion_1": "Línea 1 de Dirección de facturación",
        "direccion_facturacion_2": "Línea 2 de Dirección de facturación",
        "direccion_facturacion_3": "Línea 3 de Dirección de facturación",
        "colonia_facturacion": "Factura: Colonia / Fraccionamiento",
        "ciudad_facturacion": "Ciudad de facturación",
        "municipio_facturacion": "Delegación o Municipio de Facturación",
        "sexo": "Cuenta personal: Sexo", "profesion": "Cuenta personal: Profesión",
        "ocupacion": "Cuenta personal: Ocupación", "estado_civil": "Cuenta personal: Estado Civil",
        "nivel_estudios": "Cuenta personal: Nivel de Estudios",
        "numero_hijos": "Cuenta personal: Número de Hijos",
        "modelo_interes_1": "Modelo de interés", "modelo_interes_2": "Modelo de Interés__2",
        "fecha_nacimiento": "Cuenta personal: Fecha de nacimiento",
        "monto_financiar": "Monto a financiar", "producto_contrato": "Producto de Contrato",
        "rfc": "RFC", "codigo_postal": "Codigo Postal",
        "consentimiento_contacto": "Consentimiento de Contacto",
        "tipo_financiamiento": "Tipo de Financiamiento", "periodo_compra": "Periodo de Compra",
        "origen_venta": "Origen del Proceso de Venta", "marca": "Marca",
        "modelo_auto": "Modelo de Auto", "modelo_competencia": "Modelo de Interés de la Competencia",
        "financiera": "Financiera", "fuente_lead": "Fuente de Lead",
        "fecha_hora_entrega": "Fecha/Hora de Entrega", "fecha_hora_venta": "Fecha/Hora de Venta",
        "fecha_hora_facturacion": "Fecha / Hora Facturación", "facturas": "Facturas",
        "es_cerrada_ganada": "Es Cerrada Ganada", "buy_back": "Buy Back",
        "edad": "Cuenta personal: Edad",
    },
    "facturas": {
        "numero_concesionaria": "Número de Concesionaria", "marca": "Marca",
        "fecha_facturacion": "Fecha de Facturación", "nombre_proceso": "Nombre del proceso comercial",
        "nombre_cuenta": "Nombre de la cuenta: Nombre de la cuenta",
        "propietario_proceso": "Propietario del proceso comercial: Nombre completo",
        "etapa": "Etapa", "nombre_factura": "Nombre de Factura",
        "fecha_entrega": "Fecha de Entrega", "vin": "VIN",
        "fecha_modificacion_etapa": "Fecha de la última modificación de Etapa",
        "importe": "Importe", "total": "Total", "id_sales_dms": "idSalesDMS",
        "canal_cuenta": "Canal de Cuenta", "tipo_registro_proceso": "Tipo de registro del proceso comercial",
    },
    "entregas": {
        "numero_concesionaria": "Número de Concesionaria", "marca": "Marca",
        "fecha_facturacion": "Fecha de Facturación", "nombre_proceso": "Nombre del proceso comercial",
        "propietario_proceso": "Propietario del proceso comercial: Nombre completo",
        "etapa": "Etapa", "modelo_interes": "Modelo de Interés: Nombre de Modelo",
        "modelo": "Modelo", "nombre_factura": "Nombre de Factura",
        "fecha_entrega": "Fecha de Entrega", "cantidad_facturas_facturadas": "Cant.Fact.Estatus Facturado",
        "estatus": "Estatus", "calificados": "Calificados", "forma_pago": "Forma de Pago",
        "metodo_pago": "Método de Pago", "creado_por": "Creado por: Nombre completo",
        "nombre_cuenta": "Nombre de la cuenta: Nombre de la cuenta",
        "cliente_venta": "Cliente de Venta: Nombre de la cuenta",
        "cliente_facturacion": "Cliente de Facturación: Nombre de la cuenta",
        "vin": "VIN", "importe": "Importe", "total": "Total",
        "id_sales_dms": "idSalesDMS", "tipo_registro_proceso": "Tipo de registro del proceso comercial",
        "fecha_modificacion": "Fecha de la última modificación",
        "fecha_modificacion_etapa": "Fecha de la última modificación de Etapa",
        "tipo_proceso_venta": "Tipo del proceso de venta", "canal_cuenta": "Canal de Cuenta",
    },
}

CAMPOS_ACTIVIDAD = {
    "numero_concesionaria": "Número de Concesionaria",
    "concesionaria": "Concesionaria o Marca Propietaria",
    "asignado": "Asignado", "alias_asignado": "Alias asignado", "tipo": "Tipo",
    "subtipo_tarea": "Subtipo de tarea", "subtipo_evento": "Subtipo de evento",
    "tipo_registro_actividad": "Tipo de registro de Tarea/Evento",
    "asunto": "Asunto", "fecha": "Fecha", "vencimiento": "Hora de vencimiento",
    "finalizacion": "Fecha/Hora de finalización", "duracion_minutos": "Duración (minutos)",
    "duracion_horas": "Duración (horas)", "duracion_llamada_segundos": "Duración de la llamada (segundos)",
    "duracion_llamada_minutos_original": "Duración de la llamada (minutos)",
    "tipo_llamada": "Tipo de llamada", "resultado_llamada": "Resultado de la llamada",
    "identificador_llamada": "Identificador del objeto de llamada",
    "prioridad": "Prioridad", "estado": "Estado", "ubicacion": "Ubicación",
    "es_tarea": "Tarea", "cerrado": "Cerrado", "invitacion_eventos": "Invitación de eventos",
    "creado_por": "Creado por", "modificado_por": "Última modificación por",
    "comentarios": "Comentarios", "comentarios_completos": "Comentarios completos",
    "fecha_creacion": "Fecha de creación", "fecha_modificacion": "Fecha de la última modificación",
}
MAPEOS["actividades-prospectos"] = {
    **CAMPOS_ACTIVIDAD,
    "numero_concesionaria": "No.Concesionaria (Interfaces)",
    "numero_concesionaria_virtual": "No.Concesionaria Virtual Aplicada",
    "concesionaria": "Concesionaria o Marca Propietaria", "marca": "Marca",
    "nombre_prospecto": "Nombre", "apellido_paterno": "Apellido paterno",
    "propietario_prospecto": "Propietario del prospecto",
    "estado_prospecto": "Estado de prospecto", "ultima_actividad_prospecto": "Última actividad",
}
MAPEOS["actividades-procesos"] = {
    **CAMPOS_ACTIVIDAD,
    "concesionaria": "Concesionaria",
    "numero_concesionaria_interfaz": "Número de Concesionaria (Interfaz)",
    "inicio": "Inicio", "fin": "Fin", "nombre_proceso": "Nombre del proceso comercial",
    "propietario_proceso": "Propietario del proceso comercial",
    "tipo_proceso": "Tipo__2", "etapa_proceso": "Etapa del proceso comercial",
    "importe_proceso": "Importe", "descripcion": "Descripción",
}


def limpiar_etiqueta(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto.strip()).casefold()


def nombrar_columnas(valores):
    usados = {}
    nombres = []
    for indice, valor in enumerate(valores, start=1):
        nombre = str(valor or f"Columna {indice}").strip()
        clave = limpiar_etiqueta(nombre)
        usados[clave] = usados.get(clave, 0) + 1
        if usados[clave] > 1:
            nombre = f"{nombre}__{usados[clave]}"
        nombres.append(nombre)
    return nombres


def comprobar_encabezados(tabla, encabezados):
    presentes = {limpiar_etiqueta(c) for c in encabezados}
    config = TABLAS[tabla]
    obligatorias = [config["clave"], *config.get("firmas", [])]
    faltantes = [c for c in obligatorias if limpiar_etiqueta(c) not in presentes]
    prohibidas = [c for c in config.get("prohibidas", []) if limpiar_etiqueta(c) in presentes]
    if faltantes or prohibidas:
        raise ValueError(
            "El archivo no corresponde a la tabla seleccionada. "
            + (f"Faltan columnas: {', '.join(faltantes)}. " if faltantes else "")
            + (f"Columnas de otro reporte: {', '.join(prohibidas)}." if prohibidas else "")
        )


def archivo_legible(archivo):
    extension = archivo.name.rsplit(".", 1)[-1].lower()
    if extension not in {"csv", "xlsx", "xls"}:
        raise ValueError("El archivo debe ser CSV, XLSX o XLS.")
    if archivo.size > TAMANO_MAXIMO:
        raise ValueError("El archivo supera el límite de 60 MB.")
    if archivo.size == 0:
        raise ValueError("El archivo está vacío.")
    return extension


def iterar_filas(archivo, tabla):
    """Produce (número de línea, dict de columnas), sin cargar el Excel entero en memoria."""
    extension = archivo_legible(archivo)
    clave_buscada = limpiar_etiqueta(TABLAS[tabla]["clave"])
    archivo.seek(0)
    if extension == "csv":
        muestra = archivo.read(8192)
        archivo.seek(0)
        try:
            muestra.decode("utf-8-sig")
            codificacion = "utf-8-sig"
        except UnicodeDecodeError:
            codificacion = "cp1252"
        texto = io.TextIOWrapper(archivo.file, encoding=codificacion, errors="replace", newline="")
        try:
            ejemplo = muestra.decode(codificacion, errors="replace").splitlines()[0]
            separador = ";" if ejemplo.count(";") > ejemplo.count(",") else ","
            lector = csv.reader(texto, delimiter=separador)
            encabezados = nombrar_columnas(next(lector, []))
            comprobar_encabezados(tabla, encabezados)
            for numero, valores in enumerate(lector, start=2):
                if not any(str(v or "").strip() for v in valores):
                    continue
                yield numero, dict(zip(encabezados, valores))
        finally:
            texto.detach()  # Permite volver a leer el archivo para confirmar la importación.
        return

    if extension == "xlsx":
        libro = load_workbook(archivo, read_only=True, data_only=True)
        hoja = libro.worksheets[0]
        filas = hoja.iter_rows(values_only=True)
    else:
        try:
            import xlrd
        except ImportError as exc:
            raise ValueError("Para archivos .xls debes instalar xlrd.") from exc
        libro = xlrd.open_workbook(file_contents=archivo.read())
        hoja = libro.sheet_by_index(0)
        def filas_xls():
            for indice in range(hoja.nrows):
                valores = []
                for celda in hoja.row(indice):
                    if celda.ctype == xlrd.XL_CELL_DATE:
                        valores.append(xlrd.xldate_as_datetime(celda.value, libro.datemode))
                    else:
                        valores.append(celda.value)
                yield valores
        filas = filas_xls()

    encabezados = None
    try:
        for numero, valores in enumerate(filas, start=1):
            if encabezados is None:
                if numero > 35:
                    raise ValueError("No se encontraron encabezados Salesforce en las primeras 35 filas.")
                if clave_buscada in {limpiar_etiqueta(c) for c in valores if c is not None}:
                    encabezados = nombrar_columnas(valores)
                    comprobar_encabezados(tabla, encabezados)
                continue
            if not any(v is not None and str(v).strip() for v in valores):
                continue
            fila = dict(zip(encabezados, valores))
            # Los informes Salesforce incluyen una fila TOTAL al final.
            if any(str(v or "").strip().casefold() in {"total", "totales"} for v in list(valores)[:2]):
                continue
            yield numero, fila
        if encabezados is None:
            raise ValueError(f"No se encontró la columna {TABLAS[tabla]['clave']}.")
    finally:
        if extension == "xlsx":
            libro.close()


def leer_columna(fila, nombre):
    buscada = limpiar_etiqueta(nombre)
    for clave, valor in fila.items():
        if limpiar_etiqueta(clave) == buscada:
            return valor
    return None


def texto_celda(valor):
    if valor is None:
        return ""
    if isinstance(valor, (date, datetime, time)):
        return valor.isoformat()
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def obtener_fecha(valor, con_hora=False, fecha_base=None):
    if isinstance(valor, datetime):
        resultado = valor
    elif isinstance(valor, time):
        if not con_hora or fecha_base is None:
            return None
        resultado = datetime.combine(fecha_base, valor)
    elif isinstance(valor, date):
        resultado = datetime.combine(valor, time.min)
    else:
        dato = texto_celda(valor)
        if not dato or dato in {":", "-"}:
            return None
        resultado = None
        formatos = ("%d/%m/%Y, %H:%M:%S", "%d/%m/%Y, %H:%M", "%d/%m/%Y %H:%M:%S",
                    "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")
        for formato in formatos:
            try:
                resultado = datetime.strptime(dato, formato)
                break
            except ValueError:
                continue
        if resultado is None and con_hora and fecha_base and re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", dato):
            formato_hora = "%H:%M:%S" if dato.count(":") == 2 else "%H:%M"
            resultado = datetime.combine(fecha_base, datetime.strptime(dato, formato_hora).time())
        if resultado is None:
            raise ValueError(f"Fecha no reconocida: {dato[:35]}")
    if con_hora:
        if timezone.is_naive(resultado):
            resultado = timezone.make_aware(resultado, timezone.get_current_timezone())
        return resultado
    return resultado.date()


def convertir_valor(valor, campo, fecha_base=None):
    dato = texto_celda(valor)
    if not dato or dato in {"-", ":"}:
        return None
    # Salesforce exporta marcadores de error en columnas calculadas.
    # No se fuerzan a tipos incompatibles; el valor original queda en datos_origen.
    marcador = dato.strip().casefold()
    if isinstance(campo, (models.DateField, models.DecimalField, models.IntegerField, models.BooleanField)):
        if marcador in {"nº de error", "n° de error", "n/a", "#n/a", "na", "s/d", "no aplica", "#value!", "#ref!", "#div/0!", "error"}:
            return None
        if isinstance(campo, models.DateField) and marcador in {"0", "0.0"}:
            return None
    if isinstance(campo, models.DateTimeField):
        return obtener_fecha(valor, con_hora=True, fecha_base=fecha_base)
    if isinstance(campo, models.DateField):
        return obtener_fecha(valor)
    if isinstance(campo, models.BooleanField):
        if dato.casefold() in {"1", "1.0", "si", "sí", "true", "verdadero", "yes"}:
            return True
        if dato.casefold() in {"0", "0.0", "no", "false", "falso"}:
            return False
        raise ValueError(f"Valor booleano inválido: {dato}")
    if isinstance(campo, (models.DecimalField, models.IntegerField)):
        # Los informes Salesforce suelen exportar 1234.50; también se toleran 1,234.50 y 1.234,50.
        if isinstance(campo, models.IntegerField) and re.fullmatch(r"\d+\s+(o\s+mas|a\s+\d+)", limpiar_etiqueta(dato)):
            return None  # Valor agrupado ("5 o más"): conservar solo en datos_origen.
        numero = dato.replace("$", "").replace(" ", "").replace("%", "")
        if "," in numero and "." in numero:
            numero = numero.replace(",", "") if numero.rfind(".") > numero.rfind(",") else numero.replace(".", "").replace(",", ".")
        elif "," in numero:
            numero = numero.replace(",", ".")
        try:
            valor_numerico = Decimal(numero)
            if not valor_numerico.is_finite():
                raise ValueError("Número no finito")
            if isinstance(campo, models.IntegerField):
                if valor_numerico != valor_numerico.to_integral_value():
                    raise ValueError(f"Debe ser entero: {dato}")
                return int(valor_numerico)
            if len(valor_numerico.as_tuple().digits) > campo.max_digits + 2:
                raise ValueError(f"Número fuera de rango: {dato}")
            return valor_numerico
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Número inválido: {dato}") from exc
    if isinstance(campo, models.CharField) and campo.max_length and len(dato) > campo.max_length:
        raise ValueError(f"Texto supera {campo.max_length} caracteres")
    return dato


def preparar_fila(tabla, fila):
    modelo = TABLAS[tabla]["modelo"]
    clave = texto_celda(leer_columna(fila, TABLAS[tabla]["clave"]))
    if not clave:
        raise ValueError(f"Falta {TABLAS[tabla]['clave']}")
    if len(clave) > 18:
        raise ValueError("El identificador Salesforce excede 18 caracteres")
    valores = {}
    if tabla == "procesos-detalle":
        valores["proceso_id"] = clave
    else:
        valores[modelo._meta.pk.attname] = clave
    fecha_base = obtener_fecha(leer_columna(fila, "Fecha")) if tabla.startswith("actividades-") else None
    for nombre, columna in MAPEOS[tabla].items():
        original = leer_columna(fila, columna)
        if texto_celda(original) == "":
            continue  # No borrar datos existentes por celdas vacías.
        campo = modelo._meta.get_field(nombre)
        convertido = convertir_valor(original, campo, fecha_base=fecha_base)
        if convertido is not None:
            valores[nombre] = convertido
    if tabla == "prospectos":
        nombre = " ".join(p for p in (valores.get("nombre", ""), valores.get("apellido_paterno", "")) if p)
        modelo_interes = valores.get("modelo_interes", "")
        if nombre and modelo_interes:
            valores["nombre_proceso_generado"] = f"{nombre} - {modelo_interes}"[:500]
    if tabla == "procesos":
        valores["_referencia"] = valores.get("lead_id", "")
    elif tabla == "actividades-prospectos":
        valores["id_prospecto_original"] = texto_celda(leer_columna(fila, "Id. de prospecto"))
        valores["_referencia"] = valores["id_prospecto_original"]
    elif tabla == "actividades-procesos":
        valores["id_proceso_original"] = texto_celda(leer_columna(fila, "Id. del proceso comercial"))
        valores["_referencia"] = valores["id_proceso_original"]
    elif tabla in {"procesos-detalle", "facturas", "entregas"}:
        valores["_referencia"] = texto_celda(leer_columna(fila, "Id. del proceso comercial"))
    valores["datos_origen"] = {
        str(columna): texto_celda(contenido)
        for columna, contenido in fila.items() if texto_celda(contenido)
    }
    return clave, valores


def procesar_lote(tabla, lote, aplicar=False):
    modelo = TABLAS[tabla]["modelo"]
    existentes = modelo.objects.in_bulk([clave for _, clave, _ in lote])
    referencias = {valores.get("_referencia") for _, _, valores in lote if valores.get("_referencia")}
    ids_padre = set()
    ids_factura = set()
    if tabla in {"procesos", "actividades-prospectos"} and referencias:
        ids_padre = set(Prospecto.objects.filter(pk__in=referencias).values_list("pk", flat=True))
    if tabla in {"actividades-procesos", "procesos-detalle", "facturas", "entregas"} and referencias:
        ids_padre = set(ProcesoComercial.objects.filter(pk__in=referencias).values_list("pk", flat=True))
    if tabla == "entregas":
        ids_factura = set(FacturaComercial.objects.filter(pk__in=[clave for _, clave, _ in lote]).values_list("pk", flat=True))
    nuevos = []
    actualizados = []
    resultados = []
    ahora = timezone.now()
    for numero, clave, original in lote:
        valores = original.copy()
        referencia = valores.pop("_referencia", "")
        if tabla in {"procesos-detalle", "facturas", "entregas"} and referencia not in ids_padre:
            resultados.append((numero, clave, "error", "El proceso comercial relacionado no existe. Importa primero Procesos comerciales."))
            continue
        if tabla == "procesos-detalle":
            valores["proceso_id"] = referencia
        elif tabla in {"facturas", "entregas"}:
            valores["proceso_id"] = referencia
        elif tabla == "procesos":
            if referencia in ids_padre:
                valores["prospecto_id"] = referencia
        elif tabla == "actividades-prospectos":
            if referencia in ids_padre:
                valores["prospecto_id"] = referencia
        elif tabla == "actividades-procesos":
            if referencia in ids_padre:
                valores["proceso_id"] = referencia
        if tabla == "entregas" and clave in ids_factura:
            valores["factura_id"] = clave

        objeto = existentes.get(clave)
        if objeto is None:
            objeto = modelo(**valores)
            objeto.sincronizado_en = ahora
            nuevos.append(objeto)
            resultados.append((numero, clave, "nuevo", ""))
            continue
        cambiado = False
        for campo, valor in valores.items():
            if campo == "datos_origen":
                fusion = {**(objeto.datos_origen or {}), **valor}
                valor = fusion
            atributo = campo
            # Las relaciones se escriben mediante el atributo *_id.
            if getattr(objeto, atributo) != valor:
                setattr(objeto, atributo, valor)
                cambiado = True
        if cambiado:
            objeto.sincronizado_en = ahora
            actualizados.append(objeto)
        resultados.append((numero, clave, "actualizar" if cambiado else "sin_cambios", ""))

    if aplicar:
        if nuevos:
            modelo.objects.bulk_create(nuevos, batch_size=TAMANO_LOTE)
        if actualizados:
            campos = [c.name for c in modelo._meta.concrete_fields if not c.primary_key]
            modelo.objects.bulk_update(actualizados, campos, batch_size=150)
    return resultados


def resumen_vacio():
    return {"encontrados": 0, "nuevos": 0, "actualizar": 0, "sin_cambios": 0, "errores": 0,
            "detalle_errores": [], "vista_previa": []}


def procesar_archivo(archivo, tabla, aplicar=False):
    resumen = resumen_vacio()
    vistos = set()
    lote = []

    def terminar_lote():
        if not lote:
            return

        resultados = procesar_lote(tabla, lote, aplicar=aplicar)

        for numero, clave, estado, mensaje in resultados:
            if estado == "error":
                resumen["errores"] += 1

                if len(resumen["detalle_errores"]) < 30:
                    resumen["detalle_errores"].append({
                        "fila": numero,
                        "id": clave,
                        "error": mensaje
                    })
            else:
                clave_resumen = "nuevos" if estado == "nuevo" else estado
                resumen[clave_resumen] += 1

            for vista in resumen["vista_previa"]:
                if vista["_fila"] == numero:
                    vista["Estado"] = estado

        lote.clear()

    for numero, fila in iterar_filas(archivo, tabla):
        resumen["encontrados"] += 1

        if len(resumen["vista_previa"]) < 8:
            vista = {"_fila": numero}

            for columna, valor in list(fila.items())[:7]:
                vista[columna] = texto_celda(valor)

            resumen["vista_previa"].append(vista)

        try:
            clave, valores = preparar_fila(tabla, fila)

            if clave in vistos:
                raise ValueError(f"ID duplicado dentro del archivo: {clave}")

            vistos.add(clave)
            lote.append((numero, clave, valores))

        except (ValueError, TypeError, ErrorModelo) as exc:
            resumen["errores"] += 1

            if len(resumen["detalle_errores"]) < 30:
                resumen["detalle_errores"].append({
                    "fila": numero,
                    "error": str(exc)
                })

        if len(lote) >= TAMANO_LOTE:
            terminar_lote()

    terminar_lote()

    for vista in resumen["vista_previa"]:
        vista.pop("_fila", None)

    resumen["valido"] = resumen["encontrados"] > 0 and resumen["errores"] == 0

    return resumen

def huella_archivo(archivo):
    sha = hashlib.sha256()
    archivo.seek(0)
    for bloque in archivo.chunks(chunk_size=1024 * 1024):
        sha.update(bloque)
    archivo.seek(0)
    return sha.hexdigest()


def validar_archivo(archivo, tabla):
    archivo_legible(archivo)
    if tabla not in TABLAS:
        raise ValueError("La tabla seleccionada no existe.")
    resumen = procesar_archivo(archivo, tabla)
    resumen["huella"] = huella_archivo(archivo)
    return resumen


def importar_archivo(archivo, tabla, huella):
    if not huella or huella != huella_archivo(archivo):
        raise ValueError("El archivo no coincide con el validado. Vuelve a validarlo.")
    previo = validar_archivo(archivo, tabla)
    if not previo["valido"]:
        return previo
    # O todo el archivo se guarda o se revierte: nunca confirmar una carga parcial.
    with transaction.atomic():
        resultado = procesar_archivo(archivo, tabla, aplicar=True)
        if resultado["errores"]:
            raise ValueError("La importación encontró errores: se revirtieron todos los cambios.")
    return resultado
