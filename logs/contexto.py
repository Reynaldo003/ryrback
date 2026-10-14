# logs/contexto.py
"""
Enriquecedores opcionales de logs.

Agregan contexto legible a los logs de modificación: en vez de
"Actualizó #123 en Digitales" producen algo como
"Actualizó el lead #123 · Juan Pérez · tel. 22... · Línea 552 · IA Vagen".

Incluye resolvers para envíos de WhatsApp (plantilla/texto/media), que
describen qué se envió y a quién, y `snapshot_entidad()` para capturar la
foto de un registro ANTES de que un DELETE lo elimine (el middleware lo
llama en process_view, cuando el objeto aún existe).

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


def _acortar(valor, maximo=_VALOR_MAX):
    texto = str(valor)
    if len(texto) > maximo:
        return texto[:maximo] + "…"
    return texto


def _digitos_10(valor):
    """Últimos 10 dígitos de un teléfono (los guardados empiezan con 52)."""
    dig = "".join(c for c in str(valor or "") if c.isdigit())
    if len(dig) > 10:
        dig = dig[-10:]
    return dig if len(dig) == 10 else ""


def _cliente_por_telefono(valor):
    """(nombre, telefono) del ClienteComercial según el `to` del request.

    Devuelve nombre=None si no hay cliente o no tiene nombre (para que el
    destino caiga a mostrar el teléfono en vez de "sin nombre").
    """
    dig10 = _digitos_10(valor)
    if not dig10:
        return None, ""
    try:
        from citas.models import ClienteComercial

        cli = (ClienteComercial.objects
               .filter(telefono__endswith=dig10)
               .order_by("-actualizado_en")
               .first())
    except Exception:
        cli = None
    if cli is None:
        return None, ""
    nombre = (getattr(cli, "nombre", "") or "").strip() or None
    return nombre, (getattr(cli, "telefono", "") or "")


def _fecha_corta(valor):
    """Fecha legible corta: 14/10/2026 10:30 (o cadena vacía)."""
    try:
        if valor is None:
            return ""
        return valor.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return ""


def _destino_whatsapp(body):
    """(destino, tel_txt, linea) legibles para un envío por WhatsApp."""
    body = body or {}
    nombre, telefono = _cliente_por_telefono(body.get("to"))
    to_crudo = str(body.get("to") or "").strip()
    if nombre:
        destino = nombre
        tel_txt = (
            f" · tel. {telefono}" if telefono
            else (f" · tel. {to_crudo}" if to_crudo else "")
        )
    elif telefono or to_crudo:
        destino = f"tel. {telefono or to_crudo}"
        tel_txt = ""
    else:
        destino = "destinatario"
        tel_txt = ""

    linea = ""
    numero_body = str(body.get("numero_asesor") or "").strip()
    if numero_body:
        linea = _lines_de_whatapp(numero_body)

    return destino, tel_txt, linea


def _params_plantilla(body):
    """Texto corto con los parámetros de una plantilla (params o components)."""
    vals = []
    try:
        comps = (body or {}).get("components")
        if isinstance(comps, list):
            for comp in comps:
                if not isinstance(comp, dict):
                    continue
                for p in (comp.get("parameters") or []):
                    if (isinstance(p, dict) and p.get("type") == "text"
                            and p.get("text")):
                        vals.append(str(p.get("text")))
        if not vals:
            params = (body or {}).get("params")
            if isinstance(params, list):
                vals = [str(x) for x in params if str(x).strip()]
    except Exception:
        vals = []
    vals = [v for v in vals if v]
    if not vals:
        return ""
    recorte = [_acortar(v, 30) for v in vals[:3]]
    texto = " | ".join(f'"{v}"' for v in recorte)
    if len(vals) > 3:
        texto += f" (+{len(vals) - 3})"
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


def _entidad_cita(pk):
    """Descripción completa de una cita (sirve pre y post modificación)."""
    try:
        from citas.models import Cita

        cita = (Cita.objects
                .select_related("cliente")
                .filter(id=pk)
                .first())
    except Exception:
        return ""

    if cita is None:
        return ""

    cliente = cita.cliente
    nombre = ((getattr(cliente, "nombre", "") or "").strip()) or "sin nombre"
    telefono = (getattr(cliente, "telefono", "") or "")

    partes = [f"Cita #{pk}", nombre]
    if telefono:
        partes.append(f"tel. {telefono}")
    fecha = _fecha_corta(getattr(cita, "fecha_hora_cita", None))
    if fecha:
        partes.append(fecha)
    detalle = " / ".join(p for p in [
        (getattr(cita, "tipo_cita", "") or "").strip(),
        (getattr(cita, "motivo_cita", "") or "").strip(),
    ] if p)
    if detalle:
        partes.append(detalle)
    asesor = (getattr(cita, "asesor_digital", "") or "").strip()
    if asesor:
        partes.append(asesor)

    return " · ".join(partes)


def _entidad_entrega(pk):
    """Descripción completa de una entrega (sirve pre y post modificación)."""
    try:
        from citas.models import Entregas

        ent = (Entregas.objects
               .select_related("cliente")
               .filter(id=pk)
               .first())
    except Exception:
        return ""

    if ent is None:
        return ""

    cliente = ent.cliente
    nombre = ((getattr(cliente, "nombre", "") or "").strip()) or "sin nombre"
    telefono = (getattr(cliente, "telefono", "") or "")

    partes = [f"Entrega #{pk}", nombre]
    if telefono:
        partes.append(f"tel. {telefono}")
    fecha = _fecha_corta(getattr(ent, "fecha_hora_entrega", None))
    if fecha:
        partes.append(fecha)
    modelo = " ".join(p for p in [
        (getattr(ent, "modelo_version", "") or "").strip(),
        (getattr(ent, "version", "") or "").strip(),
        (getattr(ent, "color", "") or "").strip(),
    ] if p)
    if modelo:
        partes.append(modelo)
    asesor = (getattr(ent, "asesor_ventas", "") or "").strip()
    if asesor:
        partes.append(asesor)

    return " · ".join(partes)


def _entidad_registro_piso(pk):
    """Descripción completa de un registro de piso."""
    try:
        from citas.models import RegistroPiso

        reg = (RegistroPiso.objects
               .select_related("cliente")
               .filter(id=pk)
               .first())
    except Exception:
        return ""

    if reg is None:
        return ""

    cliente = reg.cliente
    nombre = ((getattr(cliente, "nombre", "") or "").strip()) or "sin nombre"
    telefono = (getattr(cliente, "telefono", "") or "")

    partes = [f"Registro piso #{pk}", nombre]
    if telefono:
        partes.append(f"tel. {telefono}")
    fecha = _fecha_corta(getattr(reg, "fecha_hora_cita", None))
    if fecha:
        partes.append(fecha)
    auto = (getattr(reg, "auto_interes", "") or "").strip()
    if auto:
        partes.append(auto)
    asesor = (getattr(reg, "asesor_piso", "") or "").strip()
    if asesor:
        partes.append(asesor)

    return " · ".join(partes)


def _entidad_prueba_manejo(pk):
    """Descripción completa de una prueba de manejo."""
    try:
        from citas.models import PruebaManejo

        pm = (PruebaManejo.objects
              .select_related("cliente")
              .filter(id=pk)
              .first())
    except Exception:
        return ""

    if pm is None:
        return ""

    cliente = pm.cliente
    nombre = ((getattr(cliente, "nombre", "") or "").strip()) or "sin nombre"
    telefono = (getattr(cliente, "telefono", "") or "")

    partes = [f"Prueba de manejo #{pk}", nombre]
    if telefono:
        partes.append(f"tel. {telefono}")
    fecha = _fecha_corta(getattr(pm, "fecha_hora_cita", None))
    if fecha:
        partes.append(fecha)
    auto = (getattr(pm, "auto_interes", "") or "").strip()
    if auto:
        partes.append(auto)
    folio = (getattr(pm, "folio_salida", "") or "").strip()
    if folio:
        partes.append(f"folio {folio}")

    return " · ".join(partes)


_RE_CITA_DETALLE = re.compile(
    r"^/citas/api/(citas|entregas|registro-piso|pruebas-manejo)/(\d+)/?"
)


def _entidad_recurso_citas(recurso, pk):
    """Despacha al builder según el recurso de citas/ (citas y hermanos)."""
    if recurso == "citas":
        return _entidad_cita(pk)
    if recurso == "entregas":
        return _entidad_entrega(pk)
    if recurso == "registro-piso":
        return _entidad_registro_piso(pk)
    if recurso == "pruebas-manejo":
        return _entidad_prueba_manejo(pk)
    return ""


def _contexto_citas(path, metodo, body):
    m = _RE_CITA_DETALLE.match(path or "")
    if not m:
        return None

    entidad = _entidad_recurso_citas(m.group(1), int(m.group(2)))
    return {"entidad": entidad} if entidad else None


_RE_MENSAJE_PLANTILLA = re.compile(r"^/digitales/(api/)?mensajes/enviar-plantilla/?")
_RE_MENSAJE_MEDIA = re.compile(r"^/digitales/(api/)?mensajes/enviar-media/?")
_RE_MENSAJE_TEXTO = re.compile(r"^/digitales/(api/)?mensajes/enviar/?$")


def _contexto_mensajes_digitales(path, metodo, body):
    """Describe envíos de WhatsApp: qué se envió y a quién.

    Cubre enviar-plantilla (to/template_name/idioma/params-components),
    enviar-media (to/text como caption + archivos) y enviar (to/text).
    """
    if metodo != "POST":
        return None
    body = body or {}
    path = path or ""

    if _RE_MENSAJE_PLANTILLA.match(path):
        template = str(body.get("template_name") or "").strip() or "sin nombre"
        idioma = str(body.get("idioma") or "").strip() or "es_MX"
        destino, tel_txt, linea = _destino_whatsapp(body)

        entidad = f"Plantilla '{template}' → {destino}"
        accion = (
            f"Envió plantilla '{template}' a {destino}"
            f"{tel_txt} · idioma {idioma}"
        )
        params_txt = _params_plantilla(body)
        if params_txt:
            accion += f" · params: {params_txt}"
        if linea:
            accion += f" · {linea}"
        return {"entidad": entidad, "accion": accion, "resumen": ""}

    if _RE_MENSAJE_MEDIA.match(path):
        caption = str(body.get("text") or "").strip()
        destino, tel_txt, linea = _destino_whatsapp(body)

        entidad = f"WhatsApp → {destino}"
        accion = f"Envió archivo a {destino}{tel_txt}"
        if caption:
            accion += f': "{_acortar(caption, 60)}"'
        if linea:
            accion += f" · {linea}"
        return {"entidad": entidad, "accion": accion, "resumen": ""}

    if _RE_MENSAJE_TEXTO.match(path):
        texto = str(body.get("text") or "").strip()
        destino, tel_txt, linea = _destino_whatsapp(body)

        entidad = f"WhatsApp → {destino}"
        accion = f"Envió mensaje a {destino}{tel_txt}"
        if texto:
            accion += f': "{_acortar(texto, 60)}"'
        if linea:
            accion += f" · {linea}"
        return {"entidad": entidad, "accion": accion, "resumen": ""}

    return None


def _entidad_documento(documento_id):
    """Descripción de un documento (sirve pre y post borrado)."""
    try:
        from documentacion.models import DocumentoExpediente

        doc = (
            DocumentoExpediente.objects
            .select_related("expediente")
            .filter(id=documento_id)
            .first()
        )
    except Exception:
        return ""
    if doc is None or not doc.expediente_id:
        return ""
    cliente = (doc.expediente.cliente or "").strip() or "sin cliente"
    requisito = (doc.requisito_nombre or "").strip() or "documento"
    nombre = (doc.nombre_original or "").strip()
    entidad = f"Expediente {doc.expediente.folio} · {cliente} · {requisito}"
    if nombre:
        entidad += f" · {nombre}"
    return entidad


def _contexto_documentacion(path, metodo, body):
    m_upload = re.match(
        r"^/documentacion/api/expedientes/(\d+)/documentos/", path or ""
    )
    m_delete = re.match(
        r"^/documentacion/api/documentos/(\d+)/", path or ""
    )

    if not (m_upload or m_delete):
        return None

    if m_upload:
        expediente_id = int(m_upload.group(1))
        try:
            from documentacion.models import Expediente

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
        entidad = _entidad_documento(int(m_delete.group(1)))
        return {"entidad": entidad} if entidad else None

    return None


_RESOLVERES = [
    _contexto_mensajes_digitales,
    _contexto_digitales,
    _contexto_citas,
    _contexto_documentacion,
]


def snapshot_entidad(path):
    """Foto de la entidad ANTES de un DELETE (el objeto ya no existe después).

    El middleware lo llama en process_view, cuando el registro aún está en
    la BD. Devuelve la descripción o "" si no hay nada que capturar.
    """
    path = path or ""

    m = _RE_CITA_DETALLE.match(path)
    if m:
        return _entidad_recurso_citas(m.group(1), int(m.group(2)))

    m = re.match(r"^/documentacion/api/documentos/(\d+)/", path)
    if m:
        return _entidad_documento(int(m.group(1)))

    m = re.match(r"^/digitales/api/prospectos/(\d+)/?", path)
    if m:
        try:
            dato = _contexto_digitales(path, "DELETE", {}) or {}
            return dato.get("entidad") or ""
        except Exception:
            return ""

    return ""


def contexto(*, path, metodo, body, snapshot_entidad=""):
    """Devuelve detalle enriquecido (entidad/resumen/acción) o dict vacío.

    `snapshot_entidad` es la foto pre-borrado (solo DELETE): se usa cuando
    los resolvers ya no encuentran el objeto.
    """
    resumen = _resumen_campos(body, metodo)

    entidad_extra = None
    accion_extra = None
    for resolver in _RESOLVERES:
        try:
            dato = resolver(path, metodo, body)
        except Exception:
            dato = None
        if not dato:
            continue
        if dato.get("entidad"):
            entidad_extra = dato["entidad"]
        if "resumen" in dato:
            resumen = dato.get("resumen") or ""
        if dato.get("accion"):
            accion_extra = dato["accion"]
        if dato.get("entidad"):
            break

    if not entidad_extra and snapshot_entidad:
        entidad_extra = snapshot_entidad

    return {
        "entidad": entidad_extra or "",
        "resumen": resumen,
        "accion": accion_extra or "",
    }