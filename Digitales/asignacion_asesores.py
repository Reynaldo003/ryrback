from __future__ import annotations

from django.db import transaction
from django.db.models import Q
import unicodedata

from CrmConformidad.models import Usuario
from django.utils import timezone

from citas.models import normaliza_tel_mx

from .models import (
    ControlRepartoWhatsApp,
    ExpedienteDigital,
)
from .sett import WHATSAPP_LINES


def _texto(valor) -> str:
    return str(valor or "").strip()

def _normalizar_usuario(valor) -> str:
    return _texto(valor).casefold()

def _clave(texto) -> str:
    """Compara nombres y agencias sin diferencias de acentos y mayúsculas."""
    valor = unicodedata.normalize("NFKD", _texto(texto))
    return " ".join("".join(c for c in valor if not unicodedata.combining(c)).casefold().split())


def _agencias_admitidas(agencias) -> set[str]:
    declaradas = {_clave(x) for x in _texto(agencias).split("|") if x.strip()}
    permisos = set(declaradas)
    if "vw cordoba" in declaradas:
        permisos.add("vw cordoba usados")
    if "vw orizaba" in declaradas:
        permisos.add("vw orizaba usados")
    return permisos


def resolver_usuario_crm_por_linea(numero_asesor: str, nombre_asesor: str, agencia: str) -> str:
    """Cuenta CRM inequívoca para un asesor nombrado en una línea configurada.

    Ningún nombre libre da acceso por sí solo: se verifica la línea conocida,
    la agencia, su responsable configurado, un rol de asesor y UNA sola cuenta
    CRM cuyo nombre completo coincide. No escribe datos ni reasigna registros.
    """
    numero = normaliza_tel_mx(numero_asesor or "")
    configuracion = WHATSAPP_LINES.get(numero)
    nombre = _clave(nombre_asesor)
    agencia_clave = _clave(agencia)
    if not isinstance(configuracion, dict) or not nombre or not agencia_clave:
        return ""
    if agencia_clave not in _agencias_admitidas(configuracion.get("agencia")):
        return ""

    asesores = obtener_asesores_activos(numero)
    login_configurado = ""
    if asesores:
        coincidencias = [a for a in asesores if _clave(a["nombre"]) == nombre]
        if len(coincidencias) != 1:
            return ""
        login_configurado = _normalizar_usuario(coincidencias[0]["usuario"])
    elif _clave(configuracion.get("asesor_digital")) != nombre:
        return ""

    candidatos = []
    cuentas = Usuario.objects.select_related("rol").filter(
        Q(rol__nombre__iexact="Asesor Digital") |
        Q(rol__nombre__iexact="Asesor General")
    )
    for cuenta in cuentas:
        if _clave(f"{cuenta.nombre or ''} {cuenta.apellidos or ''}") != nombre:
            continue
        if agencia_clave not in _agencias_admitidas(cuenta.agencia):
            continue
        if login_configurado and _normalizar_usuario(cuenta.usuario) != login_configurado:
            continue
        candidatos.append(_texto(cuenta.usuario))
        if len(candidatos) > 1:
            return ""
    return candidatos[0] if len(candidatos) == 1 else ""


def obtener_asesores_activos(
    numero_asesor: str,
) -> list[dict]:
    numero_asesor = normaliza_tel_mx(
        numero_asesor or ""
    )

    configuracion = WHATSAPP_LINES.get(
        numero_asesor,
        {},
    )

    asesores = []

    for item in configuracion.get("asesores") or []:
        if not isinstance(item, dict):
            continue

        usuario = _texto(item.get("usuario"))
        nombre = _texto(item.get("nombre"))
        activo = bool(item.get("activo", True))

        if not usuario or not nombre or not activo:
            continue

        asesores.append({
            "usuario": usuario,
            "nombre": nombre,
        })

    return asesores


def linea_tiene_reparto(
    numero_asesor: str,
) -> bool:
    return len(
        obtener_asesores_activos(numero_asesor)
    ) > 1


def obtener_asesor_por_usuario(
    numero_asesor: str,
    usuario: str,
) -> dict | None:
    usuario_normalizado = _normalizar_usuario(
        usuario
    )

    if not usuario_normalizado:
        return None

    for asesor in obtener_asesores_activos(
        numero_asesor
    ):
        if (
            _normalizar_usuario(asesor["usuario"])
            == usuario_normalizado
        ):
            return asesor

    return None


def obtener_asesor_por_nombre(
    numero_asesor: str,
    nombre: str,
) -> dict | None:
    nombre_normalizado = _texto(nombre).casefold()

    if not nombre_normalizado:
        return None

    for asesor in obtener_asesores_activos(
        numero_asesor
    ):
        if (
            _texto(asesor["nombre"]).casefold()
            == nombre_normalizado
        ):
            return asesor

    return None


@transaction.atomic
def asegurar_asignacion_expediente(
    expediente: ExpedienteDigital,
    numero_asesor: str,
) -> ExpedienteDigital:
    """
    Asigna el prospecto una sola vez.

    En líneas compartidas utiliza round-robin.
    En líneas normales mantiene el asesor configurado
    en WHATSAPP_LINES.
    """
    numero_asesor = normaliza_tel_mx(
        numero_asesor or ""
    )

    if not expediente or not expediente.pk:
        return expediente

    expediente = (
        ExpedienteDigital.objects
        .select_for_update()
        .get(pk=expediente.pk)
    )

    configuracion = WHATSAPP_LINES.get(
        numero_asesor,
        {},
    )

    asesores = obtener_asesores_activos(
        numero_asesor
    )

    # Línea individual: resolver y GUARDAR el usuario CRM de forma automática.
    # Si hay dueño explícito o un nombre histórico diferente, no sobreescribir.
    if not asesores:
        asesor_linea = _texto(configuracion.get("asesor_digital"))
        nombre_actual = _texto(expediente.asesor_digital)
        if not asesor_linea or (nombre_actual and _clave(nombre_actual) != _clave(asesor_linea)):
            return expediente
        if _texto(expediente.usuario_crm_asignado):
            return expediente

        login = resolver_usuario_crm_por_linea(numero_asesor, asesor_linea, expediente.agencia)
        cambios = []
        if not nombre_actual:
            expediente.asesor_digital = asesor_linea
            cambios.append("asesor_digital")
        if login:
            expediente.usuario_crm_asignado = login
            cambios.append("usuario_crm_asignado")
            if not expediente.asignado_automaticamente_at:
                expediente.asignado_automaticamente_at = timezone.now()
                cambios.append("asignado_automaticamente_at")
        if cambios:
            expediente.save(update_fields=[*cambios, "actualizado"])
        return expediente

    # Ya tiene una cuenta válida asignada.
    usuario_actual = _normalizar_usuario(
        expediente.usuario_crm_asignado
    )

    for asesor in asesores:
        if (
            _normalizar_usuario(asesor["usuario"])
            == usuario_actual
        ):
            cambios = []

            if (
                expediente.asesor_digital
                != asesor["nombre"]
            ):
                expediente.asesor_digital = (
                    asesor["nombre"]
                )
                cambios.append("asesor_digital")

            if cambios:
                cambios.append("actualizado")
                expediente.save(
                    update_fields=cambios
                )

            return expediente

    # Compatibilidad con expedientes anteriores:
    # intenta reconocer al asesor por el nombre.
    asesor_legacy = obtener_asesor_por_nombre(
        numero_asesor,
        expediente.asesor_digital,
    )

    if asesor_legacy:
        expediente.usuario_crm_asignado = (
            asesor_legacy["usuario"]
        )

        if not expediente.asignado_automaticamente_at:
            expediente.asignado_automaticamente_at = (
                timezone.now()
            )

        expediente.save(
            update_fields=[
                "usuario_crm_asignado",
                "asignado_automaticamente_at",
                "actualizado",
            ]
        )

        return expediente

    # Un histórico con asesor escrito pero NO presente en el reparto vigente
    # no debe pasar silenciosamente al siguiente asesor por round-robin.
    if _texto(expediente.asesor_digital):
        return expediente

    # Control bloqueado para evitar asignaciones duplicadas
    # cuando llegan dos webhooks al mismo tiempo.
    control, _ = (
        ControlRepartoWhatsApp.objects
        .get_or_create(
            numero_asesor=numero_asesor,
        )
    )

    control = (
        ControlRepartoWhatsApp.objects
        .select_for_update()
        .get(pk=control.pk)
    )

    indice = (
        control.siguiente_indice
        % len(asesores)
    )

    asesor_elegido = asesores[indice]

    control.siguiente_indice += 1
    control.ultimo_usuario = (
        asesor_elegido["usuario"]
    )

    control.save(
        update_fields=[
            "siguiente_indice",
            "ultimo_usuario",
            "actualizado",
        ]
    )

    expediente.usuario_crm_asignado = (
        asesor_elegido["usuario"]
    )
    expediente.asesor_digital = (
        asesor_elegido["nombre"]
    )
    expediente.asignado_automaticamente_at = (
        timezone.now()
    )

    expediente.save(
        update_fields=[
            "usuario_crm_asignado",
            "asesor_digital",
            "asignado_automaticamente_at",
            "actualizado",
        ]
    )

    return expediente


def usuario_puede_ver_expediente(
    *,
    expediente: ExpedienteDigital,
    numero_asesor: str,
    usuario: str,
) -> bool:
    """
    En líneas normales se conserva el acceso por número.

    En líneas compartidas también se valida la cuenta
    a la que fue asignado el expediente.
    """
    if not linea_tiene_reparto(numero_asesor):
        return True

    asesor = obtener_asesor_por_usuario(
        numero_asesor,
        usuario,
    )

    if not asesor:
        return False

    return (
        _normalizar_usuario(
            expediente.usuario_crm_asignado
        )
        == _normalizar_usuario(
            asesor["usuario"]
        )
    )