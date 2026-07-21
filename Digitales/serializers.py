#volkswagen
# Digitales/serializers.py
from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers

from citas.models import ClienteComercial, normaliza_tel_mx
from .models import ExpedienteDigital, MensajeWhatsApp, EvidenciaProspectoDigital

EDIT_WINDOW_MINUTES = 15

def absolute_backend_url(url_o_path: str) -> str:
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

def tel_normalizado_valido(tel: str) -> bool:
    tel = "".join(c for c in str(tel or "") if c.isdigit())
    return len(tel) == 12 and tel.startswith("52")


def diff_minutes_safe(start_value, end_value):
    if not start_value or not end_value:
        return None

    try:
        start = start_value
        end = end_value

        if isinstance(start, str):
            start = timezone.datetime.fromisoformat(start.replace("Z", "+00:00"))

        if isinstance(end, str):
            end = timezone.datetime.fromisoformat(end.replace("Z", "+00:00"))

        diff = round((end - start).total_seconds() / 60)

        if diff < 0:
            return None

        return diff
    except Exception:
        return None


def format_duration_minutes(minutes):
    if minutes is None:
        return "—"

    try:
        total = int(minutes)
    except (TypeError, ValueError):
        return "—"

    if total < 0:
        return "—"

    if total < 60:
        return f"{total} min"

    horas = total // 60
    mins = total % 60

    if horas < 24:
        return f"{horas}h {mins}m" if mins else f"{horas}h"

    dias = horas // 24
    horas_restantes = horas % 24

    return f"{dias}d {horas_restantes}h" if horas_restantes else f"{dias}d"


class WhatsAppMessageSerializer(serializers.ModelSerializer):
    mine = serializers.SerializerMethodField()
    text = serializers.CharField(source="body", read_only=True)
    time = serializers.SerializerMethodField()

    editable = serializers.SerializerMethodField()
    edit_expires_at = serializers.SerializerMethodField()
    is_template = serializers.SerializerMethodField()
    is_media = serializers.SerializerMethodField()
    is_ai = serializers.SerializerMethodField()
    reply_to_message_id = serializers.SerializerMethodField()

    attachments = serializers.SerializerMethodField()
    origin_preview = serializers.SerializerMethodField()

    class Meta:
        model = MensajeWhatsApp
        fields = [
            "id",
            "telefono",
            "direction",
            "mine",
            "text",
            "body",
            "wa_message_id",
            "reply_to_message_id",
            "status",
            "raw",
            "created_at",
            "time",
            "editable",
            "edit_expires_at",
            "is_template",
            "is_media",
            "is_ai",
            "attachments",
            "origin_preview",
        ]

    def get_mine(self, obj):
        return obj.direction == "out"

    def get_time(self, obj):
        if not obj.created_at:
            return ""

        dt = obj.created_at

        if settings.USE_TZ and timezone.is_aware(dt):
            dt = timezone.localtime(dt)

        return dt.strftime("%I:%M %p").lower()

    def get_is_template(self, obj):
        body = (obj.body or "").strip()
        return body.startswith("[TEMPLATE:")

    def get_is_media(self, obj):
        raw = obj.raw or {}

        if raw.get("meta_type") in ("image", "video", "audio", "document", "sticker"):
            return True

        body = (obj.body or "").strip()
        return body.startswith("[FILE:") or "\n[FILE:" in body

    def get_is_ai(self, obj):
        raw = obj.raw or {}

        return bool(
            raw.get("ia_provider")
            or raw.get("ia_model")
            or raw.get("openai_model")
            or raw.get("gemini_model")
        )

    def get_reply_to_message_id(self, obj):
        raw = obj.raw or {}

        if not isinstance(raw, dict):
            return ""

        return str(raw.get("reply_to") or "").strip()

    def get_edit_expires_at(self, obj):
        if not obj.created_at:
            return None

        return (obj.created_at + timedelta(minutes=EDIT_WINDOW_MINUTES)).isoformat()

    def get_editable(self, obj):
        if obj.direction != "out":
            return False

        if not obj.created_at:
            return False

        if self.get_is_template(obj):
            return False

        if self.get_is_media(obj):
            return False

        return timezone.now() <= (obj.created_at + timedelta(minutes=EDIT_WINDOW_MINUTES))

    def _media_proxy_url(self, media_id: str, obj):
        path = reverse("digitales-media-proxy", args=[media_id])

        numero_asesor = str(getattr(obj, "numero_asesor", "") or "").strip()

        if numero_asesor:
            path = f"{path}?numero_asesor={numero_asesor}"

        return absolute_backend_url(path)

    @staticmethod
    def _safe_dict(value):
        return value if isinstance(value, dict) else {}

    def get_origin_preview(self, obj):
        """
        Normaliza la referencia Click-to-WhatsApp guardada en raw para que
        el frontend pueda dibujar la tarjeta del anuncio dentro de la primera
        burbuja entrante.

        Meta puede mandar referral directamente en message.referral o dentro
        de message.context.referral. Los registros duplicados pueden conservar
        el último payload en raw["ultimo_webhook_payload"].
        """
        if obj.direction != MensajeWhatsApp.Direccion.IN:
            return None

        raw = self._safe_dict(obj.raw)
        ultimo_webhook = self._safe_dict(raw.get("ultimo_webhook_payload"))

        referral_candidates = [
            self._safe_dict(raw.get("referral")),
            self._safe_dict(self._safe_dict(raw.get("context")).get("referral")),
            self._safe_dict(ultimo_webhook.get("referral")),
            self._safe_dict(self._safe_dict(ultimo_webhook.get("context")).get("referral")),
        ]
        referral = next((item for item in referral_candidates if item), {})

        attribution_candidates = [
            self._safe_dict(raw.get("atribucion_meta")),
            self._safe_dict(ultimo_webhook.get("atribucion_meta")),
        ]
        atribucion = next((item for item in attribution_candidates if item), {})

        nombre_campana = str(
            atribucion.get("nombre_campana")
            or atribucion.get("campaign_name")
            or ""
        ).strip()
        nombre_anuncio = str(
            atribucion.get("nombre_anuncio")
            or referral.get("headline")
            or ""
        ).strip()
        sucursal = str(atribucion.get("sucursal") or "").strip()
        pauta = str(
            atribucion.get("pauta")
            or (f"{sucursal} - {nombre_campana}" if sucursal and nombre_campana else "")
            or nombre_campana
            or nombre_anuncio
            or ""
        ).strip()

        headline = str(
            referral.get("headline")
            or nombre_anuncio
            or nombre_campana
            or pauta
            or ""
        ).strip()
        body = str(
            referral.get("body")
            or atribucion.get("nombre_conjunto")
            or ""
        ).strip()
        source_url = str(referral.get("source_url") or "").strip()
        image_url = str(
            referral.get("image_url")
            or referral.get("thumbnail_url")
            or referral.get("video_thumbnail_url")
            or ""
        ).strip()

        if not any((pauta, headline, source_url, image_url)):
            return None

        return {
            "pauta": pauta or headline,
            "nombre_campana": nombre_campana,
            "nombre_anuncio": nombre_anuncio,
            "sucursal": sucursal,
            "headline": headline or pauta,
            "body": body,
            "source_url": source_url,
            "image_url": image_url,
            "media_type": str(referral.get("media_type") or "").strip(),
            "source_type": str(referral.get("source_type") or "").strip(),
            "source_id": str(referral.get("source_id") or "").strip(),
            "origen": str(atribucion.get("motivo") or "meta_ads").strip(),
            "referral": referral,
            "atribucion": atribucion,
        }

    def get_attachments(self, obj):
        raw = obj.raw or {}

        if not isinstance(raw, dict):
            return []

        # Archivos enviados desde el CRM: subir_media_whatsapp()
        # En views.py se guarda como "meta_upload".
        upload = raw.get("meta_upload") or raw.get("upload") or {}

        if upload and raw.get("meta_type"):
            media_id = upload.get("id") or raw.get("media_id") or ""
            kind = raw.get("meta_type")

            local_url = (
                raw.get("media_link")
                or raw.get("document_link")
                or raw.get("local_media_url")
                or ""
            )

            if local_url:
                return [
                    {
                        "id": media_id or local_url,
                        "kind": "file" if kind == "document" else kind,
                        "url": absolute_backend_url(local_url),
                        "mime": raw.get("content_type") or "",
                        "name": raw.get("filename") or "",
                        "size": 0,
                    }
                ]

            if media_id:
                url = self._media_proxy_url(media_id, obj)

                return [
                    {
                        "id": media_id,
                        "kind": "file" if kind == "document" else kind,
                        "url": url,
                        "mime": raw.get("content_type") or "",
                        "name": raw.get("filename") or "",
                        "size": 0,
                    }
                ]

        # Archivos enviados por link desde catálogo/IA.
        if raw.get("meta_type") in ("image", "video", "audio", "document", "sticker"):
            kind = raw.get("meta_type")
            media_url = (
                raw.get("media_link")
                or raw.get("document_link")
                or raw.get("local_media_url")
                or ""
            )

            if media_url:
                default_mime = {
                    "image": "image/jpeg",
                    "video": "video/mp4",
                    "audio": "audio/mpeg",
                    "document": "application/pdf",
                    "sticker": "image/webp",
                }.get(kind, "")

                return [
                    {
                        "id": raw.get("wa_message_id") or raw.get("filename") or media_url,
                        "kind": "file" if kind == "document" else kind,
                        "url": absolute_backend_url(media_url),
                        "mime": raw.get("content_type") or default_mime,
                        "name": raw.get("filename") or "",
                        "size": 0,
                    }
                ]

        # Archivos entrantes desde webhook Meta.
        message_type = (raw.get("type") or "").lower()

        if message_type in ("image", "video", "audio", "document", "sticker"):
            payload = raw.get(message_type) or {}
            media_id = payload.get("id") or ""

            if media_id:
                url = self._media_proxy_url(media_id, obj)
                name = payload.get("filename") or ""
                mime = payload.get("mime_type") or ""

                return [
                    {
                        "id": media_id,
                        "kind": "sticker" if message_type == "sticker" else ("file" if message_type == "document" else message_type),
                        "url": url,
                        "mime": mime,
                        "name": name,
                        "size": 0,
                    }
                ]

        return []

class EvidenciaProspectoDigitalSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = EvidenciaProspectoDigital
        fields = [
            "id",
            "nombre_original",
            "mime_type",
            "size_bytes",
            "url",
            "creado",
        ]

    def get_url(self, obj):
        if not obj.archivo:
            return ""

        request = self.context.get("request")
        url = obj.archivo.url

        return request.build_absolute_uri(url) if request else url

class ProspectoSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(write_only=True, required=False, allow_blank=True)
    telefono = serializers.CharField(write_only=True, required=True)
    correo = serializers.EmailField(write_only=True, required=False, allow_blank=True)

    nombre_out = serializers.CharField(source="cliente.nombre", read_only=True)
    telefono_out = serializers.CharField(source="cliente.telefono", read_only=True)
    correo_out = serializers.EmailField(source="cliente.correo", read_only=True)

    cliente_id = serializers.IntegerField(read_only=True)

    tiempo_respuesta_asesor_min = serializers.SerializerMethodField()
    tiempo_respuesta_asesor_label = serializers.SerializerMethodField()

    evidencias = EvidenciaProspectoDigitalSerializer(many=True, read_only=True)

    evidencias_nuevas = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False,
    )

    delete_evidencia_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
    )

    # Compatibilidad temporal con frontend viejo.
    # Recomendado: en React usa los nombres nuevos.
    primer_contacto_at = serializers.DateTimeField(source="primer_mensaje_cliente", read_only=True)
    ultimo_contacto_at = serializers.DateTimeField(source="ultimo_contacto_asesor", read_only=True)

    class Meta:
        model = ExpedienteDigital
        fields = [
            "id",
            "cliente_id",

            "nombre",
            "telefono",
            "correo",

            "nombre_out",
            "telefono_out",
            "correo_out",

            "agencia",
            "business",
            "canal_contacto",
            "pauta",
            "estado",
            "motivo_descalificacion",
            "asesor_digital",
            "asesor_ventas",
            "auto_interes",
            "anio_auto",
            "comentarios",

            "enganche_monto",
            "presupuesto_mensual",
            "buro_estado",
            "forma_pago",
            "tipo_cliente",
            "uso_vehiculo",
            "plazo_compra",
            "comprobacion_ingresos",
            
            "id_cotizacion",
            "folio_solicitud_credito",
            "solicitud_credito_estado",
            "vin_facturado",
            "vin_estatus_entrega",

            "evidencias",
            "evidencias_nuevas",
            "delete_evidencia_ids",

            "ia_pausada",
            "ia_pausada_motivo",
            "ia_pausada_at",

            "whatsapp_bloqueado",
            "whatsapp_bloqueado_at",
            "whatsapp_bloqueado_por",
            "whatsapp_bloqueado_motivo",
            "whatsapp_bloqueado_respuesta_meta",

            "requiere_asesor",
            "motivo_requiere_asesor",

            "cotizacion_pendiente",
            "cotizacion_solicitada_at",

            "resumen",
            "resumen_actualizado_at",
            "resumen_fuente",

            # Campos nuevos correctos.
            "primer_mensaje_cliente",
            "primer_contacto_asesor",
            "ultimo_contacto_asesor",

            # Campo de lectura legacy / operativo.
            "last_read_at",

            # Calculados para frontend.
            "tiempo_respuesta_asesor_min",
            "tiempo_respuesta_asesor_label",

            # Alias temporales para no romper pantallas viejas.
            "primer_contacto_at",
            "ultimo_contacto_at",

            "creado",
            "actualizado",

            "ultima_cita_agendada",
            "asistencia",
            "ultima_cita",
        ]

        read_only_fields = [
            "id",
            "cliente_id",
            "nombre_out",
            "telefono_out",
            "correo_out",
            "tiempo_respuesta_asesor_min",
            "tiempo_respuesta_asesor_label",
            "primer_contacto_at",
            "ultimo_contacto_at",
            "creado",
            "actualizado",
        ]
    
    def validate(self, attrs):
        estado_actual = (
            getattr(self.instance, "estado", "")
            if self.instance
            else ""
        )

        motivo_actual = (
            getattr(self.instance, "motivo_descalificacion", "")
            if self.instance
            else ""
        )

        estado = str(
            attrs.get("estado", estado_actual) or ""
        ).strip()

        motivo = str(
            attrs.get(
                "motivo_descalificacion",
                motivo_actual,
            ) or ""
        ).strip()

        if estado.lower() == "descalificado":
            if not motivo:
                raise serializers.ValidationError({
                    "motivo_descalificacion":
                        "Selecciona el motivo de descalificación."
                })

            attrs["motivo_descalificacion"] = motivo

        elif "estado" in attrs:
            attrs["motivo_descalificacion"] = ""

        return attrs

    def get_tiempo_respuesta_asesor_min(self, obj):
        return diff_minutes_safe(
            obj.primer_mensaje_cliente,
            obj.primer_contacto_asesor,
        )

    def _get_username_request(self):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if user and getattr(user, "is_authenticated", False):
            return (
                getattr(user, "usuario", "")
                or getattr(user, "username", "")
                or str(user)
            ).strip()

        return ""

    def _guardar_evidencias(self, expediente, archivos):
        if not archivos:
            return

        subido_por = self._get_username_request()

        for archivo in archivos:
            EvidenciaProspectoDigital.objects.create(
                expediente=expediente,
                archivo=archivo,
                nombre_original=getattr(archivo, "name", "") or "",
                mime_type=getattr(archivo, "content_type", "") or "",
                size_bytes=getattr(archivo, "size", 0) or 0,
                subido_por=subido_por,
            )

    def _eliminar_evidencias(self, expediente, evidencia_ids):
        if not evidencia_ids:
            return

        qs = expediente.evidencias.filter(id__in=evidencia_ids)

        for evidencia in qs:
            if evidencia.archivo:
                evidencia.archivo.delete(save=False)

            evidencia.delete()

    def get_tiempo_respuesta_asesor_label(self, obj):
        minutes = self.get_tiempo_respuesta_asesor_min(obj)
        return format_duration_minutes(minutes)

    def to_representation(self, instance):
        data = super().to_representation(instance)

        data["nombre"] = data.pop("nombre_out", "") or ""
        data["telefono"] = data.pop("telefono_out", "") or ""
        data["correo"] = data.pop("correo_out", "") or ""

        return data

    def _get_or_create_cliente(self, tel, nombre="", correo=""):
        tel = normaliza_tel_mx(tel)

        if not tel:
            raise serializers.ValidationError(
                {
                    "telefono": "Teléfono inválido. Debe tener 10 dígitos o formato 52XXXXXXXXXX."
                }
            )

        cli, _ = ClienteComercial.objects.get_or_create(
            telefono=tel,
            defaults={
                "nombre": (nombre or "").strip(),
                "correo": (correo or "").strip(),
            },
        )

        changed = False
        update_fields = []

        if nombre and nombre.strip() and (cli.nombre or "").strip() != nombre.strip():
            cli.nombre = nombre.strip()
            changed = True
            update_fields.append("nombre")

        if correo is not None and (cli.correo or "").strip() != (correo or "").strip():
            cli.correo = (correo or "").strip()
            changed = True
            update_fields.append("correo")

        if changed:
            update_fields.append("actualizado_en")
            cli.save(update_fields=list(dict.fromkeys(update_fields)))

        return cli

    def create(self, validated_data):
        evidencias_nuevas = validated_data.pop("evidencias_nuevas", [])
        validated_data.pop("delete_evidencia_ids", [])

        nombre = validated_data.pop("nombre", "")
        telefono = validated_data.pop("telefono", "")
        correo = validated_data.pop("correo", "")

        cli = self._get_or_create_cliente(telefono, nombre, correo)

        exp, created = ExpedienteDigital.objects.get_or_create(
            cliente=cli,
            defaults=validated_data,
        )

        if not created:
            cambios = []

            for campo, valor in validated_data.items():
                if valor is None:
                    continue

                if isinstance(valor, str) and not valor.strip():
                    continue

                if getattr(exp, campo) != valor:
                    setattr(exp, campo, valor)
                    cambios.append(campo)

            if cambios:
                cambios.append("actualizado")
                exp.save(update_fields=list(dict.fromkeys(cambios)))

        self._guardar_evidencias(exp, evidencias_nuevas)

        return exp
    
    def update(self, instance, validated_data):
        evidencias_nuevas = validated_data.pop("evidencias_nuevas", [])
        delete_evidencia_ids = validated_data.pop("delete_evidencia_ids", [])

        nombre = validated_data.pop("nombre", None)
        telefono = validated_data.pop("telefono", None)
        correo = validated_data.pop("correo", None)

        if telefono is not None:
            new_tel = normaliza_tel_mx(telefono)
            old_tel = instance.cliente.telefono

            if not new_tel:
                raise serializers.ValidationError(
                    {
                        "telefono": "Teléfono inválido. Debe ser de 10 dígitos."
                    }
                )

            if new_tel != old_tel:
                if tel_normalizado_valido(old_tel):
                    raise serializers.ValidationError(
                        {
                            "telefono": (
                                "No se permite cambiar un teléfono válido desde aquí. "
                                "Solo corrección de teléfonos inválidos."
                            )
                        }
                    )

                instance.cliente.telefono = new_tel
                instance.cliente.save(update_fields=["telefono", "actualizado_en"])

        if nombre is not None or correo is not None:
            cli = instance.cliente
            changed = False
            update_fields = []

            if nombre is not None and nombre.strip():
                cli.nombre = nombre.strip()
                changed = True
                update_fields.append("nombre")

            if correo is not None:
                cli.correo = (correo or "").strip()
                changed = True
                update_fields.append("correo")

            if changed:
                update_fields.append("actualizado_en")
                cli.save(update_fields=list(dict.fromkeys(update_fields)))

        cambios = []

        for campo, valor in validated_data.items():
            if campo == "vin_facturado" and isinstance(valor, str):
                valor = valor.strip().upper()

            if getattr(instance, campo) != valor:
                setattr(instance, campo, valor)
                cambios.append(campo)

        if cambios:
            cambios.append("actualizado")
            instance.save(update_fields=list(dict.fromkeys(cambios)))
        else:
            instance.save()

        self._eliminar_evidencias(instance, delete_evidencia_ids)
        self._guardar_evidencias(instance, evidencias_nuevas)

        return instance