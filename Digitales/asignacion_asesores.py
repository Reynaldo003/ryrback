from __future__ import annotations

from django.db import transaction
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

    # Línea normal: conserva el funcionamiento anterior.
    if not asesores:
        asesor_linea = _texto(
            configuracion.get("asesor_digital")
        )

        if (
            asesor_linea
            and expediente.asesor_digital
            != asesor_linea
        ):
            expediente.asesor_digital = asesor_linea
            expediente.save(
                update_fields=[
                    "asesor_digital",
                    "actualizado",
                ]
            )

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