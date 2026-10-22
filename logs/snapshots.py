# logs/snapshots.py
"""
Captura y restauración de snapshots de registros eliminados.

Cuando un DELETE borra un registro, en `process_view` (antes de que la
vista corra) se guarda aquí una foto completa del objeto —y de sus hijos
que se borran en cascada— en el campo `datos` del LogActividad. Con esa
foto, el comando `python manage.py restaurarlog <log_id>` puede recrear
lo eliminado con un solo comando.

Nota: los archivos físicos (FileField) no se guardan en el snapshot; solo
el nombre. Si el borrado también destruyó el archivo del storage hay que
re-subirlo a mano (el comando lo avisa).
"""
import re
from decimal import Decimal

from django.apps import apps
from django.db import transaction
from django.db.models.fields.files import FieldFile

# (regex del path, "app.Model", [(hijo "app.Model", fk_campo_attname), ...])
# Orden importa: los patrones más específicos van antes que los generales.
_RUTAS = [
    (
        r"^/digitales/api/prospectos/\d+/evidencias/(\d+)/",
        "Digitales.EvidenciaProspectoDigital",
        [],
    ),
    (
        r"^/digitales/api/prospectos/(\d+)/",
        "Digitales.ExpedienteDigital",
        [
            ("Digitales.EvidenciaProspectoDigital", "expediente_id"),
            ("Digitales.InteresVehiculoProspecto", "expediente_id"),
            ("Digitales.LecturaWhatsApp", "expediente_id"),
            ("Digitales.BloqueoWhatsAppLinea", "expediente_id"),
        ],
    ),
    (
        r"^/digitales/api/respuestas-rapidas/(\d+)/",
        "Digitales.RespuestaRapidaAsesor",
        [],
    ),
    (r"^/citas/api/citas/(\d+)/", "citas.Cita", []),
    (r"^/citas/api/registro-piso/(\d+)/", "citas.RegistroPiso", []),
    (
        r"^/citas/api/pruebas-manejo/(\d+)/",
        "citas.PruebaManejo",
        [("citas.EvidenciaPruebaManejo", "prueba_manejo_id")],
    ),
    (r"^/citas/api/entregas/(\d+)/", "citas.Entregas", []),
    (r"^/citas/api/clientes-comerciales/(\d+)/", "citas.ClienteComercial", []),
    (
        r"^/conformidad/api/casos/(\d+)/",
        "CrmConformidad.ExpedienteConformidad",
        [("CrmConformidad.ExpedienteDocumento", "expediente_id")],
    ),
    (r"^/conformidad/api/docs/(\d+)/", "CrmConformidad.ExpedienteDocumento", []),
    (r"^/documentacion/api/documentos/(\d+)/", "documentacion.DocumentoExpediente", []),
    (
        r"^/documentacion/api/expedientes/(\d+)/",
        "documentacion.Expediente",
        [("documentacion.DocumentoExpediente", "expediente_id")],
    ),
    (
        r"^/usados/api/avaluos/(\d+)/",
        "usados.AvaluoUsado",
        [
            ("usados.AvaluoUsadoEvidencia", "avaluo_id"),
            ("usados.ConceptoAvaluo", "avaluo_id"),
        ],
    ),
    (
        r"^/api/pedidos-piezas/pedidos/(\d+)/",
        "PedidosPiezas.PedidosPiezas",
        [("PedidosPiezas.PedidoPiezaDetalle", "pedido_id")],
    ),
    (r"^/api/pedidos-piezas/piezas/(\d+)/", "PedidosPiezas.Piezas", []),
    (
        r"^/api/safety/reportes/(\d+)/",
        "Safety.ReporteSafety",
        [("Safety.AdjuntoReporteSafety", "reporte_id")],
    ),
    (
        r"^/gestion_inversion/api/facturas/(\d+)/",
        "gestion_inversion.FacturaMarketing",
        [("gestion_inversion.ConceptoFactura", "factura_id")],
    ),
    (
        r"^/api/rrhh/vacantes/(\d+)/",
        "rrhh.VacanteReclutamiento",
        [("rrhh.CandidatoReclutamiento", "vacante_id")],
    ),
    (
        r"^/api/rrhh/puestos/(\d+)/",
        "rrhh.Puesto",
        [("rrhh.EvaluacionPuesto", "puesto_id")],
    ),
    (
        r"^/hojaingresos/api/hoja-ingresos/\d+/evidencias/(\d+)/",
        "hojaingresos.HojaIngresoEvidencia",
        [],
    ),
    (
        r"^/hojaingresos/api/hoja-ingresos/(\d+)/",
        "hojaingresos.HojaIngresos",
        [],
    ),
    (
        r"^/api/clickup/equipos/\d+/tablero/tareas/(\d+)/eliminar/",
        "clickup.Tarea",
        [
            ("clickup.TareaAsignada", "tarea_id"),
            ("clickup.EvidenciaTarea", "tarea_id"),
            ("clickup.Tarea", "tarea_padre_id"),
        ],
    ),
    (
        r"^/api/clickup/equipos/\d+/proyectos/(\d+)/",
        "clickup.Proyecto",
        [],
    ),
    (
        r"^/api/clickup/equipos/(\d+)/$",
        "clickup.Equipo",
        [
            ("clickup.MiembroEquipo", "equipo_id"),
            ("clickup.InvitacionEquipo", "equipo_id"),
        ],
    ),
    (
        r"^/business-plan/api/temas/(\d+)/",
        "BusinessPlan.Tema",
        [
            ("BusinessPlan.ColaboradorTema", "tema_id"),
            ("BusinessPlan.DatosTemaAnual", "tema_id"),
        ],
    ),
    (
        r"^/business-plan/api/tableros/(\d+)/",
        "BusinessPlan.Tablero",
        [],
    ),
]

# Campos sugeridos para la descripción legible (en orden de preferencia).
_CAMPOS_DESCRIPCION = (
    "nombre",
    "titulo",
    "name",
    "folio",
    "numero_pedido",
    "numero_parte",
    "codigo",
)


def _valor_serializable(valor):
    """Convierte un valor de campo a algo JSON-safe (y reversible)."""
    if valor is None or isinstance(valor, (bool, int, float, str)):
        return valor
    if isinstance(valor, Decimal):
        return str(valor)
    if hasattr(valor, "isoformat"):  # date, datetime, time
        return valor.isoformat()
    if hasattr(valor, "hex") and not isinstance(valor, (bytes, bytearray)):  # UUID
        return str(valor)
    # FieldFile: solo el nombre (nunca tocar `.file`, que intenta abrir el
    # archivo físico y explota si ya no existe en disco).
    if isinstance(valor, FieldFile):
        return valor.name or ""
    nombre = getattr(valor, "name", None)
    if nombre is not None and isinstance(nombre, str):
        return nombre
    if isinstance(valor, (bytes, bytearray)):
        return None
    return str(valor)


def _serializar_objeto(obj):
    """Todos los campos concretos del objeto, serializados de forma reversible."""
    campos = {}
    for field in obj._meta.concrete_fields:
        campos[field.attname] = _valor_serializable(getattr(obj, field.attname))
    return campos


def _modelo(app_label, nombre):
    return apps.get_model(app_label, nombre)


def _modelo_desde_string(ref):
    app_label, nombre = ref.split(".", 1)
    return _modelo(app_label, nombre)


def descripcion_de(obj):
    """Descripción legible de una instancia: "Cita #42 · Juan Pérez · tel. ..."."""
    partes = [f"{obj._meta.object_name} #{obj.pk}"]
    for campo in _CAMPOS_DESCRIPCION:
        valor = getattr(obj, campo, None)
        if isinstance(valor, str) and valor.strip():
            partes.append(valor.strip())
            break

    telefono = getattr(obj, "telefono", None)
    if isinstance(telefono, str) and telefono.strip():
        partes.append(telefono.strip())
    else:
        cliente_id = getattr(obj, "cliente_id", None)
        if cliente_id is not None:
            partes.append(f"cliente #{cliente_id}")

    return " · ".join(partes)


def snapshot_instancia(obj, hijos=None):
    """Foto completa de una instancia (y opcionalmente de hijos por cascada).

    `hijos` es una lista de (modelo_ref, fk_campo_attname). Cada hijo se
    serializa con su relación apuntando al padre (se restaura después).
    """
    datos = {
        "modelo": f"{obj._meta.app_label}.{obj._meta.object_name}",
        "pk": obj.pk,
        "descripcion": descripcion_de(obj),
        "campos": _serializar_objeto(obj),
        "hijos": [],
    }

    for ref, fk_campo in (hijos or []):
        try:
            modelo_hijo = _modelo_desde_string(ref)
            registros = []
            for hijo in modelo_hijo.objects.filter(**{fk_campo: obj.pk}):
                campos = _serializar_objeto(hijo)
                registros.append({"pk": hijo.pk, "campos": campos})
            datos["hijos"].append(
                {"modelo": ref, "fk_campo": fk_campo, "registros": registros}
            )
        except Exception:
            continue

    return datos


def capturar_snapshot(path):
    """Foto del registro que un DELETE está a punto de borrar (o None).

    El middleware la llama en process_view, cuando el objeto aún existe.
    """
    path = path or ""
    for patron, ref, hijos in _RUTAS:
        m = re.match(patron, path)
        if not m:
            continue
        try:
            modelo = _modelo_desde_string(ref)
            obj = modelo.objects.filter(pk=int(m.group(1))).first()
            if obj is None:
                return None
            return snapshot_instancia(obj, hijos=hijos)
        except Exception:
            return None
    return None


def restaurar_snapshot(datos):
    """Recrea el registro (y sus hijos) a partir del snapshot.

    Devuelve (ok, lista_de_mensajes). Nunca lanza excepciones.
    """
    mensajes = []
    if not isinstance(datos, dict) or not datos.get("modelo") or not datos.get("campos"):
        return False, ["El log no tiene snapshot restaurable (campo `datos` vacío)."]

    if datos.get("purgado"):
        return False, [
            "Este registro fue purgado definitivamente (retención vencida); "
            "no se puede restaurar."
        ]

    try:
        modelo = _modelo_desde_string(datos["modelo"])
    except Exception:
        return False, [f"No se encontró el modelo {datos.get('modelo')!r}."]

    pk_nombre = modelo._meta.pk.attname
    pk = datos.get("pk") or datos["campos"].get(pk_nombre)

    if pk and modelo.objects.filter(pk=pk).exists():
        existente = modelo.objects.get(pk=pk)

        # Soft delete (p. ej. documentación): el registro existe pero está
        # marcado como eliminado. Restaurarlo = limpiar la marca; el archivo
        # físico nunca se borró.
        if getattr(existente, "eliminado", None) is not None:
            try:
                existente.eliminado = None
                existente.save(update_fields=["eliminado"])
                return True, [
                    f"Restaurado {modelo._meta.object_name} #{pk} "
                    "(se revirtió la eliminación; el archivo sigue disponible)."
                ]
            except Exception as exc:
                return False, [f"Error al restaurar: {exc}"]

        return False, [
            f"El registro {modelo._meta.object_name} #{pk} ya existe en la BD "
            "(quizá ya fue restaurado)."
        ]

    campos = _campos_actuales(modelo, datos["campos"])
    campos[pk_nombre] = pk

    archivos = [
        nombre for nombre, valor in campos.items()
        if _es_campo_archivo(modelo, nombre) and valor
    ]

    try:
        with transaction.atomic():
            obj = modelo.objects.create(**campos)
            hijos_ok = 0
            for hijo in datos.get("hijos") or []:
                hijos_ok += _restaurar_hijos(modelo, obj, hijo, mensajes)
            mensajes.insert(
                0,
                f"Restaurado {modelo._meta.object_name} #{obj.pk}"
                + (f" (+{hijos_ok} registro(s) hijo(s))." if hijos_ok else "."),
            )
    except Exception as exc:
        return False, [f"Error al restaurar: {exc}"]

    if archivos:
        mensajes.append(
            "AVISO: el(los) archivo(s) físico(s) no se restauran "
            f"({', '.join(archivos)}); re-súbelo(s) desde la interfaz."
        )

    return True, mensajes


def _restaurar_hijos(modelo_padre, obj, hijo, mensajes):
    try:
        modelo_hijo = _modelo_desde_string(hijo["modelo"])
    except Exception:
        mensajes.append(f"No se encontró el modelo hijo {hijo.get('modelo')!r}.")
        return 0

    fk_campo = hijo["fk_campo"]
    pk_hijo = modelo_hijo._meta.pk.attname
    creados = 0

    for registro in hijo.get("registros") or []:
        campos = _campos_actuales(modelo_hijo, registro.get("campos") or {})
        campos[fk_campo] = obj.pk
        try:
            if registro.get("pk") and not modelo_hijo.objects.filter(
                pk=registro["pk"]
            ).exists():
                campos[pk_hijo] = registro["pk"]
            modelo_hijo.objects.create(**campos)
            creados += 1
        except Exception:
            try:
                modelo_hijo.objects.create(**campos)
                creados += 1
            except Exception as exc:
                mensajes.append(
                    f"No se pudo restaurar hijo {hijo['modelo']} "
                    f"#{registro.get('pk')}: {exc}"
                )
    return creados


def _campos_actuales(modelo, campos):
    """Fila del snapshot filtrada a los campos que existen hoy en el modelo.

    Protege contra cambios de esquema posteriores al borrado.
    """
    validos = {f.attname: f for f in modelo._meta.concrete_fields}
    resultado = {}
    for nombre, valor in (campos or {}).items():
        if nombre in validos:
            resultado[nombre] = valor
    return resultado


def _es_campo_archivo(modelo, attname):
    try:
        campo = modelo._meta.get_field(attname[:-3] if attname.endswith("_id") else attname)
    except Exception:
        return False
    return campo.__class__.__name__ in ("FileField", "ImageField")
