# digitales/views.py
import json
from datetime import timedelta
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Q, OuterRef, Subquery
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status, viewsets

from .models import ClientesDigitales, MensajeWhatsApp, normaliza_tel_mx, CampanaMeta
from .serializers import ClientesDigitalesSerializer, WhatsAppMessageSerializer
from .contacto import (
    obtener_mensaje_whatsapp,
    replace_start,
    enviar_texto_whatsapp,
    enviar_template_whatsapp,
)

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
            for k, v in data.items():
                if k == "telefono":
                    continue
                if v is not None and str(v).strip() != "":
                    setattr(obj, k, v)

            obj.telefono = tel

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

        if getattr(obj, "asesor_digital", "") or getattr(obj, "asesor_ventas", ""):
            obj.responsable = " / ".join([x for x in [obj.asesor_digital, obj.asesor_ventas] if x])
            obj.save(update_fields=["responsable", "actualizado"])

        return Response(self.get_serializer(obj).data, status=status.HTTP_200_OK)

    def partial_update(self, request, *args, **kwargs):
        data = request.data.copy()
        data.pop("creado", None)
        data.pop("primer_contacto_at", None)
        data.pop("ultimo_contacto_at", None)

        if "telefono" in data:
            tel = normaliza_tel_mx(data.get("telefono", ""))
            if not tel:
                return Response({"ok": False, "error": "Teléfono inválido"}, status=status.HTTP_400_BAD_REQUEST)
            data["telefono"] = tel

        instance = self.get_object()
        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()

        if getattr(obj, "asesor_digital", "") or getattr(obj, "asesor_ventas", ""):
            obj.responsable = " / ".join([x for x in [obj.asesor_digital, obj.asesor_ventas] if x])
            obj.save(update_fields=["responsable", "actualizado"])

        return Response(self.get_serializer(obj).data, status=status.HTTP_200_OK)


def bienvenido(request):
    return HttpResponse("Funcionando Digitales WhatsApp R&R, desde Django")


TOKEN = "CBAR&RVOLKS"

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
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponse("ok")

    try:
        entries = body.get("entry") or []
        for entry in entries:
            changes = entry.get("changes") or []
            for ch in changes:
                value = ch.get("value") or {}

                contacts = value.get("contacts") or []
                profile_name = ""
                if contacts:
                    profile_name = (contacts[0].get("profile") or {}).get("name", "") or ""

                # ✅ 1) Mensajes (pueden venir varios)
                messages = value.get("messages") or []
                for msg in messages:
                    wa_from = msg.get("from", "")
                    tel = normaliza_tel_mx(replace_start(wa_from))
                    wa_id = msg.get("id", "") or ""
                    text = obtener_mensaje_whatsapp(msg)

                    if not tel or not wa_id:
                        continue

                    # ✅ idempotencia
                    if MensajeWhatsApp.objects.filter(wa_message_id=wa_id).exists():
                        continue

                    cliente, _ = ClientesDigitales.objects.get_or_create(
                        telefono=tel,
                        defaults={"nombre": profile_name or ""},
                    )

                    if profile_name and not cliente.nombre:
                        cliente.nombre = profile_name
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

                # ✅ 2) Statuses (sent/delivered/read/failed)
                statuses = value.get("statuses") or []
                for s in statuses:
                    wa_id = s.get("id")
                    st = s.get("status")
                    errors = s.get("errors") or []
                    ts = s.get("timestamp")
                    if not (wa_id and st):
                        continue

                    msg = MensajeWhatsApp.objects.filter(wa_message_id=wa_id).first()
                    if not msg:
                        continue

                    new_raw = dict(msg.raw or {})
                    new_raw["status_payload"] = s
                    if errors:
                        new_raw["errors"] = errors
                    if ts:
                        new_raw["status_timestamp"] = ts

                    msg.status = st
                    msg.raw = new_raw
                    msg.save(update_fields=["status", "raw"])
                    #logger.warning("WA STATUS EVENT: %s", json.dumps(s, ensure_ascii=False))
                    print("WA STATUS EVENT:", json.dumps(s, ensure_ascii=False))

        return HttpResponse("ok")

    except Exception:
        # recomendado: logging.exception("webhook error")
        return HttpResponse("ok")


def _unread_count(cliente: ClientesDigitales) -> int:
    qs = MensajeWhatsApp.objects.filter(telefono=cliente.telefono, direction="in")
    if cliente.last_read_at:
        qs = qs.filter(created_at__gt=cliente.last_read_at)
    return qs.count()


@api_view(["GET"])
@permission_classes([AllowAny])
def contacto_updates(request):
    tel = normaliza_tel_mx(request.query_params.get("tel", ""))
    after = request.query_params.get("after", "")

    if not tel:
        return Response({"ok": False, "error": "Falta tel"}, status=400)

    qs = MensajeWhatsApp.objects.filter(telefono=tel).order_by("created_at")

    if after:
        try:
            after_dt = timezone.datetime.fromisoformat(after.replace("Z", "+00:00"))
            if timezone.is_naive(after_dt):
                after_dt = timezone.make_aware(after_dt, timezone=timezone.utc)
            qs = qs.filter(created_at__gt=after_dt)
        except Exception:
            pass

    return Response(
        {
            "ok": True,
            "mensajes": WhatsAppMessageSerializer(qs, many=True).data,
            "server_now": timezone.now().isoformat(),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def chats_list(request):
    # ✅ baja de 300 a 200 (si quieres 300, ok, pero 200 mejora carga)
    limit = 200

    last_msg_qs = (
        MensajeWhatsApp.objects
        .filter(telefono=OuterRef("telefono"))
        .order_by("-created_at")
    )

    clientes = (
        ClientesDigitales.objects
        .all()
        .annotate(
            last_text=Subquery(last_msg_qs.values("body")[:1]),
            last_time=Subquery(last_msg_qs.values("created_at")[:1]),
        )
        .order_by("-ultimo_contacto_at", "-actualizado", "-creado")[:limit]
    )

    # ✅ unread en Python (pero sin last_msg query N+1 ya cae mucho el tiempo)
    data = []
    for c in clientes:
        last_time_str = ""
        if c.last_time:
            last_time_str = timezone.localtime(c.last_time).strftime("%I:%M %p").lower()

        data.append(
            {
                "id": c.id,
                "telefono": c.telefono,
                "nombre": c.nombre or "Prospecto",
                "agencia": c.agencia or "",
                "linea": c.business or "",
                "estado": c.estado or "",
                "unread": _unread_count(c),
                "last_text": c.last_text or "",
                "last_time": last_time_str,
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
            defaults={"primer_contacto_at": None, "ultimo_contacto_at": None},
        )

        wa_res = enviar_texto_whatsapp(to=to, text=text)

        update_fields = []
        if not cliente.primer_contacto_at:
            cliente.primer_contacto_at = now
            update_fields.append("primer_contacto_at")

        cliente.ultimo_contacto_at = now
        update_fields.append("ultimo_contacto_at")

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
            status="accepted",
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
            defaults={"primer_contacto_at": None, "ultimo_contacto_at": None},
        )
        cliente.touch_ultimo_contacto(save_now=True)

        wa_res = enviar_template_whatsapp(
            to=to,
            template_name=template_name,
            params=[str(x) for x in params],
            idioma="es",
        )

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
            status="accepted",
            raw=wa_res,
        )

        return Response({"ok": True, "data": wa_res}, status=status.HTTP_200_OK)

    except Exception as e:
        MensajeWhatsApp.objects.create(
        telefono=to,
        cliente=cliente,
        direction="out",
        body=f"[TEMPLATE:{template_name}] " + " | ".join([str(x) for x in params]),
        wa_message_id="",
        status="failed",
        raw={"error": str(e)},
        )
        return Response({"ok": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([AllowAny])
def campanas_meta_recientes(request):
    try:
        days = int(request.query_params.get("days", "30"))
    except ValueError:
        days = 30

    cutoff = timezone.localdate() - timedelta(days=days)
    qs = CampanaMeta.objects.filter(Q(inicio_campana__gte=cutoff) | Q(fin_campana__gte=cutoff)).order_by("-inicio_campana", "-fin_campana")

    seen = set()
    out = []
    for c in qs[:500]:
        label = f"{(c.sucursal or '').strip()} - {(c.nombre_campana or '').strip()}".strip(" -")
        if not label or label in seen:
            continue
        seen.add(label)
        out.append({"value": label, "label": label})

    return Response({"ok": True, "items": out}, status=status.HTTP_200_OK)
