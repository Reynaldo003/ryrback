# digitales/views.py
import json
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status, viewsets
from .models import ClientesDigitales, MensajeWhatsApp, normaliza_tel_mx,CampanaMeta
from .serializers import ClientesDigitalesSerializer, WhatsAppMessageSerializer
from .contacto import (
    obtener_mensaje_whatsapp,
    replace_start,
    enviar_texto_whatsapp,
    enviar_template_whatsapp,
)
from datetime import timedelta

class ProspectosViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    queryset = ClientesDigitales.objects.all().order_by("-ultimo_contacto_at", "-actualizado", "-creado")
    serializer_class = ClientesDigitalesSerializer

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        tel = normaliza_tel_mx(data.get("telefono", ""))

        nombre = (data.get("nombre") or "").strip()
        if not nombre:
            return Response({"ok": False, "error": "El nombre es obligatorio"}, status=status.HTTP_400_BAD_REQUEST)

        if not tel:
            return Response({"ok": False, "error": "El teléfono es obligatorio"}, status=status.HTTP_400_BAD_REQUEST)

        obj = ClientesDigitales.objects.filter(telefono=tel).first()
        if obj:
            # update parcial tipo upsert
            for k, v in data.items():
                if k == "telefono":
                    continue
                if v is not None and str(v).strip() != "":
                    setattr(obj, k, v)
            obj.telefono = tel

            # opcional: mantener "responsable" consistente
            if getattr(obj, "asesor_digital", "") or getattr(obj, "asesor_ventas", ""):
                obj.responsable = " / ".join([x for x in [obj.asesor_digital, obj.asesor_ventas] if x])

            obj.save()
            return Response(self.get_serializer(obj).data, status=status.HTTP_200_OK)

        data["telefono"] = tel
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        data = request.data.copy()
        data.pop("creado", None)
        data.pop("primer_contacto_at", None)
        data.pop("ultimo_contacto_at", None)

        # valida obligatorios también en update
        nombre = (data.get("nombre") or "").strip()
        tel = normaliza_tel_mx(data.get("telefono", ""))
        if not nombre:
            return Response({"ok": False, "error": "El nombre es obligatorio"}, status=status.HTTP_400_BAD_REQUEST)
        if not tel:
            return Response({"ok": False, "error": "El teléfono es obligatorio"}, status=status.HTTP_400_BAD_REQUEST)
        data["telefono"] = tel

        instance = self.get_object()
        serializer = self.get_serializer(instance, data=data, partial=False)
        serializer.is_valid(raise_exception=True)

        obj = serializer.save()

        # opcional: mantener "responsable" consistente
        if getattr(obj, "asesor_digital", "") or getattr(obj, "asesor_ventas", ""):
            obj.responsable = " / ".join([x for x in [obj.asesor_digital, obj.asesor_ventas] if x])
            obj.save(update_fields=["responsable", "actualizado"])

            return Response(self.get_serializer(obj).data, status=status.HTTP_200_OK)
    def partial_update(self, request, *args, **kwargs):
            data = request.data.copy()
            data.pop("creado", None)
            data.pop("primer_contacto_at", None)
            data.pop("ultimo_contacto_at", None)

            # Normaliza teléfono SOLO si viene en payload
            if "telefono" in data:
                tel = normaliza_tel_mx(data.get("telefono", ""))
                if not tel:
                    return Response({"ok": False, "error": "Teléfono inválido"}, status=status.HTTP_400_BAD_REQUEST)
                data["telefono"] = tel

            instance = self.get_object()
            serializer = self.get_serializer(instance, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            obj = serializer.save()

            # mantener "responsable" consistente
            if getattr(obj, "asesor_digital", "") or getattr(obj, "asesor_ventas", ""):
                obj.responsable = " / ".join([x for x in [obj.asesor_digital, obj.asesor_ventas] if x])
                obj.save(update_fields=["responsable", "actualizado"])

            return Response(self.get_serializer(obj).data, status=status.HTTP_200_OK)

def bienvenido(request):
    return HttpResponse("Funcionando Digitales WhatsApp R&R, desde Django")

TOKEN = 'CBAR&RVOLKS'
@csrf_exempt
def webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode", "")
        token = request.GET.get("hub.verify_token", "")
        challenge = request.GET.get("hub.challenge", "")

        if mode == "subscribe" and token == TOKEN and challenge:
            return HttpResponse(challenge, content_type="text/plain")

        return HttpResponse("token incorrecto", status=403)

    if request.method != "POST":
        return HttpResponse("method not allowed", status=405)

    try:
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return HttpResponse("ok")

        entry0 = (body.get("entry") or [{}])[0]
        changes0 = (entry0.get("changes") or [{}])[0]
        value = changes0.get("value") or {}

        messages = value.get("messages") or []
        statuses = value.get("statuses") or []

        if messages:
            msg = messages[0]

            wa_from = msg.get("from", "")
            tel = normaliza_tel_mx(replace_start(wa_from))

            text = obtener_mensaje_whatsapp(msg)
            wa_id = msg.get("id", "") or ""

            name = ""
            contacts = value.get("contacts") or []
            if contacts:
                name = (contacts[0].get("profile") or {}).get("name", "") or ""

            if tel:
                cliente, _created = ClientesDigitales.objects.get_or_create(
                    telefono=tel,
                    defaults={"nombre": name or ""},
                )

                if name and not cliente.nombre:
                    cliente.nombre = name
                    cliente.save(update_fields=["nombre", "actualizado"])

                cliente.touch_ultimo_contacto(save_now=True)

                MensajeWhatsApp.objects.create(
                    telefono=tel,
                    cliente=cliente,
                    direction="in",
                    body=text,
                    wa_message_id=wa_id,
                    status="received",
                    raw=body,
                )

            return HttpResponse("ok")

        # Si no los manejas, no pasa nada: responde ok.
        if statuses:
            # Si quieres, aquí podrías mapear status por wa_message_id:
            for s in statuses:
                wa_id = s.get("id")
                st = s.get("status")  # sent, delivered, read, failed...
                MensajeWhatsApp.objects.filter(wa_message_id=wa_id).update(status=st)
            return HttpResponse("ok")
        return HttpResponse("ok")

    except Exception as e:
        return HttpResponse("ok")


def _unread_count(cliente: ClientesDigitales) -> int:
    """
    Cuenta mensajes entrantes no leídos basados en last_read_at.
    """
    qs = MensajeWhatsApp.objects.filter(telefono=cliente.telefono, direction="in")
    if cliente.last_read_at:
        qs = qs.filter(created_at__gt=cliente.last_read_at)
    return qs.count()


@api_view(["GET"])
@permission_classes([AllowAny])
def chats_list(request):
    clientes = ClientesDigitales.objects.all().order_by("-ultimo_contacto_at", "-actualizado", "-creado")

    data = []
    for c in clientes[:300]:
        last_msg = (
            MensajeWhatsApp.objects.filter(telefono=c.telefono)
            .order_by("-created_at")
            .first()
        )

        data.append(
            {
                "id": c.id,
                "telefono": c.telefono,
                "nombre": c.nombre or "Prospecto",
                "agencia": c.agencia or "",
                "linea": c.business or "",
                "estado": c.estado or "",
                "unread": _unread_count(c),
                "last_text": (last_msg.body if last_msg else ""),
                "last_time": (timezone.localtime(last_msg.created_at).strftime("%I:%M %p").lower() if last_msg else ""),
            }
        )

    return Response(data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def contacto_por_telefono(request):
    tel = normaliza_tel_mx(request.query_params.get("tel", ""))

    if not tel:
        return Response({"ok": False, "error": "Falta tel"}, status=status.HTTP_400_BAD_REQUEST)

    prospecto = ClientesDigitales.objects.filter(telefono=tel).first()
    mensajes = MensajeWhatsApp.objects.filter(telefono=tel).order_by("created_at")

    # ✅ al abrir chat -> marcar como leído
    if prospecto:
        prospecto.mark_read()

    return Response(
        {
            "ok": True,
            "prospecto": ClientesDigitalesSerializer(prospecto).data if prospecto else None,
            "mensajes": WhatsAppMessageSerializer(mensajes, many=True).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def mark_read_view(request):
    tel = normaliza_tel_mx(request.data.get("tel", ""))
    if not tel:
        return Response({"ok": False, "error": "Falta tel"}, status=status.HTTP_400_BAD_REQUEST)

    prospecto = ClientesDigitales.objects.filter(telefono=tel).first()
    if prospecto:
        prospecto.mark_read()
        return Response({"ok": True}, status=status.HTTP_200_OK)

    return Response({"ok": False, "error": "No existe prospecto"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
@permission_classes([AllowAny])
def enviar_mensaje_view(request):
    to = normaliza_tel_mx(request.data.get("to", ""))
    text = (request.data.get("text") or "").strip()

    if not to or not text:
        return Response({"ok": False, "error": "Falta to o text"}, status=status.HTTP_400_BAD_REQUEST)
    now = timezone.now()

    try:
        cliente, _ = ClientesDigitales.objects.get_or_create(
            telefono=to,
            defaults={
                "primer_contacto_at": None,
                "ultimo_contacto_at": None,
            },
        )

        wa_res = enviar_texto_whatsapp(to=to, text=text)
        # Si es el primer mensaje que tú envías, setea primer_contacto_at
        update_fields = []
        if not cliente.primer_contacto_at:
            cliente.primer_contacto_at = now
            update_fields.append("primer_contacto_at")

        # Siempre que envías, actualiza ultimo_contacto_at
        cliente.ultimo_contacto_at = now
        update_fields.append("ultimo_contacto_at")

        # Guarda solo si hubo cambios
        if update_fields:
            update_fields.append("actualizado")
            cliente.save(update_fields=update_fields)

        wa_message_id = ""
        try:
            wa_message_id = (wa_res.get("messages") or [{}])[0].get("id", "") or ""
        except Exception:
            wa_message_id = ""

        MensajeWhatsApp.objects.create(
            telefono=to,
            cliente=cliente,
            direction="out",
            body=text,
            wa_message_id=wa_message_id,
            status="entregado",
            raw=wa_res,
        )

        return Response({"ok": True, "data": wa_res}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"ok": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def enviar_plantilla_view(request):
    to = normaliza_tel_mx(request.data.get("to", ""))
    template_name = (request.data.get("template_name") or "").strip()
    params = request.data.get("params") or []

    if not to:
        return Response({"ok": False, "error": "Falta to"}, status=status.HTTP_400_BAD_REQUEST)
    if not template_name:
        return Response({"ok": False, "error": "Falta template_name"}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(params, list):
        return Response({"ok": False, "error": "params debe ser lista"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        cliente, _ = ClientesDigitales.objects.get_or_create(
            telefono=to,
            defaults={
                "primer_contacto_at": None,
                "ultimo_contacto_at": None,
            },
        )
        cliente.touch_ultimo_contacto(save_now=True)

        wa_res = enviar_template_whatsapp(to=to, template_name=template_name, params=[str(x) for x in params])

        wa_message_id = ""
        try:
            wa_message_id = (wa_res.get("messages") or [{}])[0].get("id", "") or ""
        except Exception:
            wa_message_id = ""

        MensajeWhatsApp.objects.create(
            telefono=to,
            cliente=cliente,
            direction="out",
            body=f"[TEMPLATE:{template_name}] " + " | ".join([str(x) for x in params]),
            wa_message_id=wa_message_id,
            status="entregado",
            raw=wa_res,
        )

        return Response({"ok": True, "data": wa_res}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"ok": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(["GET"])
@permission_classes([AllowAny])
def campanas_meta_recientes(request):
    """
    Devuelve campañas recientes (últimos N días).
    Retorna items: { value: "Sucursal - Campaña", label: "Sucursal - Campaña" }
    """
    try:
        days = int(request.query_params.get("days", "30"))
    except ValueError:
        days = 30

    cutoff = timezone.localdate() - timedelta(days=days)

    # Campañas donde inicio o fin caen dentro de los últimos N días.
    # (si inicio_campana es null, fin_campana puede servir; por eso OR)
    qs = CampanaMeta.objects.filter(
        Q(inicio_campana__gte=cutoff) | Q(fin_campana__gte=cutoff)
    ).order_by("-inicio_campana", "-fin_campana")

    # DISTINCT por "Sucursal - Nombre" (evitar duplicados)
    seen = set()
    out = []
    for c in qs[:500]:
        label = f"{(c.sucursal or '').strip()} - {(c.nombre_campana or '').strip()}".strip(" -")
        if not label:
            continue
        if label in seen:
            continue
        seen.add(label)
        out.append({"value": label, "label": label})

    return Response({"ok": True, "items": out}, status=status.HTTP_200_OK)
