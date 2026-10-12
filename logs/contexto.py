# logs/contexto.py
"""
Enriquecedores opcionales de logs.

Agregan contexto legible a los logs de modificación: en vez de
"Actualizó #123 en Digitales" producen algo como
"Actualizó el lead #123 · Juan Pérez · tel. 22... · Línea 552 · IA Vagen".

Cada resolver es opcional y nunca debe romper el request: cualquier
error se captura y devuelve None.
"""
import re

# Campos de "ruido" que no aportan al detalle de la acción.
CAMPOS_RUIDO = {
    "numero_asesor",
    "context",
    "csrfmiddlewaretoken",
    "_method",
}

_VALOR_MAX = 40


def _acortar(valor):
    texto = str(valor)
    if len(texto) > _VALOR_MAX:
        return texto[:_VALOR_MAX] + "…"
    return texto


def _resumen_campos(body, metodo):
    """Resumen de campos modificados, sin guardar el payload completo."""
    if not isinstance(body, dict) or not body:
        return ""

    if metodo == "POST":
        claves = [
            clave for clave in body
            if clave not in CAMPOS_RUIDO
        ][:8]
        if not claves:
            return ""
        return "Campos: " + ", ".join(claves)

    partes = []
    for clave, valor in list(body.items())[:8]:
        if clave in CAMPOS_RUIDO:
            continue
        partes.append(f"{clave} → {_acortar(valor)}")

    return "; ".join(partes)


def _lines_de_whatapp(numero_asesor):
    """Etiqueta legible de una línea de WhatsApp configurada."""
    numero = str(numero_asesor or "").strip()
    if not numero:
        return ""
    try:
        from Digitales.sett import WHATSAPP_LINES

        cfg = WHATSAPP_LINES.get(numero) or {}
    except Exception:
        cfg = {}

    partes = [f"Línea {numero}"]
    asesor = (cfg.get("asesor_digital") or "").strip()
    agencia = (cfg.get("agencia") or "").strip()
    business = (cfg.get("business") or "").strip()
    if asesor:
        partes.append(asesor)
    if agencia:
        partes.append(f"{agencia}{f' · {business}' if business else ''}")
    return " · ".join(partes)


def _contexto_digitales(path, metodo, body):
    m = re.match(r"^/digitales/api/prospectos/(\d+)/?", path or "")
    if not m:
        return None

    pk = int(m.group(1))

    try:
        from Digitales.models import ExpedienteDigital

        exp = (ExpedienteDigital.objects
               .select_related("cliente")
               .filter(id=pk)
               .first())
    except Exception:
        exp = None

    if exp is None:
        return None

    cliente = exp.cliente
    nombre = (cliente.nombre if cliente else "").strip() or "sin nombre"
    telefono = (cliente.telefono if cliente else "") or ""

    linea = ""
    numero_body = str((body or {}).get("numero_asesor") or "").strip()
    if numero_body:
        linea = _lines_de_whatapp(numero_body)
    else:
        try:
            from Digitales.models import MensajeWhatsApp

            numeros = list(
                MensajeWhatsApp.objects
                .filter(cliente_id=exp.cliente_id, numero_asesor__isnull=False)
                .order_by("-created_at")
                .values_list("numero_asesor", flat=True)
                .distinct()[:1]
            )
            if numeros:
                linea = _lines_de_whatapp(numeros[0])
        except Exception:
            linea = ""

    entidad = f"Lead #{pk} · {nombre}"
    if telefono:
        entidad += f" · tel. {telefono}"
    if linea:
        entidad += f" · {linea}"

    return {"entidad": entidad}


def _contexto_citas(path, metodo, body):
    m = re.match(r"^/citas/api/citas/(\d+)/?", path or "")
    if not m:
        return None

    pk = int(m.group(1))

    try:
        from citas.models import Cita

        cita = (Cita.objects
                .select_related("cliente")
                .filter(id=pk)
                .first())
    except Exception:
        cita = None

    if cita is None:
        return None

    cliente = cita.cliente
    nombre = (cliente.nombre if cliente else "").strip() or "sin nombre"
    telefono = (cliente.telefono if cliente else "") or ""

    entidad = f"Cita #{pk} · {nombre}"
    if telefono:
        entidad += f" · tel. {telefono}"
    if cita.asesor_digital:
        entidad += f" · {cita.asesor_digital}"

    return {"entidad": entidad}


def _contexto_documentacion(path, metodo, body):
    m_upload = re.match(
        r"^/documentacion/api/expedientes/(\d+)/documentos/", path or ""
    )
    m_delete = re.match(
        r"^/documentacion/api/documentos/(\d+)/", path or ""
    )

    if not (m_upload or m_delete):
        return None

    try:
        from documentacion.models import DocumentoExpediente, Expediente
    except Exception:
        return None

    if m_upload:
        expediente_id = int(m_upload.group(1))
        expediente = None
        try:
            expediente = Expediente.objects.filter(id=expediente_id).first()
        except Exception:
            expediente = None
        if expediente is None:
            return None
        cliente = (expediente.cliente or "").strip() or "sin cliente"
        return {
            "entidad": f"Expediente {expediente.folio} · {cliente}",
        }

    if m_delete:
        documento_id = int(m_delete.group(1))
        try:
            doc = (
                DocumentoExpediente.objects
                .select_related("expediente")
                .filter(id=documento_id)
                .first()
            )
        except Exception:
            doc = None
        if doc is None or not doc.expediente_id:
            return None
        cliente = (doc.expediente.cliente or "").strip() or "sin cliente"
        requisito = (doc.requisito_nombre or "").strip() or "documento"
        return {
            "entidad": f"Expediente {doc.expediente.folio} · {cliente} · {requisito}",
        }

    return None


_RESOLVERES = [
    _contexto_digitales,
    _contexto_citas,
    _contexto_documentacion,
]


def contexto(*, path, metodo, body):
    """Devuelve detalle enriquecido (entidad/campos) o un dict vacío."""
    resumen = _resumen_campos(body, metodo)

    entidad_extra = None
    for resolver in _RESOLVERES:
        try:
            dato = resolver(path, metodo, body)
        except Exception:
            dato = None
        if dato and dato.get("entidad"):
            entidad_extra = dato["entidad"]
            break

    return {
        "entidad": entidad_extra or "",
        "resumen": resumen,
    }