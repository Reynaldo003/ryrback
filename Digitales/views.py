#volkswagen
#Digitales/views.py
import json
import logging
import mimetypes
import os
import threading
import traceback
import uuid
from datetime import date, timedelta
import re

from django.conf import settings
from django.db import close_old_connections
from django.core.files.storage import default_storage
from django.db.models import Case, Count, IntegerField, OuterRef, Q, Subquery, Value, When
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from requests import request
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes, parser_classes, authentication_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied

from CrmConformidad.models import Usuario
from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from citas.models import ClienteComercial, normaliza_tel_mx

from .sett import WHATSAPP_LINES, whatsapp_numero_default
from .IA import responder_mensaje_automatico
from .models import (
    ExpedienteDigital,
    MensajeWhatsApp,
    CampanaMeta,
    LecturaWhatsApp,
    ConfiguracionIAWhatsApp,
    ConversacionIA,
    CatalogoVehiculos,
    ControlRepartoWhatsApp,
)
from .serializers import ProspectoSerializer, WhatsAppMessageSerializer, EvidenciaProspectoDigitalSerializer
from .services import generar_y_guardar_resumen, debe_generar_resumen_al_llegar_a_6
from .contacto import (
    obtener_mensaje_whatsapp,
    replace_start,
    enviar_texto_whatsapp,
    enviar_template_whatsapp,
    subir_media_whatsapp,
    enviar_media_whatsapp,
    editar_texto_whatsapp,
    download_media_whatsapp,
    obtener_numero_asesor_desde_webhook_value,
    obtener_templates_whatsapp,
    MetaAPIError,
    MetaMediaError,
    iniciar_llamada_whatsapp,
    bloquear_usuario_whatsapp,
    desbloquear_usuario_whatsapp,
    convertir_bytes_a_mp3,
)
from notificaciones.services import notificar_mensaje_whatsapp
from .atribucion_meta import aplicar_pauta_desde_referencia_meta
from .audio_whatsapp import es_archivo_audio, preparar_media_whatsapp
from .ia_config import obtener_estado_ia_conversacion
from .plantillas_meta import (
    REGLAS_UTILITY,
    analizar_estructura_plantilla,
    analizar_riesgo_marketing,
    crear_plantilla_meta,
    editar_plantilla_meta,
    eliminar_plantilla_meta,
    listar_plantillas_meta,
    subir_media_plantilla_meta,
)
from .asesor_logs import (
    actualizar_estado_entrega,
    registrar_cambios_expediente,
    registrar_evento_mensaje,
    registrar_evento_operativo,
    resolver_evento_por_respuesta,
)

from .asignacion_asesores import (
    asegurar_asignacion_expediente,
    linea_tiene_reparto,
    obtener_asesor_por_usuario,
    usuario_puede_ver_expediente,
)

from django.http import JsonResponse


TOKEN = "CBAR&RVOLKS"
logger = logging.getLogger(__name__)
_cat_logger = logging.getLogger(__name__)


# ── ViewSet ───────────────────────────────────────────────────────────────────
class ProspectosViewSet(viewsets.ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = ProspectoSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    CAMPOS_AUDITABLES = (
        "estado",
        "motivo_descalificacion",
        "asesor_digital",
        "asesor_ventas",
        "auto_interes",
        "forma_pago",
        "buro_estado",
        "plazo_compra",
        "requiere_asesor",
        "cotizacion_pendiente",
        "whatsapp_bloqueado",
    )

    def _modo_ligero(self):
        valor = str(self.request.query_params.get("ligero", "") or "").strip().casefold()
        return valor in {"1", "true", "si", "sí", "yes", "on"}

    def _base_queryset(self):
        queryset = ExpedienteDigital.objects.select_related("cliente")
        if not self._modo_ligero():
            queryset = queryset.prefetch_related("evidencias")
        return queryset.order_by(
            "-ultimo_contacto_asesor",
            "-primer_contacto_asesor",
            "-primer_mensaje_cliente",
            "-actualizado",
            "-creado",
        )

    def _solicita_todos(self):
        valor = str(
            self.request.query_params.get("todos", "")
            or ""
        ).strip().casefold()

        return valor in {
            "1",
            "true",
            "yes",
            "si",
            "sí",
            "all",
            "todos",
        }

    def _queryset_por_linea(self, numero_asesor):
        queryset = self._base_queryset()

        cfg_linea = WHATSAPP_LINES.get(
            numero_asesor,
            {},
        )

        agencia_linea = str(
            cfg_linea.get("agencia") or ""
        ).strip()

        asesor_linea = str(
            cfg_linea.get("asesor_digital") or ""
        ).strip()

        filtro_linea = Q(
            cliente__mensajes_whatsapp__numero_asesor=(
                numero_asesor
            )
        )

        if agencia_linea:
            filtro_manual = (
                Q(
                    cliente__mensajes_whatsapp__isnull=True
                )
                & Q(
                    agencia__iexact=agencia_linea
                )
            )

            if (
                not linea_tiene_reparto(
                    numero_asesor
                )
                and asesor_linea
            ):
                filtro_manual &= Q(
                    asesor_digital__iexact=(
                        asesor_linea
                    )
                )

            filtro_linea |= filtro_manual

        queryset = (
            queryset
            .filter(filtro_linea)
            .distinct()
        )

        return _filtrar_expedientes_por_asignacion(
            request=self.request,
            queryset=queryset,
            numero_asesor=numero_asesor,
        )

    def get_queryset(self):
        user = getattr(
            self.request,
            "user",
            None,
        )

        es_admin = _usuario_es_admin(
            user
        )

        accion = getattr(
            self,
            "action",
            "",
        )

        if es_admin:
            if accion in {
                "retrieve",
                "update",
                "partial_update",
                "destroy",
                "evidencias",
                "eliminar_evidencia",
            } or self._solicita_todos():
                return self._base_queryset()

        numero_asesor = (
            _get_numero_asesor_request(
                self.request
            )
        )

        return self._queryset_por_linea(
            numero_asesor
        )

    def perform_create(self, serializer):
        expediente = serializer.save()

        numero_asesor = (
            _get_numero_asesor_request(
                self.request
            )
        )

        expediente = (
            _asegurar_asignacion_salida_manual(
                request=self.request,
                expediente=expediente,
                numero_asesor=numero_asesor,
            )
        )

        serializer.instance = expediente

    def perform_update(self, serializer):
        expediente = serializer.instance

        antes = {
            campo: getattr(
                expediente,
                campo,
                None,
            )
            for campo
            in self.CAMPOS_AUDITABLES
        }

        expediente = serializer.save()

        registrar_cambios_expediente(
            expediente=expediente,
            antes=antes,
            request=self.request,
        )

    @action(detail=True, methods=["get", "post"], url_path="evidencias", parser_classes=[MultiPartParser, FormParser])
    def evidencias(self, request, pk=None):
        expediente = self.get_object()

        if request.method == "GET":
            queryset = expediente.evidencias.all().order_by("-creado")
            serializer = EvidenciaProspectoDigitalSerializer(queryset, many=True, context={"request": request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        archivos = request.FILES.getlist("archivos")
        if not archivos:
            return Response({"detail": "No se recibieron archivos."}, status=status.HTTP_400_BAD_REQUEST)

        usuario = _usuario_login(getattr(request, "user", None))
        evidencias_creadas = []

        for archivo in archivos:
            evidencia = expediente.evidencias.create(
                archivo=archivo,
                nombre_original=getattr(archivo, "name", "") or "",
                mime_type=getattr(archivo, "content_type", "") or "",
                size_bytes=getattr(archivo, "size", 0) or 0,
                subido_por=usuario,
            )
            evidencias_creadas.append(evidencia)

        serializer = EvidenciaProspectoDigitalSerializer(evidencias_creadas, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"evidencias/(?P<evidencia_id>\d+)")
    def eliminar_evidencia(self, request, pk=None, evidencia_id=None):
        expediente = self.get_object()
        evidencia = expediente.evidencias.filter(pk=evidencia_id).first()

        if not evidencia:
            return Response({"detail": "La evidencia no existe o no pertenece a este prospecto."}, status=status.HTTP_404_NOT_FOUND)

        if evidencia.archivo:
            evidencia.archivo.delete(save=False)

        evidencia.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
        
# ── Vistas simples ────────────────────────────────────────────────────────────

def bienvenido(request):
    return HttpResponse("Funcionando Digitales WhatsApp R&R, desde Django")


def privacidad_meta_view(request):
    html = """
    <!doctype html>
    <html lang="es">
    <head>
        <meta charset="utf-8">
        <title>Aviso de Privacidad - CRM WhatsApp</title>
    </head>
    <body>
        <h1>Aviso de Privacidad</h1>
        <p>
            Automotriz R&R y sus agencias utilizan este sistema CRM para gestionar
            la atención de prospectos y clientes que se comunican por canales digitales,
            incluyendo WhatsApp Business.
        </p>
        <p>
            Los datos personales que pueden tratarse incluyen nombre, teléfono,
            correo electrónico, mensajes enviados por el cliente, interés vehicular,
            agencia de atención y datos necesarios para dar seguimiento comercial.
        </p>
        <p>
            La información se utiliza únicamente para brindar atención, seguimiento,
            cotizaciones, programación de citas, atención postventa y mejora del servicio.
        </p>
        <p>
            El titular puede solicitar acceso, rectificación, cancelación u oposición
            al tratamiento de sus datos personales enviando un correo a:
            crmtuxtepec@gmail.com
        </p>
        <p>
            Esta política puede actualizarse conforme a necesidades operativas,
            legales o comerciales.
        </p>
    </body>
    </html>
    """
    return HttpResponse(html, content_type="text/html; charset=utf-8")


def eliminacion_datos_meta_view(request):
    html = """
    <!doctype html>
    <html lang="es">
    <head>
        <meta charset="utf-8">
        <title>Eliminación de Datos - CRM WhatsApp</title>
    </head>
    <body>
        <h1>Instrucciones para eliminación de datos</h1>
        <p>
            Para solicitar la eliminación de tus datos personales almacenados en el CRM,
            envía un correo a crmtuxtepec@gmail.com con el asunto:
            "Solicitud de eliminación de datos".
        </p>
        <p>
            Incluye tu nombre completo y número telefónico asociado a la conversación
            de WhatsApp para poder localizar tu información.
        </p>
        <p>
            Una vez recibida la solicitud, se revisará y procesará conforme a los
            procedimientos internos y obligaciones legales aplicables.
        </p>
    </body>
    </html>
    """
    return HttpResponse(html, content_type="text/html; charset=utf-8")


# ── Helpers internos ──────────────────────────────────────────────────────────

def _agregar_diagnostico_linea_vs_meta(resultado: dict, numero_asesor: str) -> dict:
    resultado = dict(resultado or {})
    cfg_linea = WHATSAPP_LINES.get(normaliza_tel_mx(numero_asesor or ""), {})

    agencia_linea = (cfg_linea.get("agencia") or "").strip()
    business_linea = (cfg_linea.get("business") or "").strip()
    asesor_linea = (cfg_linea.get("asesor_digital") or "").strip()

    sucursal_meta = str(resultado.get("sucursal") or "").strip()
    pauta_meta = str(resultado.get("pauta") or "").strip()

    resultado["linea_recibida"] = {
        "numero_asesor": numero_asesor,
        "agencia": agencia_linea,
        "business": business_linea,
        "asesor_digital": asesor_linea,
    }

    resultado["meta_resuelto"] = {
        "sucursal": sucursal_meta,
        "pauta": pauta_meta,
        "nombre_campana": resultado.get("nombre_campana", ""),
        "nombre_anuncio": resultado.get("nombre_anuncio", ""),
        "nombre_conjunto": resultado.get("nombre_conjunto", ""),
    }

    resultado["requiere_revision_ruteo"] = bool(
        resultado.get("ok")
        and sucursal_meta
        and agencia_linea
        and sucursal_meta.lower() not in agencia_linea.lower()
        and agencia_linea.lower() not in sucursal_meta.lower()
    )

    return resultado

def _get_or_create_cliente_y_expediente(
    *,
    tel: str,
    profile_name: str = "",
    numero_asesor: str = "",
    aplicar_reparto: bool = True,
):
    tel = normaliza_tel_mx(tel)
    numero_asesor = normaliza_tel_mx(numero_asesor or "")

    if not tel:
        return None, None

    cliente, _ = (
        ClienteComercial.objects
        .get_or_create(
            telefono=tel,
            defaults={
                "nombre": "",
            },
        )
    )

    cfg_linea = WHATSAPP_LINES.get(
        numero_asesor,
        {},
    )

    agencia_linea = str(
        cfg_linea.get("agencia") or ""
    ).strip()

    business_linea = str(
        cfg_linea.get("business") or ""
    ).strip()

    expediente, expediente_creado = (
        ExpedienteDigital.objects
        .get_or_create(cliente=cliente)
    )

    cambios = []

    campos_linea = [
        ("agencia", agencia_linea),
        ("business", business_linea),
    ]

    for campo, valor in campos_linea:
        if (
            valor
            and getattr(expediente, campo, "")
            != valor
        ):
            setattr(expediente, campo, valor)
            cambios.append(campo)

    if (
        expediente_creado
        and not (
            expediente.canal_contacto or ""
        ).strip()
    ):
        expediente.canal_contacto = "Facebook"
        cambios.append("canal_contacto")

    if not (
        expediente.estado or ""
    ).strip():
        expediente.estado = "Contactado"
        cambios.append("estado")

    if cambios:
        cambios.append("actualizado")

        expediente.save(
            update_fields=list(
                dict.fromkeys(cambios)
            )
        )

    # El reparto automático debe ejecutarse cuando el prospecto llega
    # por webhook. Para salidas manuales se asigna al usuario que inició
    # la conversación, evitando que el turno aleatorio lo entregue al otro asesor.
    if aplicar_reparto:
        expediente = asegurar_asignacion_expediente(
            expediente,
            numero_asesor,
        )

    return cliente, expediente

def _numero_linea_valido(numero: str) -> str:
    numero = normaliza_tel_mx(numero or "")
    return numero if numero in WHATSAPP_LINES else ""


def _es_usuario_autenticado(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user and getattr(user, "is_authenticated", False))


def _usuario_es_admin(user) -> bool:
    """Reconoce administradores tanto por rol como por permisos del CRM."""
    if not user or not getattr(user, "is_authenticated", False):
        return False

    if bool(getattr(user, "is_superuser", False)):
        return True

    try:
        rol_obj = getattr(user, "rol", None)
        rol = (
            getattr(rol_obj, "nombre", "")
            or getattr(rol_obj, "name", "")
            or (rol_obj if isinstance(rol_obj, str) else "")
            or ""
        ).strip().lower()

        if rol in ("administrador", "admin"):
            return True
    except Exception:
        pass

    permisos = getattr(user, "permisos", None)

    try:
        if hasattr(permisos, "all"):
            permisos = permisos.all()

        valores = set()
        for permiso in permisos or []:
            if isinstance(permiso, str):
                valores.add(permiso.strip().upper())
                continue

            valores.add(
                str(
                    getattr(permiso, "codigo", "")
                    or getattr(permiso, "nombre", "")
                    or getattr(permiso, "name", "")
                    or permiso
                ).strip().upper()
            )

        return bool({"ALL", "USUARIOS_ADMIN"} & valores)
    except Exception:
        return False

def _usuario_login(user) -> str:
    return str(
        getattr(user, "usuario", "")
        or getattr(user, "username", "")
        or ""
    ).strip()


def _rol_usuario(user) -> str:
    rol_obj = getattr(user, "rol", None)

    return str(
        getattr(rol_obj, "nombre", "")
        or getattr(rol_obj, "name", "")
        or (
            rol_obj
            if isinstance(rol_obj, str)
            else ""
        )
        or ""
    ).strip().casefold()


def _usuario_puede_ver_toda_linea(user) -> bool:
    if _usuario_es_admin(user):
        return True

    rol = _rol_usuario(user)

    return (
        "coordinador" in rol
        and "digital" in rol
    )


def _filtrar_expedientes_por_asignacion(
    *,
    request,
    queryset,
    numero_asesor: str,
):
    if not linea_tiene_reparto(
        numero_asesor
    ):
        return queryset

    user = getattr(request, "user", None)

    if _usuario_puede_ver_toda_linea(user):
        return queryset

    usuario = _usuario_login(user)

    asesor = obtener_asesor_por_usuario(
        numero_asesor,
        usuario,
    )

    if not asesor:
        return queryset.none()

    return queryset.filter(
        usuario_crm_asignado__iexact=(
            asesor["usuario"]
        )
    )


def _validar_acceso_expediente(
    *,
    request,
    expediente,
    numero_asesor: str,
):
    if not expediente:
        raise PermissionDenied(
            "No existe el expediente solicitado."
        )

    user = getattr(request, "user", None)

    if _usuario_puede_ver_toda_linea(user):
        return

    if not usuario_puede_ver_expediente(
        expediente=expediente,
        numero_asesor=numero_asesor,
        usuario=_usuario_login(user),
    ):
        raise PermissionDenied(
            "Este prospecto está asignado "
            "a otro asesor digital."
        )
    
def _asegurar_asignacion_salida_manual(
    *,
    request,
    expediente: ExpedienteDigital,
    numero_asesor: str,
) -> ExpedienteDigital:
    if not expediente:
        raise PermissionDenied(
            "No existe el expediente solicitado."
        )

    # Línea normal:
    # conserva el asesor único configurado en WHATSAPP_LINES.
    if not linea_tiene_reparto(numero_asesor):
        return asegurar_asignacion_expediente(
            expediente,
            numero_asesor,
        )

    # Línea compartida:
    # el prospecto se asigna a quien inició la conversación.
    if str(
        getattr(
            expediente,
            "usuario_crm_asignado",
            "",
        ) or ""
    ).strip():
        _validar_acceso_expediente(
            request=request,
            expediente=expediente,
            numero_asesor=numero_asesor,
        )

        return expediente

    user = getattr(request, "user", None)

    if _usuario_puede_ver_toda_linea(user):
        raise PermissionDenied(
            "El prospecto todavía no tiene asesor asignado."
        )

    asesor = obtener_asesor_por_usuario(
        numero_asesor,
        _usuario_login(user),
    )

    if not asesor:
        raise PermissionDenied(
            "Tu usuario no está configurado "
            "como asesor de esta línea."
        )

    ahora = timezone.now()

    ExpedienteDigital.objects.filter(
        pk=expediente.pk,
        usuario_crm_asignado="",
    ).update(
        usuario_crm_asignado=asesor["usuario"],
        asesor_digital=asesor["nombre"],
        asignado_automaticamente_at=ahora,
        actualizado=ahora,
    )

    expediente.refresh_from_db()

    _validar_acceso_expediente(
        request=request,
        expediente=expediente,
        numero_asesor=numero_asesor,
    )

    return expediente

def _numeros_whatsapp_usuario(user) -> list[str]:
    raw = str(getattr(user, "telefono", "") or "").strip()

    if not raw:
        return []

    partes = re.split(r"[|,;\n]+", raw)
    numeros = []

    for parte in partes:
        numero = _numero_linea_valido(parte)

        if numero and numero not in numeros:
            numeros.append(numero)

    return numeros

def _get_usuario_request_obj(request):
    user = getattr(request, "user", None)

    if user and getattr(user, "is_authenticated", False):
        return user

    return None


def _obtener_usuario_crm_request(request) -> str:
    user = _get_usuario_request_obj(request)

    if user:
        return (getattr(user, "usuario", "") or "").strip()

    username = (request.query_params.get("usuario", "") or "").strip()
    if username:
        return username

    try:
        username = (request.data.get("usuario", "") or "").strip()
        if username:
            return username
    except Exception:
        pass

    return ""


def _buscar_numero_por_usuario(username: str) -> str:
    username = (username or "").strip()

    if not username:
        return ""

    usuario = (
        Usuario.objects
        .filter(usuario__iexact=username)
        .first()
    )

    if not usuario:
        return ""

    numeros = _numeros_whatsapp_usuario(usuario)

    return numeros[0] if numeros else ""


def _get_numero_asesor_request(request) -> str:
    """
    Obtiene la línea solicitada y valida que el usuario tenga acceso.

    Administrador:
        Puede consultar cualquier número registrado en WHATSAPP_LINES.

    Usuario normal/coordinador:
        Solo puede consultar números incluidos en su campo telefono,
        separados por |, coma o punto y coma.
    """
    user = _get_usuario_request_obj(request)

    numero_param = _numero_linea_valido(
        request.query_params.get("numero_asesor", "") or ""
    )

    if not numero_param:
        try:
            numero_param = _numero_linea_valido(
                request.data.get("numero_asesor", "") or ""
            )
        except Exception:
            numero_param = ""

    if user:
        numeros_asignados = _numeros_whatsapp_usuario(user)

        if _usuario_es_admin(user):
            if numero_param:
                return numero_param

            if numeros_asignados:
                return numeros_asignados[0]

            raise PermissionDenied(
                "El administrador no tiene una línea configurada "
                "y no se recibió numero_asesor."
            )

        if numero_param:
            if numero_param in numeros_asignados:
                return numero_param

            raise PermissionDenied(
                f"No tienes permiso para administrar la línea "
                f"{numero_param}."
            )

        if numeros_asignados:
            return numeros_asignados[0]

        raise PermissionDenied(
            "Tu usuario no tiene líneas de WhatsApp asignadas."
        )

    # Compatibilidad con peticiones legacy no autenticadas.
    if numero_param:
        return numero_param

    username = _obtener_usuario_crm_request(request)
    numero = _buscar_numero_por_usuario(username)

    if numero:
        return numero

    raise PermissionDenied(
        "No se pudo determinar la línea de WhatsApp. "
        "Envía numero_asesor o usa un usuario con teléfono configurado."
    )

def _get_or_create_lectura(exp: ExpedienteDigital, numero_asesor: str) -> LecturaWhatsApp:
    lectura, _ = LecturaWhatsApp.objects.get_or_create(
        expediente=exp,
        numero_asesor=numero_asesor,
    )
    return lectura


def _mark_read_exp(exp: ExpedienteDigital, numero_asesor: str, when=None):
    lectura = _get_or_create_lectura(exp, numero_asesor)
    lectura.last_read_at = when or timezone.now()
    lectura.save(update_fields=["last_read_at", "updated_at"])


def _unread_count(exp: ExpedienteDigital, numero_asesor: str) -> int:
    qs = MensajeWhatsApp.objects.filter(
        telefono=exp.cliente.telefono,
        numero_asesor=numero_asesor,
        direction="in",
    )
    lectura = LecturaWhatsApp.objects.filter(
        expediente=exp,
        numero_asesor=numero_asesor,
    ).first()
    if lectura and lectura.last_read_at:
        qs = qs.filter(created_at__gt=lectura.last_read_at)
    return qs.count()


def _contar_no_leidos_chats(expedientes, numero_asesor: str) -> dict[str, int]:
    """Calcula los no leídos de una página completa sin ejecutar una consulta por cada chat."""
    expedientes = list(expedientes or [])
    if not expedientes:
        return {}

    ids = [exp.id for exp in expedientes if exp.id]
    lecturas = {
        item["expediente_id"]: item["last_read_at"]
        for item in LecturaWhatsApp.objects.filter(expediente_id__in=ids, numero_asesor=numero_asesor)
        .values("expediente_id", "last_read_at")
    }

    filtro = Q()
    for exp in expedientes:
        telefono = normaliza_tel_mx(exp.cliente.telefono)
        if not telefono:
            continue
        condicion = Q(telefono=telefono)
        last_read_at = lecturas.get(exp.id)
        if last_read_at:
            condicion &= Q(created_at__gt=last_read_at)
        filtro |= condicion

    if not filtro.children:
        return {}

    conteos = (
        MensajeWhatsApp.objects
        .filter(numero_asesor=numero_asesor, direction=MensajeWhatsApp.Direccion.IN)
        .filter(filtro)
        .values("telefono")
        .annotate(total=Count("id"))
    )
    return {normaliza_tel_mx(item["telefono"]): int(item["total"] or 0) for item in conteos}

def _parse_hora_ia(value):
    try:
        return timezone.datetime.strptime(str(value or "").strip(), "%H:%M").time()
    except Exception:
        return None

def _aware_datetime_ia(fecha, hora):
    dt = timezone.datetime.combine(fecha, hora)

    if settings.USE_TZ and timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())

    return dt

def _ia_esta_en_horario(horarios: dict) -> bool:
    if not isinstance(horarios, dict) or not horarios:
        return True

    dias = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
    ahora = timezone.now()

    if settings.USE_TZ and timezone.is_aware(ahora):
        ahora = timezone.localtime(ahora)
    hoy_idx = ahora.weekday()

    for inicio_idx, dia_key in enumerate(dias):
        config_dia = horarios.get(dia_key) or {}

        if not config_dia.get("activo", False):
            continue

        hora_inicio = _parse_hora_ia(config_dia.get("inicio"))
        hora_fin = _parse_hora_ia(config_dia.get("fin"))

        if not hora_inicio or not hora_fin:
            continue

        hasta_dia = config_dia.get("hastaDia")
        hasta_idx = dias.index(hasta_dia) if hasta_dia in dias else None

        base_delta = inicio_idx - hoy_idx

        for semana_offset in (0, -7):
            fecha_inicio = ahora.date() + timedelta(days=base_delta + semana_offset)

            if hasta_idx is not None:
                dias_duracion = (hasta_idx - inicio_idx) % 7
                fecha_fin = fecha_inicio + timedelta(days=dias_duracion)
            else:
                fecha_fin = fecha_inicio
                if hora_fin <= hora_inicio:
                    fecha_fin = fecha_fin + timedelta(days=1)

            inicio_dt = _aware_datetime_ia(fecha_inicio, hora_inicio)
            fin_dt = _aware_datetime_ia(fecha_fin, hora_fin)

            if inicio_dt <= ahora <= fin_dt:
                return True

    return False

def _debe_responder_con_ia(numero_asesor: str, expediente=None) -> bool:
    estado_ia = obtener_estado_ia_conversacion(
        numero_asesor=numero_asesor,
        expediente=expediente,
    )

    if not estado_ia.get("puede_responder"):
        logger.info(
            "IA OMITIDA | numero_asesor=%s expediente_id=%s bloqueos=%s estado=%s",
            numero_asesor,
            getattr(expediente, "id", None),
            estado_ia.get("bloqueos"),
            json.dumps(estado_ia, ensure_ascii=False),
        )
        return False

    logger.info(
        "IA HABILITADA | numero_asesor=%s expediente_id=%s",
        numero_asesor,
        getattr(expediente, "id", None),
    )
    return True

def _ya_existe_respuesta_ia_para_entrada(numero_asesor: str, wa_message_id_entrante: str) -> bool:
    numero_asesor = normaliza_tel_mx(numero_asesor or "")
    wa_message_id_entrante = (wa_message_id_entrante or "").strip()
    if not numero_asesor or not wa_message_id_entrante:
        return False
    return MensajeWhatsApp.objects.filter(
        numero_asesor=numero_asesor,
        direction="out",
        raw__reply_to=wa_message_id_entrante,
    ).exists()


def _obtener_referral_meta(msg: dict) -> dict:
    if not isinstance(msg, dict):
        return {}
    referral = msg.get("referral") or {}
    if not referral:
        context = msg.get("context") or {}
        if isinstance(context, dict):
            referral = context.get("referral") or {}
    if not isinstance(referral, dict):
        return {}
    return referral


def _normalizar_id_campana_meta(value):
    texto = str(value or "").strip()
    if not texto or not texto.isdigit():
        return None
    try:
        return int(texto)
    except (TypeError, ValueError, OverflowError):
        return None


def _buscar_campana_meta_por_source_id(source_id: str):
    id_campana = _normalizar_id_campana_meta(source_id)
    if id_campana is None:
        return None
    try:
        return (
            CampanaMeta.objects.using("sqlserver")
            .filter(id_campana=id_campana)
            .only("id_campana", "sucursal", "nombre_campana")
            .first()
        )
    except Exception as e:
        logger.exception("ERROR CONSULTANDO CAMPANA META: source_id=%s error=%s", source_id, str(e))
        return None


def _armar_label_campana_meta(campana: CampanaMeta) -> str:
    if not campana:
        return ""
    sucursal = str(campana.sucursal or "").strip()
    nombre = str(campana.nombre_campana or "").strip()
    if sucursal and nombre:
        return f"{sucursal} - {nombre}"
    return nombre or sucursal

def _aplicar_atribucion_meta_segura(*, expediente, mensaje_whatsapp, numero_asesor, telefono, wa_id):
    try:
        return aplicar_pauta_desde_referencia_meta(
            expediente=expediente,
            mensaje_whatsapp=mensaje_whatsapp,
            numero_asesor=numero_asesor,
        )
    except Exception as e:
        logger.exception(
            "ERROR ATRIBUCION META WEBHOOK | numero_asesor=%s telefono=%s wa_id=%s error=%s",
            numero_asesor, telefono, wa_id, str(e),
        )
        return {"ok": False, "motivo": "error_atribucion_meta", "error": str(e)}
    
def _procesar_respuesta_ia_en_segundo_plano(
    *,
    wa_from: str,
    numero_asesor: str,
    profile_name: str,
    texto_usuario: str,
    wa_message_id_entrante: str,
    raw_message: dict,
):
    close_old_connections()
    try:
        logger.info(
            "IA INICIO: numero_asesor=%s wa_from=%s wa_id=%s texto=%s",
            numero_asesor, wa_from, wa_message_id_entrante, texto_usuario,
        )
        res = responder_mensaje_automatico(
            wa_from=wa_from,
            profile_name=profile_name,
            texto_usuario=texto_usuario,
            wa_message_id_entrante=wa_message_id_entrante,
            raw_message=raw_message,
            numero_asesor=numero_asesor,
        )
        logger.info(
            "IA OK: numero_asesor=%s wa_from=%s ok=%s skipped=%s",
            numero_asesor, wa_from,
            (res or {}).get("ok"),
            (res or {}).get("skipped", False),
        )
    except Exception as e:
        logger.error(
            "Error respondiendo con IA: numero_asesor=%s wa_from=%s error=%s",
            numero_asesor, wa_from, str(e),
        )
        traceback.print_exc()
    finally:
        close_old_connections()


def _int_param(request, name: str, default: int, min_value: int, max_value: int) -> int:
    try:
        value = int(request.query_params.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(value, max_value))


def _parse_dt_param(value: str):
    value = (value or "").strip()
    if not value:
        return None
    dt = parse_datetime(value)
    if not dt:
        return None
    if settings.USE_TZ:
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    if timezone.is_aware(dt):
        return timezone.make_naive(dt, timezone.get_current_timezone())
    return dt



def _extraer_wa_message_id(wa_res: dict) -> str:
    try:
        return (wa_res.get("messages") or [{}])[0].get("id", "") or ""
    except Exception:
        return ""


def _http_status_desde_meta_error(error: MetaAPIError) -> int:
    if error.status_code == 429:
        return status.HTTP_429_TOO_MANY_REQUESTS

    if error.retryable:
        return status.HTTP_503_SERVICE_UNAVAILABLE

    if error.status_code == 400:
        return status.HTTP_400_BAD_REQUEST

    return status.HTTP_502_BAD_GATEWAY


def _response_meta_error(error: MetaAPIError, *, numero_asesor: str = "", extra: dict | None = None):
    payload = {
        "ok": False,
        "error": error.meta_message,
        "retryable": error.retryable,
        "meta": error.to_dict(),
        "numero_asesor": numero_asesor,
    }

    if extra:
        payload.update(extra)

    return Response(
        payload,
        status=_http_status_desde_meta_error(error),
    )


def _guardar_mensaje_fallido(
    *,
    to: str,
    numero_asesor: str,
    cliente=None,
    body: str,
    error,
    extra_raw: dict | None = None,
):
    raw = {
        "provider": "meta",
        "numero_asesor": numero_asesor,
        "error": str(error),
    }

    if isinstance(error, MetaAPIError):
        raw["meta"] = error.to_dict()

    if isinstance(error, MetaMediaError):
        raw["meta_media"] = error.to_dict()

    if extra_raw:
        raw.update(extra_raw)

    try:
        mensaje_fallido = MensajeWhatsApp.objects.create(
            telefono=to,
            numero_asesor=numero_asesor,
            cliente=cliente,
            direction="out",
            body=body,
            wa_message_id="",
            status="failed",
            raw=raw,
        )
        registrar_evento_mensaje(mensaje_fallido)
        return mensaje_fallido
    except Exception as save_error:
        logger.exception(
            "No se pudo guardar mensaje fallido | to=%s numero_asesor=%s error=%s",
            to,
            numero_asesor,
            str(save_error),
        )


def _absolute_backend_url(url_o_path: str) -> str:
    value = str(url_o_path or "").strip()

    if not value:
        return ""

    if value.startswith("http://") or value.startswith("https://"):
        return value.replace(" ", "%20")

    base = str(
        getattr(settings, "PUBLIC_API_BASE_URL", "")
        or "https://crm.grupoautomotrizryr.com"
    ).rstrip("/")

    if value.startswith("//"):
        return f"https:{value}".replace(" ", "%20")

    if not value.startswith("/"):
        value = f"/{value}"

    return f"{base}{value}".replace(" ", "%20")


def _guardar_upload_whatsapp_local(
    file_obj,
    *,
    numero_asesor: str,
    telefono: str,
    content_type: str = "",
) -> str:
    original_name = getattr(file_obj, "name", "archivo") or "archivo"
    _, ext = os.path.splitext(original_name)

    if not ext:
        ext = mimetypes.guess_extension(content_type or "") or ".bin"

    filename = f"{uuid.uuid4().hex}{ext.lower()}"
    path = f"whatsapp_uploads/{numero_asesor}/{telefono}/{filename}"

    try:
        file_obj.seek(0)
    except Exception:
        pass

    saved_path = default_storage.save(path, file_obj)

    try:
        file_obj.seek(0)
    except Exception:
        pass

    local_url = default_storage.url(saved_path)

    return _absolute_backend_url(local_url)

def _cache_media_meta_en_segundo_plano(*, media_id: str, numero_asesor: str):
    close_old_connections()

    try:
        download_media_whatsapp(
            media_id,
            numero_asesor=numero_asesor,
        )

        logger.info(
            "MEDIA CACHEADA OK | media_id=%s numero_asesor=%s",
            media_id,
            numero_asesor,
        )

    except Exception as e:
        logger.warning(
            "NO SE PUDO CACHEAR MEDIA | media_id=%s numero_asesor=%s error=%s",
            media_id,
            numero_asesor,
            str(e),
        )

    finally:
        close_old_connections()

# ── Procesador de respuestas WhatsApp Flow (enc_piso) ─────────────────────────

def _procesar_respuesta_flow_enc_piso(msg: dict) -> bool:
    try:
        msg_type = str(msg.get("type") or "").lower()
        if msg_type != "interactive":
            return False

        interactive = msg.get("interactive") or {}
        if str(interactive.get("type") or "").lower() != "nfm_reply":
            return False

        nfm_reply = interactive.get("nfm_reply") or {}
        response_json_str = nfm_reply.get("response_json") or "{}"

        try:
            flow_data = json.loads(response_json_str)
        except Exception:
            logger.warning("FLOW ENC_PISO | No se pudo parsear response_json: %s", response_json_str)
            return False

        logger.info("FLOW ENC_PISO RECIBIDO | data=%s", json.dumps(flow_data, ensure_ascii=False))

        # Verificar que es el flow correcto — debe tener al menos atencion_llegada
        if "atencion_llegada" not in flow_data:
            return False

        # flow_token
        flow_token = str(
            msg.get("context", {}).get("flow_token")
            or flow_data.get("flow_token")
            or ""
        ).strip()

        # id_trafico desde flow_token "trafico_<id>"
        id_trafico = None
        if flow_token.startswith("trafico_"):
            try:
                id_trafico = int(flow_token.replace("trafico_", ""))
            except ValueError:
                pass

        # Teléfono del remitente
        wa_from = str(msg.get("from") or "").strip()
        digitos = "".join(ch for ch in wa_from if ch.isdigit())
        telefono = digitos[-10:] if len(digitos) >= 10 else digitos

        # Mapeo de palabras a número de estrellas
        STAR_MAP = {
            "cinco": 5, "cuatro": 4, "tres": 3, "dos": 2, "uno": 1,
            "five": 5, "four": 4, "three": 3, "two": 2, "one": 1,
            "5": 5, "4": 4, "3": 3, "2": 2, "1": 1,
        }

        def parse_star(val):
            if val is None:
                return 0
            v = str(val).strip().lower()
            return STAR_MAP.get(v, 0)

        # Obtener agencia y nombre desde TraficoPiso si tenemos id_trafico
        agencia = ""
        nombre_cliente = ""
        asesor_atendio = ""
        if id_trafico:
            try:
                from TraficoPiso.models import TraficoPiso as TraficoPisoModel
                trafico = TraficoPisoModel.objects.filter(id_trafico=id_trafico).first()
                if trafico:
                    agencia = trafico.agencia or ""
                    nombre_cliente = trafico.nombre_prospecto or ""
                    asesor_atendio = trafico.asesor_ventas or ""
            except Exception as e:
                logger.warning("No se pudo obtener TraficoPiso id=%s: %s", id_trafico, e)

        from Encuestas.models import EncuestaPiso

        encuesta = EncuestaPiso.objects.create(
            id_trafico      = id_trafico,
            telefono        = telefono,
            flow_token      = flow_token,
            agencia         = agencia,
            nombre_cliente  = nombre_cliente,
            asesor_atendio  = asesor_atendio,
            # Campos del Flow
            atencion_llegada = parse_star(flow_data.get("atencion_llegada")),
            amenidades       = parse_star(flow_data.get("amenidades")),
            atencion_asesor  = parse_star(flow_data.get("atencion_asesor")),
            financiamiento   = str(flow_data.get("financiamiento") or "").strip(),
            experiencia      = parse_star(flow_data.get("experiencia")),
            medio_contacto   = str(flow_data.get("medio_contacto") or "").strip(),
            prueba_manejo    = str(flow_data.get("prueba_manejo") or "").strip(),
            recomendacion    = str(flow_data.get("recomendacion") or "").strip(),
            contacto_post    = str(flow_data.get("contacto_post") or "").strip(),
            tiempo_contacto  = str(flow_data.get("tiempo_contacto") or "").strip(),
            comentarios      = str(flow_data.get("comentarios") or "").strip(),
        )

        logger.info(
            "FLOW ENC_PISO GUARDADO | id_encuesta=%s id_trafico=%s telefono=%s",
            encuesta.id_encuesta, id_trafico, telefono,
        )
        return True

    except Exception as e:
        logger.exception("ERROR PROCESANDO FLOW ENC_PISO | error=%s", str(e))
        return False
    
def _extraer_reaccion_whatsapp(msg: dict) -> dict:
    if not isinstance(msg, dict):
        return {}

    if str(msg.get("type") or "").lower() != "reaction":
        return {}

    reaction = msg.get("reaction") or {}

    if not isinstance(reaction, dict):
        return {}

    target_message_id = str(reaction.get("message_id") or "").strip()
    emoji = str(reaction.get("emoji") or "").strip()

    if not target_message_id:
        return {}

    return {
        "target_message_id": target_message_id,
        "emoji": emoji,
        "removed": not bool(emoji),
    }


def _aplicar_reaccion_a_mensaje_original(
    *,
    msg: dict,
    raw_msg: dict,
    telefono: str,
    numero_asesor: str,
    cliente=None,
) -> bool:
    data = _extraer_reaccion_whatsapp(msg)

    if not data:
        return False

    target_message_id = data["target_message_id"]
    emoji = data["emoji"]
    removed = data["removed"]

    mensaje_objetivo = (
        MensajeWhatsApp.objects
        .filter(
            numero_asesor=numero_asesor,
            wa_message_id=target_message_id,
        )
        .order_by("-id")
        .first()
    )

    # Guardamos también un evento oculto para que el polling del frontend lo reciba.
    # Este evento NO se va a pintar como burbuja.
    wa_reaction_id = str(msg.get("id") or "").strip()

    MensajeWhatsApp.objects.get_or_create(
        wa_message_id=wa_reaction_id,
        numero_asesor=numero_asesor,
        defaults={
            "telefono": telefono,
            "cliente": cliente,
            "direction": "in",
            "body": "",
            "status": "received",
            "raw": {
                **raw_msg,
                "is_reaction_event": True,
                "reaction_target_id": target_message_id,
                "reaction_emoji": emoji,
                "reaction_removed": removed,
            },
        },
    )

    if not mensaje_objetivo:
        logger.info(
            "REACTION SIN MENSAJE OBJETIVO | target=%s emoji=%s tel=%s numero_asesor=%s",
            target_message_id,
            emoji,
            telefono,
            numero_asesor,
        )
        return True

    raw_objetivo = dict(mensaje_objetivo.raw or {})

    reactions = raw_objetivo.get("reactions")
    if not isinstance(reactions, list):
        reactions = []

    # Solo dejamos una reacción activa por cliente sobre ese mensaje.
    reactions = [
        item for item in reactions
        if str(item.get("telefono") or "") != str(telefono or "")
    ]

    if not removed and emoji:
        reactions.append({
            "telefono": telefono,
            "emoji": emoji,
            "from": "cliente",
            "reaction_message_id": wa_reaction_id,
            "created_at": timezone.now().isoformat(),
        })

    raw_objetivo["reactions"] = reactions
    raw_objetivo["last_reaction_payload"] = raw_msg

    mensaje_objetivo.raw = raw_objetivo
    mensaje_objetivo.save(update_fields=["raw"])

    logger.info(
        "REACTION APLICADA | target=%s emoji=%s removed=%s tel=%s numero_asesor=%s",
        target_message_id,
        emoji,
        removed,
        telefono,
        numero_asesor,
    )

    return True

# ── Webhook ───────────────────────────────────────────────────────────────────

@csrf_exempt
def webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode", "")
        token = request.GET.get("hub.verify_token", "")
        challenge = request.GET.get("hub.challenge", "")
        logger.info("WEBHOOK VERIFY | mode=%s token_ok=%s challenge=%s", mode, token == TOKEN, challenge)
        if mode == "subscribe" and token == TOKEN and challenge:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse("token incorrecto", status=403)

    if request.method != "POST":
        return HttpResponse("method not allowed", status=405)

    try:
        raw_body = request.body.decode("utf-8")
        body = json.loads(raw_body)
        logger.info("WEBHOOK RAW BODY: %s", json.dumps(body, ensure_ascii=False))
    except Exception as e:
        logger.exception("ERROR PARSEANDO WEBHOOK: %s", str(e))
        return HttpResponse("ok")

    try:
        entries = body.get("entry") or []
        for entry in entries:
            changes = entry.get("changes") or []
            for ch in changes:
                value = ch.get("value") or {}
                metadata = value.get("metadata") or {}
                calls = value.get("calls") or []

                for call in calls:
                    logger.info(
                        "WEBHOOK CALL RECIBIDO | id=%s from=%s to=%s event=%s",
                        call.get("id"),
                        call.get("from"),
                        call.get("to"),
                        call.get("event"),
                    )
                numero_asesor = obtener_numero_asesor_desde_webhook_value(value)

                if not numero_asesor:
                    logger.warning(
                        "WEBHOOK SIN MAPEO DE LINEA | phone_number_id=%s display_phone_number=%s",
                        metadata.get("phone_number_id"),
                        metadata.get("display_phone_number"),
                    )

                contacts = value.get("contacts") or []
                profile_name = ""
                if contacts:
                    profile_name = (contacts[0].get("profile") or {}).get("name", "") or ""

                messages = value.get("messages") or []
                for msg in messages:
                    wa_from = msg.get("from", "")
                    tel = normaliza_tel_mx(replace_start(wa_from))
                    wa_id = (msg.get("id", "") or "").strip()
                    text = obtener_mensaje_whatsapp(msg)

                    logger.info(
                        "WEBHOOK MENSAJE RECIBIDO | from=%s tel=%s wa_id=%s type=%s text=%s",
                        wa_from, tel, wa_id, msg.get("type"), text,
                    )
                    if _procesar_respuesta_flow_enc_piso(msg):
                        logger.info("FLOW PROCESADO | from=%s wa_id=%s", wa_from, wa_id)

                    if not tel or not wa_id:
                        logger.warning("WEBHOOK MENSAJE OMITIDO SIN TEL O WA_ID | from=%s wa_id=%s", wa_from, wa_id)
                        continue

                    if not numero_asesor:
                        logger.warning("MENSAJE OMITIDO POR LINEA NO RESUELTA | from=%s tel=%s wa_id=%s", wa_from, tel, wa_id)
                        continue

                    cliente, exp = _get_or_create_cliente_y_expediente(
                        tel=tel,
                        profile_name=profile_name,
                        numero_asesor=numero_asesor,
                        aplicar_reparto=True,
                    )

                    if not cliente or not exp:
                        logger.warning("WEBHOOK OMITIDO SIN CLIENTE O EXPEDIENTE | tel=%s", tel)
                        continue

                    exp.touch_mensaje_cliente(save_now=True)

                    resultado_atribucion_meta = _aplicar_atribucion_meta_segura(
                        expediente=exp,
                        mensaje_whatsapp=msg,
                        numero_asesor=numero_asesor,
                        telefono=tel,
                        wa_id=wa_id,
                    )

                    resultado_atribucion_meta = _agregar_diagnostico_linea_vs_meta(
                        resultado_atribucion_meta,
                        numero_asesor,
                    )

                    if resultado_atribucion_meta.get("requiere_revision_ruteo"):
                        logger.warning(
                            "POSIBLE RUTEO INCORRECTO META VS WHATSAPP | tel=%s wa_id=%s resultado=%s",
                            tel,
                            wa_id,
                            json.dumps(resultado_atribucion_meta, ensure_ascii=False),
                        )

                    raw_msg = dict(msg)
                    raw_msg["numero_asesor"] = numero_asesor
                    raw_msg["phone_number_id"] = metadata.get("phone_number_id", "")
                    raw_msg["display_phone_number"] = metadata.get("display_phone_number", "")
                    raw_msg["atribucion_meta"] = resultado_atribucion_meta
                    if _aplicar_reaccion_a_mensaje_original(
                        msg=msg,
                        raw_msg=raw_msg,
                        telefono=tel,
                        numero_asesor=numero_asesor,
                        cliente=cliente,
                    ):
                        logger.info(
                            "WEBHOOK REACTION PROCESADA SIN IA | tel=%s wa_id=%s numero_asesor=%s",
                            tel,
                            wa_id,
                            numero_asesor,
                        )
                        continue
                    
                    mensaje_entrante, created = MensajeWhatsApp.objects.get_or_create(
                        wa_message_id=wa_id,
                        numero_asesor=numero_asesor,
                        defaults={
                            "telefono": tel,
                            "cliente": cliente,
                            "direction": "in",
                            "body": text,
                            "status": "received",
                            "raw": raw_msg,
                        },
                    )

                    logger.info(
                        "WEBHOOK MENSAJE GUARDADO | created=%s id=%s tel=%s wa_id=%s",
                        created, mensaje_entrante.id, tel, wa_id,
                    )

                    if not created:
                        cambios = []
                        if not mensaje_entrante.cliente_id and cliente:
                            mensaje_entrante.cliente = cliente
                            cambios.append("cliente")
                        if not (mensaje_entrante.telefono or "").strip():
                            mensaje_entrante.telefono = tel
                            cambios.append("telefono")
                        raw_actual = dict(mensaje_entrante.raw or {})
                        raw_actual["ultimo_webhook_payload"] = raw_msg
                        mensaje_entrante.raw = raw_actual
                        cambios.append("raw")
                        if cambios:
                            mensaje_entrante.save(update_fields=list(dict.fromkeys(cambios)))


                    if created:
                        resolver_evento_por_respuesta(
                            mensaje_entrante,
                            expediente=exp,
                        )

                    if created:
                        media_type = str(msg.get("type") or "").lower()

                        if media_type in ("image", "document", "video", "audio", "sticker"):
                            media_payload = msg.get(media_type) or {}
                            media_id = str(media_payload.get("id") or "").strip()

                            if media_id:
                                hilo_media = threading.Thread(
                                    target=_cache_media_meta_en_segundo_plano,
                                    kwargs={
                                        "media_id": media_id,
                                        "numero_asesor": numero_asesor,
                                    },
                                    daemon=True,
                                )
                                hilo_media.start()

                    if created:
                        try:
                            if debe_generar_resumen_al_llegar_a_6(telefono=tel):
                                generar_y_guardar_resumen(expediente=exp, fuente="auto_6")
                        except Exception as e:
                            logger.exception("Error generando resumen automático | tel=%s error=%s", tel, str(e))

                    if created:
                        try:
                            notificar_mensaje_whatsapp(
                                numero_asesor=numero_asesor,
                                telefono=tel,
                                nombre=getattr(cliente, "nombre", "") or profile_name or "Prospecto",
                                mensaje=text,
                                wa_message_id=wa_id,
                                expediente_id=exp.id if exp else None,
                                created_at=mensaje_entrante.created_at,
                            )
                        except Exception as e:
                            logger.exception("Error notificación websocket | tel=%s wa_id=%s error=%s", tel, wa_id, str(e))

                    if _debe_responder_con_ia(numero_asesor, exp):
                        if not _ya_existe_respuesta_ia_para_entrada(numero_asesor, wa_id):
                            hilo = threading.Thread(
                                target=_procesar_respuesta_ia_en_segundo_plano,
                                kwargs={
                                    "wa_from": wa_from,
                                    "numero_asesor": numero_asesor,
                                    "profile_name": profile_name,
                                    "texto_usuario": text,
                                    "wa_message_id_entrante": wa_id,
                                    "raw_message": msg,
                                },
                            )
                            hilo.start()

                statuses = value.get("statuses") or []
                for s in statuses:
                    wa_id = s.get("id")
                    st = s.get("status")
                    errors = s.get("errors") or []
                    ts = s.get("timestamp")

                    if not (wa_id and st):
                        logger.warning("WEBHOOK STATUS OMITIDO SIN ID O STATUS | payload=%s", json.dumps(s, ensure_ascii=False))
                        continue

                    q = MensajeWhatsApp.objects.filter(wa_message_id=wa_id)
                    if numero_asesor:
                        q = q.filter(numero_asesor=numero_asesor)

                    msg_obj = q.first()
                    if not msg_obj:
                        logger.warning("WEBHOOK STATUS SIN MENSAJE LOCAL | wa_id=%s status=%s", wa_id, st)
                        continue

                    new_raw = dict(msg_obj.raw or {})
                    new_raw["status_payload"] = s
                    if errors:
                        new_raw["errors"] = errors
                    if ts:
                        new_raw["status_timestamp"] = ts

                    msg_obj.status = st
                    msg_obj.raw = new_raw
                    msg_obj.save(update_fields=["status", "raw"])
                    actualizar_estado_entrega(msg_obj, st, errors=errors)

                    logger.info("WEBHOOK STATUS ACTUALIZADO | wa_id=%s status=%s", wa_id, st)

        return HttpResponse("ok")

    except Exception as e:
        logger.exception("ERROR GENERAL WEBHOOK: %s", str(e))
        return HttpResponse("ok")


# ── API views ─────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def media_proxy_view(request, media_id: str):
    numero_asesor = normaliza_tel_mx(request.query_params.get("numero_asesor", ""))

    try:
        blob, content_type = download_media_whatsapp(
            media_id,
            numero_asesor=numero_asesor,
        )

        resp = HttpResponse(blob, content_type=content_type)
        resp["Cache-Control"] = "private, max-age=86400"
        return resp

    except MetaMediaError as e:
        logger.warning(
            "MEDIA META NO DISPONIBLE | media_id=%s numero_asesor=%s error=%s",
            media_id,
            numero_asesor,
            e.to_dict(),
        )

        status_code = 410 if e.es_media_no_disponible() else 502

        return HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "error": "El archivo ya no está disponible en Meta o no pertenece a esta línea.",
                    "meta": e.to_dict(),
                },
                ensure_ascii=False,
            ),
            status=status_code,
            content_type="application/json; charset=utf-8",
        )

    except Exception as e:
        logger.exception(
            "ERROR MEDIA PROXY | media_id=%s numero_asesor=%s error=%s",
            media_id,
            numero_asesor,
            str(e),
        )

        return HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "error": str(e),
                },
                ensure_ascii=False,
            ),
            status=400,
            content_type="application/json; charset=utf-8",
        )

@api_view(["GET"])
@permission_classes([AllowAny])
def media_descargar_mp3_view(request, media_id: str):
    """
    Descarga forzada del audio ya convertido a MP3 real (no solo renombrado).
    Usa Content-Disposition: attachment para que el navegador lo baje directo,
    sin depender de fetch/CORS en el frontend.
    """
    numero_asesor = normaliza_tel_mx(request.query_params.get("numero_asesor", ""))

    try:
        blob, content_type = download_media_whatsapp(
            media_id,
            numero_asesor=numero_asesor,
        )

        if content_type.startswith("audio/"):
            mp3_bytes = convertir_bytes_a_mp3(blob, content_type)
            resp = HttpResponse(mp3_bytes, content_type="audio/mpeg")
            resp["Content-Disposition"] = 'attachment; filename="nota-voz.mp3"'
            return resp

        # No es audio: se descarga tal cual, sin conversión.
        resp = HttpResponse(blob, content_type=content_type)
        resp["Content-Disposition"] = 'attachment; filename="archivo"'
        return resp

    except MetaMediaError as e:
        logger.warning(
            "MEDIA META NO DISPONIBLE (descarga) | media_id=%s numero_asesor=%s error=%s",
            media_id, numero_asesor, e.to_dict(),
        )
        status_code = 410 if e.es_media_no_disponible() else 502
        return HttpResponse(
            json.dumps({"ok": False, "error": "El archivo ya no está disponible en Meta.", "meta": e.to_dict()}, ensure_ascii=False),
            status=status_code,
            content_type="application/json; charset=utf-8",
        )

    except Exception as e:
        logger.exception(
            "ERROR DESCARGANDO/CONVIRTIENDO MEDIA | media_id=%s numero_asesor=%s error=%s",
            media_id, numero_asesor, str(e),
        )
        return HttpResponse(
            json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            status=400,
            content_type="application/json; charset=utf-8",
        )

@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def chats_list(request):
    numero_asesor = _get_numero_asesor_request(request)
    paginado = str(request.query_params.get("paginado", "0") or "").strip().casefold() in {"1", "true", "yes", "si", "sí", "on"}
    limit = _int_param(request, "limit", 30, 10, 60) if paginado else 200
    busqueda = str(request.query_params.get("q", "") or "").strip()[:120]
    scope = str(request.query_params.get("scope", "recientes") or "recientes").strip().casefold()
    dias = _int_param(request, "dias", 3, 1, 30)
    before = _parse_dt_param(request.query_params.get("before", ""))

    try:
        before_id = int(request.query_params.get("before_id", "") or 0)
    except (TypeError, ValueError):
        before_id = 0

    try:
        before_prioridad = int(request.query_params.get("before_prioridad", "") or 0)
    except (TypeError, ValueError):
        before_prioridad = 0
    ahora = timezone.now()
    limite_recientes = ahora - timedelta(days=dias)
    limite_cita_prioritaria = ahora + timedelta(days=5)
    last_msg_qs = (
        MensajeWhatsApp.objects
        .filter(telefono=OuterRef("cliente__telefono"), numero_asesor=numero_asesor)
        .order_by("-created_at", "-id")
    )
    qs = (
        ExpedienteDigital.objects.select_related("cliente")
        .filter(cliente__mensajes_whatsapp__numero_asesor=numero_asesor)
    )
    qs = _filtrar_expedientes_por_asignacion(request=request, queryset=qs, numero_asesor=numero_asesor)
    qs = qs.annotate(
        last_text=Subquery(last_msg_qs.values("body")[:1]),
        last_time=Subquery(last_msg_qs.values("created_at")[:1]),
    ).distinct()

    if busqueda:
        digitos = re.sub(r"\D", "", busqueda)
        filtro_busqueda = Q(cliente__nombre__icontains=busqueda)
        if digitos:
            telefono_busqueda = digitos[-10:] if len(digitos) >= 10 else digitos
            filtro_busqueda |= Q(cliente__telefono__icontains=telefono_busqueda)
        qs = qs.filter(filtro_busqueda)
        scope = "busqueda"
    elif paginado:
        if scope == "historico":
            qs = qs.filter(
                last_time__lt=limite_recientes,
            ).filter(
                Q(ultima_cita_agendada__isnull=True)
                | Q(ultima_cita_agendada__lt=ahora)
                | Q(ultima_cita_agendada__gt=limite_cita_prioritaria)
            )
        else:
            scope = "recientes"
            qs = qs.filter(
                Q(last_time__gte=limite_recientes)
                | Q(
                    ultima_cita_agendada__gte=ahora,
                    ultima_cita_agendada__lte=limite_cita_prioritaria,
                )
            )
    qs = qs.annotate(
        tiene_cita_futura=Case(
            When(
                ultima_cita_agendada__isnull=False,
                ultima_cita_agendada__gte=ahora,
                ultima_cita_agendada__lte=limite_cita_prioritaria,
                then=Value(1),
            ),
            default=Value(0),
            output_field=IntegerField(),
        )
    )

    if paginado and before:
        if before_id:
            qs = qs.filter(
                Q(tiene_cita_futura__lt=before_prioridad)
                | Q(
                    tiene_cita_futura=before_prioridad,
                    last_time__lt=before,
                )
                | Q(
                    tiene_cita_futura=before_prioridad,
                    last_time=before,
                    id__lt=before_id,
                )
            )
        else:
            qs = qs.filter(
                Q(tiene_cita_futura__lt=before_prioridad)
                | Q(
                    tiene_cita_futura=before_prioridad,
                    last_time__lt=before,
                )
            )

    consulta = qs.order_by(
        "-tiene_cita_futura",
        "-last_time",
        "-id",
    )
    if paginado:
        pagina = list(consulta[:limit + 1])
        has_more = len(pagina) > limit
        expedientes = pagina[:limit]
    else:
        expedientes = list(consulta[:limit])
        has_more = False

    no_leidos = _contar_no_leidos_chats(expedientes, numero_asesor)
    data = []
    for exp in expedientes:
        dt_original = exp.last_time
        dt_ui = dt_original
        if dt_ui and settings.USE_TZ and timezone.is_aware(dt_ui):
            dt_ui = timezone.localtime(dt_ui)
        telefono = normaliza_tel_mx(exp.cliente.telefono)
        estado_ia = obtener_estado_ia_conversacion(
            numero_asesor=numero_asesor,
            expediente=exp,
        )
        data.append({
            "id": exp.id, "telefono": telefono, "nombre": exp.cliente.nombre or "Prospecto",
            "agencia": exp.agencia or "", "linea": exp.business or "", "estado": exp.estado or "",
            "unread": int(no_leidos.get(telefono, 0)), "last_text": exp.last_text or "",
            "last_time": dt_ui.strftime("%I:%M %p").lower() if dt_ui else "",
            "last_message_at": dt_original.isoformat() if dt_original else None, "numero_asesor": numero_asesor,
            "asesor_digital": exp.asesor_digital or "", "usuario_crm_asignado": exp.usuario_crm_asignado or "",
            # En la lista paginada el detalle de IA se obtiene al abrir el chat; el modo legacy conserva su respuesta anterior.
            "ia_estado": estado_ia,
            "ia_pausada": estado_ia.get("expediente", {}).get("ia_pausada", False) if estado_ia else bool(exp.ia_pausada),
            "ia_bloqueos": estado_ia.get("bloqueos", []) if estado_ia else [],
            "whatsapp_bloqueado": bool(exp.whatsapp_bloqueado),
            "whatsapp_bloqueado_at": exp.whatsapp_bloqueado_at.isoformat() if exp.whatsapp_bloqueado_at else None,
            "whatsapp_bloqueado_motivo": exp.whatsapp_bloqueado_motivo or "",
        })

    if not paginado:
        return Response(data, status=status.HTTP_200_OK)

    ultimo = expedientes[-1] if expedientes else None
    next_scope = "historico" if not busqueda and scope == "recientes" and not has_more else ""
    return Response({
        "ok": True, "results": data,
        "paginacion": {
            "limit": limit, "has_more": has_more, "scope": scope, "next_scope": next_scope,
            "before": ultimo.last_time.isoformat() if ultimo and ultimo.last_time else "",
            "before_id": ultimo.id if ultimo else 0,
            "before_prioridad": ultimo.tiene_cita_futura if ultimo else 0,
            "dias_recientes": dias,
            "query": busqueda,
        },
    }, status=status.HTTP_200_OK)

def _obtener_origen_preview_para_contacto(*, expediente, tel, numero_asesor):
    """
    Recupera la referencia del anuncio desde los primeros mensajes entrantes.

    No depende de que el mensaje original esté dentro de la página visible del
    historial. Usa exclusivamente el raw almacenado por el webhook y, cuando
    no existe referral, devuelve al menos la pauta guardada en el expediente.
    """
    if not expediente:
        return None

    serializer = WhatsAppMessageSerializer()

    mensajes_iniciales = (
        MensajeWhatsApp.objects
        .filter(
            telefono=tel,
            numero_asesor=numero_asesor,
            direction=MensajeWhatsApp.Direccion.IN,
        )
        .only("id", "wa_message_id", "direction", "raw", "created_at")
        .order_by("created_at", "id")[:50]
    )

    for mensaje in mensajes_iniciales:
        preview = serializer.get_origin_preview(mensaje)

        if not preview:
            continue

        return {
            **preview,
            "message_id": mensaje.wa_message_id or str(mensaje.id),
            "created_at": mensaje.created_at.isoformat() if mensaje.created_at else None,
        }

    pauta = str(getattr(expediente, "pauta", "") or "").strip()

    if pauta:
        return {
            "pauta": pauta,
            "nombre_campana": pauta,
            "nombre_anuncio": "",
            "sucursal": str(getattr(expediente, "agencia", "") or "").strip(),
            "headline": pauta,
            "body": "Prospecto originado desde una campaña de Meta.",
            "source_url": "",
            "image_url": "",
            "media_type": "",
            "source_type": "",
            "source_id": "",
            "origen": "expediente_pauta",
            "referral": {},
            "atribucion": {},
            "message_id": "",
            "created_at": None,
        }

    return None


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def contacto_por_telefono(request):
    numero_asesor = _get_numero_asesor_request(request)
    tel = normaliza_tel_mx(request.query_params.get("tel", ""))
    if not tel:
        return Response({"ok": False, "error": "Falta tel"}, status=status.HTTP_400_BAD_REQUEST)

    limit = _int_param(request, "limit", 8, 1, 50)
    before_id = str(request.query_params.get("before_id", "") or "").strip()
    mark_read = str(request.query_params.get("mark_read", "1") or "1").strip().casefold() not in {"0", "false", "no", "off"}
    incluir_contexto = str(request.query_params.get("incluir_contexto", "1") or "1").strip().casefold() not in {"0", "false", "no", "off"}

    cliente = ClienteComercial.objects.filter(telefono=tel).first()
    exp = ExpedienteDigital.objects.select_related("cliente").filter(cliente=cliente).first() if cliente else None
    if not exp:
        return Response({"ok": False, "error": "No existe expediente"}, status=status.HTTP_404_NOT_FOUND)
    _validar_acceso_expediente(request=request, expediente=exp, numero_asesor=numero_asesor)

    qs = MensajeWhatsApp.objects.filter(telefono=tel, numero_asesor=numero_asesor)
    if before_id:
        try:
            id_referencia = int(before_id)
        except (TypeError, ValueError):
            id_referencia = 0
        if id_referencia:
            ref = qs.filter(id=id_referencia).only("id", "created_at").first()
            if ref:
                qs = qs.filter(Q(created_at__lt=ref.created_at) | Q(created_at=ref.created_at, id__lt=ref.id))

    mensajes_desc = list(qs.order_by("-created_at", "-id")[:limit + 1])
    has_more = len(mensajes_desc) > limit
    mensajes = list(reversed(mensajes_desc[:limit]))
    if not before_id and mark_read:
        _mark_read_exp(exp, numero_asesor)

    prospecto_data, ia_estado = None, None
    if incluir_contexto:
        ia_estado = obtener_estado_ia_conversacion(tel=tel, numero_asesor=numero_asesor, expediente=exp)
        prospecto_data = ProspectoSerializer(exp, context={"request": request}).data
        prospecto_data["origen_preview"] = _obtener_origen_preview_para_contacto(
            expediente=exp, tel=tel, numero_asesor=numero_asesor
        )

    oldest_id = mensajes[0].id if mensajes else None
    newest_id = mensajes[-1].id if mensajes else None
    return Response({
        "ok": True, "numero_asesor_activo": numero_asesor, "prospecto": prospecto_data, "ia_estado": ia_estado,
        "mensajes": WhatsAppMessageSerializer(mensajes, many=True, context={"request": request}).data,
        "paginacion": {
            "limit": limit, "has_more": has_more, "oldest_id": oldest_id, "newest_id": newest_id,
            "oldest_created_at": mensajes[0].created_at.isoformat() if mensajes and mensajes[0].created_at else None,
            "newest_created_at": mensajes[-1].created_at.isoformat() if mensajes and mensajes[-1].created_at else None,
            "before_id": oldest_id,
        },
    }, status=status.HTTP_200_OK)

@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def llamar_whatsapp(request):
    numero_asesor = _get_numero_asesor_request(request)
    telefono = normaliza_tel_mx(
        request.data.get("telefono", "")
    )

    if not telefono:
        return Response(
            {"ok": False, "error": "Falta telefono"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    cliente = ClienteComercial.objects.filter(
        telefono=telefono,
    ).first()

    expediente = (
        ExpedienteDigital.objects
        .select_related("cliente")
        .filter(cliente=cliente)
        .first()
        if cliente
        else None
    )

    _validar_acceso_expediente(
        request=request,
        expediente=expediente,
        numero_asesor=numero_asesor,
    )

    try:
        resultado = iniciar_llamada_whatsapp(
            to=telefono,
            numero_asesor=numero_asesor,
            sdp_offer=request.data.get("sdp_offer", ""),
        )

        registrar_evento_operativo(
            expediente=expediente,
            numero_asesor=numero_asesor,
            tipo="llamada",
            accion="Inició una llamada de WhatsApp",
            request=request,
            metadata={"respuesta_meta": resultado},
        )

        return Response(
            {"ok": True, "data": resultado},
            status=status.HTTP_200_OK,
        )

    except PermissionDenied:
        raise

    except Exception as e:
        logger.exception(
            "ERROR LLAMADA WHATSAPP: %s",
            str(e),
        )

        return Response(
            {"ok": False, "error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def generar_resumen_prospecto_view(request, prospecto_id: int):
    numero_asesor = _get_numero_asesor_request(request)

    exp = (
        ExpedienteDigital.objects
        .select_related("cliente")
        .filter(id=prospecto_id)
        .first()
    )

    if not exp:
        return Response(
            {"ok": False, "error": "Prospecto no encontrado"},
            status=status.HTTP_404_NOT_FOUND,
        )

    _validar_acceso_expediente(
        request=request,
        expediente=exp,
        numero_asesor=numero_asesor,
    )

    try:
        resumen = generar_y_guardar_resumen(
            expediente=exp,
            fuente="manual",
        )

        return Response({
            "ok": True,
            "id": exp.id,
            "resumen": resumen,
            "resumen_actualizado_at": (
                exp.resumen_actualizado_at.isoformat()
                if exp.resumen_actualizado_at
                else None
            ),
            "resumen_fuente": exp.resumen_fuente or "",
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"ok": False, "error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def mark_read_view(request):
    numero_asesor = _get_numero_asesor_request(request)
    tel = normaliza_tel_mx(request.data.get("tel", ""))
    if not tel:
        return Response({"ok": False, "error": "Falta tel"}, status=status.HTTP_400_BAD_REQUEST)
    cliente = ClienteComercial.objects.filter(telefono=tel).first()
    if not cliente:
        return Response({"ok": False, "error": "No existe prospecto"}, status=status.HTTP_404_NOT_FOUND)
    exp = ExpedienteDigital.objects.filter(cliente=cliente).first()
    if not exp:
        return Response(
            {"ok": False, "error": "No existe expediente"},
            status=status.HTTP_404_NOT_FOUND,
        )

    _validar_acceso_expediente(
        request=request,
        expediente=exp,
        numero_asesor=numero_asesor,
    )

    _mark_read_exp(exp, numero_asesor)
    return Response({"ok": True}, status=status.HTTP_200_OK)


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def contacto_updates(request):
    numero_asesor = _get_numero_asesor_request(request)
    tel = normaliza_tel_mx(request.query_params.get("tel", ""))
    after = str(request.query_params.get("after", "") or "").strip()
    try:
        after_id = int(request.query_params.get("after_id", "") or 0)
    except (TypeError, ValueError):
        after_id = 0
    limit = _int_param(request, "limit", 50, 1, 100)
    tracked_ids_raw = str(request.query_params.get("tracked_ids", "") or "").strip()
    tracked_ids = []

    if tracked_ids_raw:
        for value in tracked_ids_raw.split(","):
            try:
                tracked_ids.append(int(value))
            except (TypeError, ValueError):
                continue

        tracked_ids = tracked_ids[:100]
    if not tel:
        return Response({"ok": False, "error": "Falta tel"}, status=status.HTTP_400_BAD_REQUEST)

    cliente = ClienteComercial.objects.filter(telefono=tel).first()
    exp = ExpedienteDigital.objects.select_related("cliente").filter(cliente=cliente).first() if cliente else None
    _validar_acceso_expediente(request=request, expediente=exp, numero_asesor=numero_asesor)

    qs = MensajeWhatsApp.objects.filter(telefono=tel, numero_asesor=numero_asesor).order_by("created_at", "id")
    after_dt = _parse_dt_param(after)
    if after_dt and after_id:
        qs = qs.filter(Q(created_at__gt=after_dt) | Q(created_at=after_dt, id__gt=after_id))
    elif after_dt:
        qs = qs.filter(created_at__gt=after_dt)
    elif after_id:
        qs = qs.filter(id__gt=after_id)
    else:
        qs = qs.none()

    mensajes = list(qs[:limit])

    status_updates = []
    if tracked_ids:
        status_updates = list(
            MensajeWhatsApp.objects.filter(
                id__in=tracked_ids,
                telefono=tel,
                numero_asesor=numero_asesor,
                direction=MensajeWhatsApp.Direccion.OUT,
            )
        )

    return Response({
        "ok": True,
        "numero_asesor_activo": numero_asesor,
        "mensajes": WhatsAppMessageSerializer(
            mensajes,
            many=True,
            context={"request": request},
        ).data,
        "status_updates": WhatsAppMessageSerializer(
            status_updates,
            many=True,
            context={"request": request},
        ).data,
        "server_now": timezone.now().isoformat(),
    }, status=status.HTTP_200_OK)

@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def enviar_mensaje_view(request):
    numero_asesor = _get_numero_asesor_request(request)
    to = normaliza_tel_mx(request.data.get("to", ""))
    text = (request.data.get("text") or "").strip()
    reply_to_message_id = (request.data.get("reply_to_message_id") or "").strip()

    if not to or not text:
        return Response(
            {"ok": False, "error": "Falta to o text"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    cliente = None

    try:
        cliente, exp = _get_or_create_cliente_y_expediente(
            tel=to,
            numero_asesor=numero_asesor,
            aplicar_reparto=False,
        )

        exp = _asegurar_asignacion_salida_manual(
            request=request,
            expediente=exp,
            numero_asesor=numero_asesor,
        )

        _validar_acceso_expediente(
            request=request,
            expediente=exp,
            numero_asesor=numero_asesor,
        )

        if getattr(exp, "whatsapp_bloqueado", False):
            return Response(
                {
                    "ok": False,
                    "error": "Este contacto está bloqueado en WhatsApp. Desbloquéalo antes de enviar mensajes.",
                    "tel": to,
                    "numero_asesor": numero_asesor,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        exp.touch_contacto_asesor(save_now=True)

        wa_res = enviar_texto_whatsapp(
            to=to,
            text=text,
            numero_asesor=numero_asesor,
            reply_to_message_id=reply_to_message_id,
        )

        wa_message_id = _extraer_wa_message_id(wa_res)

        mensaje_enviado = MensajeWhatsApp.objects.create(
            telefono=to,
            numero_asesor=numero_asesor,
            cliente=cliente,
            direction="out",
            body=text,
            wa_message_id=wa_message_id,
            status="accepted",
            raw={
                "provider": "meta",
                "send": wa_res,
                "numero_asesor": numero_asesor,
                "origen": "asesor_humano",
                "reply_to": reply_to_message_id,
            },
        )
        registrar_evento_mensaje(
            mensaje_enviado,
            request=request,
            expediente=exp,
            tipo="mensaje",
        )

        #pausar_ia_por_intervencion_humana(exp, numero_asesor)

        return Response(
            {
                "ok": True,
                "data": wa_res,
                "wa_message_id": wa_message_id,
                "numero_asesor": numero_asesor,
            },
            status=status.HTTP_200_OK,
        )

    except PermissionDenied:
        raise

    except MetaAPIError as e:
        logger.warning(
            "FALLO META ENVIAR MENSAJE | to=%s numero_asesor=%s retryable=%s meta=%s",
            to,
            numero_asesor,
            e.retryable,
            e.to_dict(),
        )

        _guardar_mensaje_fallido(
            to=to,
            numero_asesor=numero_asesor,
            cliente=cliente,
            body=text,
            error=e,
            extra_raw={
                "request_type": "text",
            },
        )

        return _response_meta_error(
            e,
            numero_asesor=numero_asesor,
            extra={
                "tipo": "text",
                "to": to,
            },
        )

    except Exception as e:
        logger.exception(
            "ERROR INTERNO ENVIAR MENSAJE | to=%s numero_asesor=%s error=%s",
            to,
            numero_asesor,
            str(e),
        )

        _guardar_mensaje_fallido(
            to=to,
            numero_asesor=numero_asesor,
            cliente=cliente,
            body=text,
            error=e,
            extra_raw={
                "request_type": "text",
                "internal_error": True,
            },
        )

        return Response(
            {
                "ok": False,
                "error": str(e),
                "retryable": False,
                "numero_asesor": numero_asesor,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

def pausar_ia_por_intervencion_humana(expediente, numero_asesor):
    expediente.ia_pausada = True
    expediente.ia_pausada_motivo = "intervencion_humana"
    expediente.ia_pausada_at = timezone.now()
    expediente.save(update_fields=[
        "ia_pausada",
        "ia_pausada_motivo",
        "ia_pausada_at",
        "actualizado",
    ])

    conv, _ = ConversacionIA.objects.get_or_create(
        expediente=expediente,
        numero_asesor=numero_asesor,
    )

    conv.ia_activa = False
    conv.ia_pausada = True
    conv.motivo_pausa = "intervencion_humana"
    conv.estado_conversacion = "pausada"
    conv.save(update_fields=[
        "ia_activa",
        "ia_pausada",
        "motivo_pausa",
        "estado_conversacion",
    ])

@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def enviar_media_view(request):
    numero_asesor = _get_numero_asesor_request(request)

    to = normaliza_tel_mx(
        request.data.get("to", "")
    )

    caption = (
        request.data.get("text")
        or ""
    ).strip()

    reply_to_message_id = (
        request.data.get("reply_to_message_id")
        or ""
    ).strip()

    files = request.FILES.getlist("files") or []

    if not to:
        return Response(
            {
                "ok": False,
                "error": "Falta to",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not files:
        return Response(
            {
                "ok": False,
                "error": "Faltan files",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    cliente, exp = _get_or_create_cliente_y_expediente(
        tel=to,
        numero_asesor=numero_asesor,
        aplicar_reparto=False,
    )

    exp = _asegurar_asignacion_salida_manual(
        request=request,
        expediente=exp,
        numero_asesor=numero_asesor,
    )

    _validar_acceso_expediente(
        request=request,
        expediente=exp,
        numero_asesor=numero_asesor,
    )

    if getattr(
        exp,
        "whatsapp_bloqueado",
        False,
    ):
        return Response(
            {
                "ok": False,
                "error": (
                    "Este contacto está bloqueado en WhatsApp. "
                    "Desbloquéalo antes de enviar mensajes."
                ),
                "tel": to,
                "numero_asesor": numero_asesor,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    exp.touch_contacto_asesor(
        save_now=True
    )

    sent = []
    failed = []

    for file_obj in files:
        original_name = (
            getattr(file_obj, "name", "archivo")
            or "archivo"
        )

        original_ct = (
            getattr(file_obj, "content_type", "")
            or mimetypes.guess_type(original_name)[0]
            or "application/octet-stream"
        )

        local_media_url = ""

        try:
            # Para audio:
            #   convierte WebM/M4A/WAV/etc. a OGG/Opus.
            #
            # Para otros archivos:
            #   devuelve el mismo archivo sin cambios.
            with preparar_media_whatsapp(
                file_obj,
                filename=original_name,
                content_type=original_ct,
            ) as prepared:

                send_file = prepared.archivo
                name = prepared.nombre

                ct = (
                    prepared.content_type
                    or "application/octet-stream"
                )

                # Determinar el tipo de mensaje que se enviará a Meta.
                if ct.startswith("image/"):
                    wtype = "image"

                elif ct.startswith("video/"):
                    wtype = "video"

                elif es_archivo_audio(name, ct):
                    wtype = "audio"

                else:
                    wtype = "document"

                # Regresar el puntero al inicio antes de guardar localmente.
                try:
                    send_file.seek(0)
                except Exception:
                    pass

                local_media_url = _guardar_upload_whatsapp_local(
                    send_file,
                    numero_asesor=numero_asesor,
                    telefono=to,
                    content_type=ct,
                )

                # _guardar_upload_whatsapp_local ya consumió el archivo.
                # Debemos volver al inicio antes de subirlo a Meta.
                try:
                    send_file.seek(0)
                except Exception:
                    pass

                up = subir_media_whatsapp(
                    send_file,
                    numero_asesor=numero_asesor,
                    filename=name,
                    content_type=ct,
                )

                media_id = up.get("id") or ""

                if not media_id:
                    raise RuntimeError(
                        f"Meta no regresó media_id: {up}"
                    )

                wa_res = enviar_media_whatsapp(
                    to=to,
                    media_id=media_id,
                    media_type=wtype,
                    numero_asesor=numero_asesor,

                    # WhatsApp no permite caption en audios.
                    # enviar_media_whatsapp ya limita el caption
                    # a image, video y document.
                    caption=caption if caption else "",

                    filename=(
                        name
                        if wtype == "document"
                        else ""
                    ),

                    reply_to_message_id=reply_to_message_id,
                )

                wa_message_id = _extraer_wa_message_id(
                    wa_res
                )

                body = caption if caption else ""

                if body:
                    body = (
                        f"{body}\n[FILE:{name}]"
                    ).strip()
                else:
                    body = f"[FILE:{name}]"

                raw = {
                    "provider": "meta",
                    "meta_upload": up,
                    "send": wa_res,
                    "meta_type": wtype,

                    # Nombre que realmente se envió.
                    "filename": name,

                    # Nombre que llegó desde el navegador.
                    "original_filename": prepared.nombre_original,

                    # MIME que realmente se envió.
                    "content_type": ct,

                    # MIME original del navegador.
                    "original_content_type": original_ct,

                    # Permite diagnosticar si FFmpeg fue utilizado.
                    "audio_converted": prepared.convertido,

                    "numero_asesor": numero_asesor,
                    "media_id": media_id,
                    "local_media_url": local_media_url,

                    "media_link": (
                        local_media_url
                        if wtype in (
                            "image",
                            "video",
                            "audio",
                        )
                        else ""
                    ),

                    "document_link": (
                        local_media_url
                        if wtype == "document"
                        else ""
                    ),

                    "reply_to": reply_to_message_id,
                }

                mensaje_media = MensajeWhatsApp.objects.create(
                    telefono=to,
                    numero_asesor=numero_asesor,
                    cliente=cliente,
                    direction="out",
                    body=body,
                    wa_message_id=wa_message_id,
                    status="accepted",
                    raw=raw,
                )
                registrar_evento_mensaje(
                    mensaje_media,
                    request=request,
                    expediente=exp,
                    tipo="media",
                )

                sent.append(
                    {
                        "filename": name,
                        "original_filename": (
                            prepared.nombre_original
                        ),
                        "type": wtype,
                        "content_type": ct,
                        "converted": prepared.convertido,
                        "data": wa_res,
                        "wa_message_id": wa_message_id,
                        "local_media_url": local_media_url,
                    }
                )

        except MetaAPIError as error:
            logger.warning(
                (
                    "FALLO META ENVIAR MEDIA | "
                    "to=%s numero_asesor=%s "
                    "file=%s retryable=%s meta=%s"
                ),
                to,
                numero_asesor,
                original_name,
                error.retryable,
                error.to_dict(),
            )

            _guardar_mensaje_fallido(
                to=to,
                numero_asesor=numero_asesor,
                cliente=cliente,
                body=f"[FILE:{original_name}] failed",
                error=error,
                extra_raw={
                    "request_type": "media",
                    "filename": original_name,
                    "content_type": original_ct,
                    "local_media_url": local_media_url,
                },
            )

            failed.append(
                {
                    "filename": original_name,
                    "error": error.meta_message,
                    "retryable": error.retryable,
                    "meta": error.to_dict(),
                }
            )

        except Exception as error:
            logger.exception(
                (
                    "ERROR ENVIAR MEDIA | "
                    "to=%s numero_asesor=%s "
                    "file=%s error=%s"
                ),
                to,
                numero_asesor,
                original_name,
                str(error),
            )

            _guardar_mensaje_fallido(
                to=to,
                numero_asesor=numero_asesor,
                cliente=cliente,
                body=f"[FILE:{original_name}] failed",
                error=error,
                extra_raw={
                    "request_type": "media",
                    "filename": original_name,
                    "content_type": original_ct,
                    "local_media_url": local_media_url,
                    "internal_error": True,
                },
            )

            failed.append(
                {
                    "filename": original_name,
                    "error": str(error),
                    "retryable": False,
                }
            )

    response_status = (
        status.HTTP_200_OK
        if sent
        else status.HTTP_400_BAD_REQUEST
    )

    return Response(
        {
            "ok": bool(sent),
            "sent": sent,
            "failed": failed,
            "numero_asesor": numero_asesor,
        },
        status=response_status,
    )

@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def enviar_plantilla_view(request):
    numero_asesor = _get_numero_asesor_request(request)
    to = normaliza_tel_mx(request.data.get("to", ""))
    template_name = (request.data.get("template_name") or "").strip()
    params = request.data.get("params")
    components = request.data.get("components")
    idioma = (request.data.get("idioma") or "es_MX").strip()

    if not to:
        return Response(
            {"ok": False, "error": "Falta to"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not template_name:
        return Response(
            {"ok": False, "error": "Falta template_name"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if components is not None and not isinstance(components, list):
        return Response(
            {"ok": False, "error": "components debe ser lista"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if components is None:
        if params is None:
            params = []

        if not isinstance(params, list):
            return Response(
                {"ok": False, "error": "params debe ser lista"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    cliente = None

    try:
        cliente, exp = _get_or_create_cliente_y_expediente(
            tel=to,
            numero_asesor=numero_asesor,
            aplicar_reparto=False,
        )

        exp = _asegurar_asignacion_salida_manual(
            request=request,
            expediente=exp,
            numero_asesor=numero_asesor,
        )

        _validar_acceso_expediente(
            request=request,
            expediente=exp,
            numero_asesor=numero_asesor,
        )

        if getattr(exp, "whatsapp_bloqueado", False):
            return Response(
                {
                    "ok": False,
                    "error": "Este contacto está bloqueado en WhatsApp. Desbloquéalo antes de enviar mensajes.",
                    "tel": to,
                    "numero_asesor": numero_asesor,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        exp.touch_contacto_asesor(save_now=True)

        wa_res = enviar_template_whatsapp(
            to=to,
            template_name=template_name,
            numero_asesor=numero_asesor,
            params=[str(x) for x in (params or [])],
            idioma=idioma,
            components=components,
        )

        wa_message_id = _extraer_wa_message_id(wa_res)

        body_log = f"[TEMPLATE:{template_name}]"

        if components:
            flat = []

            for component in components:
                for parametro in (component.get("parameters") or []):
                    if parametro.get("type") == "text":
                        flat.append(str(parametro.get("text") or ""))

            if flat:
                body_log += " " + " | ".join(flat)

        else:
            body_log += " " + " | ".join([str(x) for x in (params or [])])

        mensaje_plantilla = MensajeWhatsApp.objects.create(
            telefono=to,
            numero_asesor=numero_asesor,
            cliente=cliente,
            direction="out",
            body=body_log.strip(),
            wa_message_id=wa_message_id,
            status="accepted",
            raw={
                "provider": "meta",
                "type": "template",
                "send": wa_res,
                "numero_asesor": numero_asesor,
                "template_name": template_name,
                "idioma": idioma,
                "params": params or [],
                "components": components or [],
                "origen": "asesor_humano",
            },
        )
        registrar_evento_mensaje(
            mensaje_plantilla,
            request=request,
            expediente=exp,
            tipo="plantilla",
        )
        
        #pausar_ia_por_intervencion_humana(exp, numero_asesor)

        return Response(
            {
                "ok": True,
                "data": wa_res,
                "wa_message_id": wa_message_id,
                "numero_asesor": numero_asesor,
            },
            status=status.HTTP_200_OK,
        )

    except PermissionDenied:
        raise

    except MetaAPIError as e:
        logger.warning(
            "FALLO META ENVIAR PLANTILLA | to=%s numero_asesor=%s template=%s retryable=%s meta=%s",
            to,
            numero_asesor,
            template_name,
            e.retryable,
            e.to_dict(),
        )

        _guardar_mensaje_fallido(
            to=to,
            numero_asesor=numero_asesor,
            cliente=cliente,
            body=f"[TEMPLATE:{template_name}] failed",
            error=e,
            extra_raw={
                "request_type": "template",
                "template_name": template_name,
                "idioma": idioma,
                "params": params or [],
                "components": components or [],
            },
        )

        return _response_meta_error(
            e,
            numero_asesor=numero_asesor,
            extra={
                "tipo": "template",
                "to": to,
                "template_name": template_name,
                "idioma": idioma,
            },
        )

    except Exception as e:
        logger.exception(
            "ERROR INTERNO ENVIAR PLANTILLA | to=%s numero_asesor=%s template=%s error=%s",
            to,
            numero_asesor,
            template_name,
            str(e),
        )

        _guardar_mensaje_fallido(
            to=to,
            numero_asesor=numero_asesor,
            cliente=cliente,
            body=f"[TEMPLATE:{template_name}] failed",
            error=e,
            extra_raw={
                "request_type": "template",
                "template_name": template_name,
                "idioma": idioma,
                "params": params or [],
                "components": components or [],
                "internal_error": True,
            },
        )

        return Response(
            {
                "ok": False,
                "error": str(e),
                "retryable": False,
                "numero_asesor": numero_asesor,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def campanas_meta_recientes(request):
    try:
        days = int(request.query_params.get("days", "30"))
    except ValueError:
        days = 30

    cutoff = date.today() - timedelta(days=days)
    qs = CampanaMeta.objects.using("sqlserver").filter(
        Q(inicio_campana__gte=cutoff) | Q(fin_campana__gte=cutoff)
    ).order_by("-inicio_campana", "-fin_campana")

    seen, out = set(), []
    for c in qs[:500]:
        label = f"{(c.sucursal or '').strip()} - {(c.nombre_campana or '').strip()}".strip(" -")
        if not label or label in seen:
            continue
        seen.add(label)
        out.append({"value": label, "label": label})

    return Response({"ok": True, "items": out}, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def editar_mensaje_view(request):
    numero_asesor = _get_numero_asesor_request(request)
    to = normaliza_tel_mx(request.data.get("to", ""))
    message_id = (request.data.get("message_id") or "").strip()
    text = (request.data.get("text") or "").strip()

    if not to or not message_id or not text:
        return Response({"ok": False, "error": "Falta to, message_id o text"}, status=400)

    msg = MensajeWhatsApp.objects.filter(
        telefono=to, numero_asesor=numero_asesor, wa_message_id=message_id,
    ).first()

    if not msg:
        return Response(
            {"ok": False, "error": "Mensaje no encontrado"},
            status=status.HTTP_404_NOT_FOUND,
        )

    expediente = (
        ExpedienteDigital.objects
        .select_related("cliente")
        .filter(cliente=msg.cliente)
        .first()
        if msg.cliente_id
        else None
    )

    _validar_acceso_expediente(
        request=request,
        expediente=expediente,
        numero_asesor=numero_asesor,
    )

    if msg.direction != "out":
        return Response({"ok": False, "error": "Solo puedes editar mensajes enviados"}, status=400)
    if (msg.body or "").startswith("[TEMPLATE:"):
        return Response({"ok": False, "error": "No se editan plantillas ya enviadas"}, status=400)
    if msg.created_at and timezone.now() - msg.created_at > timedelta(minutes=15):
        return Response({"ok": False, "error": "Ya no es editable (ventana expiró)"}, status=400)

    try:
        wa_res = editar_texto_whatsapp(
            to=to, original_message_id=message_id, new_text=text, numero_asesor=numero_asesor,
        )
        msg.body = text
        raw = dict(msg.raw or {})
        raw["edit_response"] = wa_res
        msg.raw = raw
        msg.save(update_fields=["body", "raw"])
        return Response({"ok": True, "data": wa_res}, status=200)
    except Exception as e:
        return Response({"ok": False, "error": str(e)}, status=400)


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def plantillas_whatsapp_view(request):
    try:
        numero_asesor = _get_numero_asesor_request(request)
        templates = obtener_templates_whatsapp(numero_asesor)
        cfg = WHATSAPP_LINES.get(numero_asesor, {})
        return Response({
            "ok": True,
            "numero_asesor": numero_asesor,
            "linea": {
                "key": cfg.get("key", ""),
                "asesor_digital": cfg.get("asesor_digital", ""),
                "agencia": cfg.get("agencia", ""),
                "business": cfg.get("business", ""),
                "phone_number_id": cfg.get("phone_number_id", ""),
            },
            "items": templates,
        }, status=200)
    except Exception as e:
        return Response({"ok": False, "error": str(e), "items": []}, status=400)

@api_view(["POST"])
@authentication_classes([
    CRMJWTAuthentication
])
@permission_classes([
    IsAuthenticated
])
@parser_classes([
    MultiPartParser,
    FormParser,
])
def plantilla_whatsapp_admin_media_view(
    request,
):
    numero_asesor = (
        _get_numero_asesor_request(
            request
        )
    )

    archivo = (
        request.FILES.get(
            "file"
        )
        or request.FILES.get(
            "archivo"
        )
    )

    formato = str(
        request.data.get(
            "format",
            "",
        )
        or ""
    ).strip().upper()

    if not archivo:
        return Response(
            {
                "ok": False,
                "error": (
                    "No se recibió ningún archivo."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        resultado = (
            subir_media_plantilla_meta(
                numero_asesor=
                    numero_asesor,
                archivo=
                    archivo,
                formato=
                    formato,
            )
        )

        return Response(
            {
                "ok": True,
                "numero_asesor":
                    numero_asesor,
                **resultado,
            },
            status=status.HTTP_200_OK,
        )

    except MetaAPIError as exc:
        return _response_meta_error(
            exc,
            numero_asesor=
                numero_asesor,
            extra={
                "tipo":
                    "template_media_upload",
            },
        )

    except ValueError as exc:
        return Response(
            {
                "ok": False,
                "error": str(
                    exc
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    except Exception as exc:
        logger.exception(
            "ERROR SUBIENDO MEDIA DE PLANTILLA "
            "| numero=%s error=%s",
            numero_asesor,
            exc,
        )

        return Response(
            {
                "ok": False,
                "error": (
                    "No se pudo cargar "
                    "la muestra multimedia."
                ),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    
@api_view(["GET", "POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def plantillas_whatsapp_admin_view(request):
    """
    Administración de plantillas de la WABA asociada a la línea del usuario.

    GET  -> lista todos los estados: APPROVED, PENDING, REJECTED, PAUSED, etc.
    POST -> crea una plantilla y la envía a revisión de Meta.
    """
    numero_asesor = _get_numero_asesor_request(request)
    cfg = WHATSAPP_LINES.get(numero_asesor, {})

    if request.method == "GET":
        try:
            items = listar_plantillas_meta(numero_asesor)
            return Response({
                "ok": True,
                "numero_asesor": numero_asesor,
                "linea": {
                    "key": cfg.get("key", ""),
                    "asesor_digital": cfg.get("asesor_digital", ""),
                    "agencia": cfg.get("agencia", ""),
                    "business": cfg.get("business", ""),
                    "phone_number_id": cfg.get("phone_number_id", ""),
                    "waba_id": cfg.get("waba_id", ""),
                },
                "reglas_utility": REGLAS_UTILITY,
                "items": items,
            }, status=status.HTTP_200_OK)
        except MetaAPIError as exc:
            return _response_meta_error(exc, numero_asesor=numero_asesor, extra={"tipo": "template_list"})
        except Exception as exc:
            logger.exception("ERROR LISTANDO PLANTILLAS META | numero=%s error=%s", numero_asesor, exc)
            return Response({"ok": False, "error": str(exc), "items": []}, status=status.HTTP_400_BAD_REQUEST)

    try:
        resultado = crear_plantilla_meta(numero_asesor, dict(request.data or {}))
        return Response({
            "ok": True,
            "numero_asesor": numero_asesor,
            "mensaje": "Plantilla enviada a revisión de Meta.",
            **resultado,
        }, status=status.HTTP_201_CREATED)
    except MetaAPIError as exc:
        return _response_meta_error(exc, numero_asesor=numero_asesor, extra={"tipo": "template_create"})
    except ValueError as exc:
        analysis = getattr(exc, "analysis", None)
        return Response({
            "ok": False,
            "error": str(exc),
            "analysis": analysis,
            "requires_confirmation": bool(analysis and analysis.get("requiere_confirmacion")),
        }, status=status.HTTP_409_CONFLICT if analysis else status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.exception("ERROR CREANDO PLANTILLA META | numero=%s error=%s", numero_asesor, exc)
        return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

TEMPLATE_MEDIA_RULES = {
    "image": {
        "mime": {
            "image/jpeg",
            "image/png",
        },
        "max_bytes": 5 * 1024 * 1024,
        "max_label": "5 MB",
    },
    "video": {
        "mime": {
            "video/mp4",
        },
        "max_bytes": 16 * 1024 * 1024,
        "max_label": "16 MB",
    },
    "document": {
        "mime": {
            "application/pdf",
        },
        "max_bytes": 100 * 1024 * 1024,
        "max_label": "100 MB",
    },
}


@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def subir_media_plantilla_view(request):
    numero_asesor = _get_numero_asesor_request(
        request
    )

    file_obj = request.FILES.get(
        "file"
    )

    media_type = str(
        request.data.get(
            "media_type",
            ""
        )
    ).lower().strip()

    if not file_obj:
        return Response(
            {
                "ok": False,
                "error": "Falta el archivo.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    rule = TEMPLATE_MEDIA_RULES.get(
        media_type
    )

    if not rule:
        return Response(
            {
                "ok": False,
                "error": "Tipo multimedia no válido.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    filename = str(
        getattr(
            file_obj,
            "name",
            "archivo"
        )
    )

    content_type = str(
        getattr(
            file_obj,
            "content_type",
            ""
        )
        or mimetypes.guess_type(
            filename
        )[0]
        or ""
    ).lower()

    if content_type not in rule["mime"]:
        return Response(
            {
                "ok": False,
                "error": (
                    f"Formato no permitido "
                    f"para {media_type}."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    file_size = int(
        getattr(
            file_obj,
            "size",
            0
        )
        or 0
    )

    if file_size > rule["max_bytes"]:
        return Response(
            {
                "ok": False,
                "error": (
                    "El archivo supera "
                    f"el límite de "
                    f"{rule['max_label']}."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        try:
            file_obj.seek(0)
        except Exception:
            pass

        result = subir_media_whatsapp(
            file_obj,
            numero_asesor=numero_asesor,
            filename=filename,
            content_type=content_type,
        )

        media_id = str(
            result.get("id") or ""
        ).strip()

        if not media_id:
            raise RuntimeError(
                "Meta no regresó media_id."
            )

        return Response(
            {
                "ok": True,
                "media_id": media_id,
                "id": media_id,
                "media_type": media_type,
                "filename": filename,
                "mime": content_type,
                "size": file_size,
                "numero_asesor":
                    numero_asesor,
            },
            status=status.HTTP_200_OK,
        )

    except MetaAPIError as error:
        logger.warning(
            (
                "FALLO SUBIR MEDIA PLANTILLA | "
                "numero_asesor=%s "
                "media_type=%s "
                "filename=%s "
                "error=%s"
            ),
            numero_asesor,
            media_type,
            filename,
            str(error),
        )

        return Response(
            {
                "ok": False,
                "error": getattr(
                    error,
                    "meta_message",
                    str(error),
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    except Exception as error:
        logger.exception(
            (
                "ERROR SUBIR MEDIA PLANTILLA | "
                "numero_asesor=%s "
                "media_type=%s "
                "filename=%s"
            ),
            numero_asesor,
            media_type,
            filename,
        )

        return Response(
            {
                "ok": False,
                "error": str(error),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    
@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def analizar_plantilla_whatsapp_view(request):
    """
    Analiza estructura, variables, ejemplos, botones y riesgo comercial.
    No crea ni modifica nada en Meta.
    """
    category = str(request.data.get("category") or "UTILITY").upper().strip()
    components = request.data.get("components")

    if components is None:
        components = []

    analysis = analizar_estructura_plantilla(components, category)

    return Response({
        "ok": True,
        "numero_asesor": _get_numero_asesor_request(request),
        "analysis": analysis,
    }, status=status.HTTP_200_OK)


@api_view(["PATCH", "DELETE"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def plantilla_whatsapp_admin_detail_view(request, template_id: str):
    numero_asesor = _get_numero_asesor_request(request)
    template_id = str(template_id or "").strip()

    if not template_id:
        return Response({"ok": False, "error": "Falta template_id."}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":
        name = str(request.query_params.get("name") or request.data.get("name") or "").strip()

        try:
            meta = eliminar_plantilla_meta(numero_asesor, template_id, name)
            return Response({
                "ok": True,
                "mensaje": "Plantilla eliminada correctamente.",
                "meta": meta,
            }, status=status.HTTP_200_OK)
        except MetaAPIError as exc:
            return _response_meta_error(exc, numero_asesor=numero_asesor, extra={"tipo": "template_delete"})
        except Exception as exc:
            logger.exception("ERROR ELIMINANDO PLANTILLA META | numero=%s template=%s error=%s", numero_asesor, template_id, exc)
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    try:
        resultado = editar_plantilla_meta(numero_asesor, template_id, dict(request.data or {}))
        return Response({
            "ok": True,
            "numero_asesor": numero_asesor,
            "mensaje": "Cambios enviados a revisión de Meta.",
            **resultado,
        }, status=status.HTTP_200_OK)
    except MetaAPIError as exc:
        return _response_meta_error(exc, numero_asesor=numero_asesor, extra={"tipo": "template_edit"})
    except ValueError as exc:
        analysis = getattr(exc, "analysis", None)
        return Response({
            "ok": False,
            "error": str(exc),
            "analysis": analysis,
            "requires_confirmation": bool(analysis and analysis.get("requiere_confirmacion")),
        }, status=status.HTTP_409_CONFLICT if analysis else status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.exception("ERROR EDITANDO PLANTILLA META | numero=%s template=%s error=%s", numero_asesor, template_id, exc)
        return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


# ── Catálogo de Precios ───────────────────────────────────────────────────────

@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def catalogo_precios_actuales(request):
    qs = CatalogoVehiculos.objects.filter(activo=True)

    precios = {}

    for item in qs.order_by("modelo", "ano", "version"):
        key = f"{item.modelo} {item.ano}".strip()

        if key not in precios:
            precios[key] = {
                "modelo": item.modelo,
                "ano": item.ano,
                "precio_desde": item.precio_lista,
                "versiones": [],
            }

        precios[key]["versiones"].append({
            "id": item.id,
            "version": item.version,
            "precio_lista": item.precio_lista,
            "precio_contado": item.precio_contado,
            "precio_financiado": item.precio_financiado,
        })

        if item.precio_lista:
            precio_actual = precios[key].get("precio_desde")

            if not precio_actual or item.precio_lista < precio_actual:
                precios[key]["precio_desde"] = item.precio_lista

    return Response({
        "ok": True,
        "precios": precios,
    })

@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def mark_unread_view(request):
    numero_asesor = _get_numero_asesor_request(request)
    tel = normaliza_tel_mx(request.data.get("tel", ""))

    if not tel:
        return Response({"ok": False, "error": "Falta tel"}, status=400)

    cliente = ClienteComercial.objects.filter(telefono=tel).first()
    if not cliente:
        return Response({"ok": False, "error": "No existe prospecto"}, status=404)

    exp = ExpedienteDigital.objects.filter(cliente=cliente).first()
    if not exp:
        return Response(
            {"ok": False, "error": "No existe expediente"},
            status=status.HTTP_404_NOT_FOUND,
        )

    _validar_acceso_expediente(
        request=request,
        expediente=exp,
        numero_asesor=numero_asesor,
    )

    lectura = LecturaWhatsApp.objects.filter(
        expediente=exp,
        numero_asesor=numero_asesor,
    ).first()

    if lectura:
        lectura.last_read_at = None
        lectura.save(update_fields=["last_read_at", "updated_at"])

    return Response({"ok": True}, status=200)

def _usuario_nombre_para_auditoria(request) -> str:
    user = _get_usuario_request_obj(request)

    if user:
        return (
            getattr(user, "usuario", "")
            or getattr(user, "username", "")
            or getattr(user, "email", "")
            or ""
        ).strip()

    return _obtener_usuario_crm_request(request)


def _meta_block_added(data: dict) -> list:
    block_users = data.get("block_users") if isinstance(data, dict) else {}
    if not isinstance(block_users, dict):
        return []

    return (
        block_users.get("added_users")
        or block_users.get("removed_users")
        or []
    )


def _meta_block_failed(data: dict) -> list:
    block_users = data.get("block_users") if isinstance(data, dict) else {}
    if not isinstance(block_users, dict):
        return []

    return (
        block_users.get("failed_users")
        or block_users.get("errors")
        or []
    )


@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def bloquear_contacto_whatsapp_view(request):
    numero_asesor = _get_numero_asesor_request(request)
    tel = normaliza_tel_mx(
        request.data.get("tel", "")
        or request.data.get("telefono", "")
    )

    motivo = str(
        request.data.get("motivo", "")
        or "Bloqueado manualmente desde CRM"
    ).strip()[:255]

    if not tel:
        return Response(
            {"ok": False, "error": "Falta tel"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    cliente = ClienteComercial.objects.filter(telefono=tel).first()
    expediente = (
        ExpedienteDigital.objects.filter(cliente=cliente).first()
        if cliente
        else None
    )

    _validar_acceso_expediente(
        request=request,
        expediente=expediente,
        numero_asesor=numero_asesor,
    )

    try:
        meta_res = bloquear_usuario_whatsapp(
            to=tel,
            numero_asesor=numero_asesor,
        )
    except MetaAPIError as e:
        return _response_meta_error(
            e,
            numero_asesor=numero_asesor,
            extra={
                "tipo": "block_user",
                "tel": tel,
            },
        )
    except Exception as e:
        logger.exception(
            "ERROR BLOQUEANDO CONTACTO WHATSAPP | tel=%s numero_asesor=%s error=%s",
            tel,
            numero_asesor,
            str(e),
        )

        return Response(
            {
                "ok": False,
                "error": str(e),
                "numero_asesor": numero_asesor,
                "tel": tel,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    agregados = _meta_block_added(meta_res)
    fallidos = _meta_block_failed(meta_res)

    if not agregados:
        return Response(
            {
                "ok": False,
                "error": (
                    "Meta no confirmó el bloqueo. "
                    "Recuerda que solo se puede bloquear si el cliente escribió en las últimas 24 horas."
                ),
                "numero_asesor": numero_asesor,
                "tel": tel,
                "meta": meta_res,
                "fallidos": fallidos,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    usuario = _usuario_nombre_para_auditoria(request)

    if expediente:
        expediente.whatsapp_bloqueado = True
        expediente.whatsapp_bloqueado_at = timezone.now()
        expediente.whatsapp_bloqueado_por = usuario
        expediente.whatsapp_bloqueado_motivo = motivo
        expediente.whatsapp_bloqueado_respuesta_meta = meta_res

        expediente.ia_pausada = True
        expediente.ia_pausada_motivo = "cliente_bloqueado"
        expediente.ia_pausada_at = timezone.now()

        expediente.estado = "Descalificado"

        expediente.save(update_fields=[
            "whatsapp_bloqueado",
            "whatsapp_bloqueado_at",
            "whatsapp_bloqueado_por",
            "whatsapp_bloqueado_motivo",
            "whatsapp_bloqueado_respuesta_meta",
            "ia_pausada",
            "ia_pausada_motivo",
            "ia_pausada_at",
            "estado",
            "actualizado",
        ])

    registrar_evento_operativo(
        expediente=expediente,
        numero_asesor=numero_asesor,
        tipo="bloqueo",
        accion="Bloqueó al cliente en WhatsApp",
        detalle=motivo,
        request=request,
        metadata={"respuesta_meta": meta_res},
    )

    return Response(
        {
            "ok": True,
            "bloqueado": True,
            "tel": tel,
            "numero_asesor": numero_asesor,
            "meta": meta_res,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def desbloquear_contacto_whatsapp_view(request):
    numero_asesor = _get_numero_asesor_request(request)
    tel = normaliza_tel_mx(
        request.data.get("tel", "")
        or request.data.get("telefono", "")
    )

    if not tel:
        return Response(
            {"ok": False, "error": "Falta tel"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    cliente = ClienteComercial.objects.filter(telefono=tel).first()
    expediente = (
        ExpedienteDigital.objects.filter(cliente=cliente).first()
        if cliente
        else None
    )

    _validar_acceso_expediente(
        request=request,
        expediente=expediente,
        numero_asesor=numero_asesor,
    )

    try:
        meta_res = desbloquear_usuario_whatsapp(
            to=tel,
            numero_asesor=numero_asesor,
        )
    except MetaAPIError as e:
        return _response_meta_error(
            e,
            numero_asesor=numero_asesor,
            extra={
                "tipo": "unblock_user",
                "tel": tel,
            },
        )
    except Exception as e:
        logger.exception(
            "ERROR DESBLOQUEANDO CONTACTO WHATSAPP | tel=%s numero_asesor=%s error=%s",
            tel,
            numero_asesor,
            str(e),
        )

        return Response(
            {
                "ok": False,
                "error": str(e),
                "numero_asesor": numero_asesor,
                "tel": tel,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    removidos = _meta_block_added(meta_res)
    fallidos = _meta_block_failed(meta_res)

    if not removidos:
        return Response(
            {
                "ok": False,
                "error": "Meta no confirmó el desbloqueo.",
                "numero_asesor": numero_asesor,
                "tel": tel,
                "meta": meta_res,
                "fallidos": fallidos,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if expediente:
        expediente.whatsapp_bloqueado = False
        expediente.whatsapp_bloqueado_at = None
        expediente.whatsapp_bloqueado_por = ""
        expediente.whatsapp_bloqueado_motivo = ""
        expediente.whatsapp_bloqueado_respuesta_meta = meta_res

        expediente.save(update_fields=[
            "whatsapp_bloqueado",
            "whatsapp_bloqueado_at",
            "whatsapp_bloqueado_por",
            "whatsapp_bloqueado_motivo",
            "whatsapp_bloqueado_respuesta_meta",
            "actualizado",
        ])

    registrar_evento_operativo(
        expediente=expediente,
        numero_asesor=numero_asesor,
        tipo="bloqueo",
        accion="Desbloqueó al cliente en WhatsApp",
        request=request,
        metadata={"respuesta_meta": meta_res},
    )

    return Response(
        {
            "ok": True,
            "bloqueado": False,
            "tel": tel,
            "numero_asesor": numero_asesor,
            "meta": meta_res,
        },
        status=status.HTTP_200_OK,
    )

def obtener_productos(request):
    datos = [
        {"nombre": "Producto A", "precio": 150.50},
        {"nombre": "Producto B", "precio": 200.00}
    ]
    return JsonResponse(datos, safe=False)