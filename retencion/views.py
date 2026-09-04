# retencion/views.py
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from django.db.models import Case, IntegerField, Q, Value, When
from django.db.models.functions import ExtractDay, ExtractMonth
from django.db.models import Count, Q, Sum
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import OrdenServicioCompletaVW, OrdenServicioVentaVW, TareaCliente

from .serializers import (
    OrdenServicioCompletaVWSerializer,
    OrdenServicioVentaVWSerializer,
)

DB_ALIAS = "sqlserver_inv"

def es_filtro_vacio(valor):
    return valor in (None, "", "Todos", "Todas", "all", "null", "undefined")


def fecha_iso(valor):
    if not valor:
        return None
    return valor.isoformat()


def decimal_desde_texto(valor):
    if valor in (None, ""):
        return 0
    if isinstance(valor, (int, float, Decimal)):
        return float(valor)
    texto = str(valor).strip()
    if not texto:
        return 0
    texto = texto.replace(",", "")
    texto = re.sub(r"[^0-9.\-]", "", texto)
    if texto in ("", ".", "-", "-."):
        return 0
    try:
        return float(Decimal(texto))
    except (InvalidOperation, ValueError):
        return 0


class OrdenVentaPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000

def normalizar_segmento(valor):
    texto = str(valor or "").strip().upper()

    if not texto:
        return ""

    match = re.search(r"(\d+)", texto)

    if match:
        return f"S{match.group(1)}"

    return texto


def aliases_segmento(valor):
    segmento = normalizar_segmento(valor)

    if not segmento:
        return []

    match = re.fullmatch(r"S(\d+)", segmento)

    if not match:
        return [segmento]

    numero = match.group(1)

    return [
        f"S{numero}",
        f"Segmento {numero}",
        f"SEGMENTO {numero}",
    ]


def separar_valores(valor):
    return [
        item.strip()
        for item in re.split(r"[|,;]+", str(valor or ""))
        if item.strip()
    ]

class OrdenServicioVentaViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrdenServicioVentaVWSerializer
    pagination_class = OrdenVentaPagination
    lookup_field = "vin"
    lookup_value_regex = "[^/]+"

    # Igual que en el resto del CRM: la protección real vive en
    # ProtectedRoute/RequirePermission del front.
    permission_classes = [permissions.AllowAny]

    ordering_permitido = {
        "fecha_ultima_os": "fecha_ultima_os",
        "-fecha_ultima_os": "-fecha_ultima_os",
        "fecha_venta": "fecha_venta",
        "-fecha_venta": "-fecha_venta",
        "estado": "estado_actividad",
        "-estado": "-estado_actividad",
        "segmento": "segmento",
        "-segmento": "-segmento",
        "marca": "marca",
        "-marca": "-marca",
        "modelo": "modelo_nombre",
        "-modelo": "-modelo_nombre",
        "meses": "meses_desde_venta",
        "-meses": "-meses_desde_venta",
    }

    def get_queryset(self):
        qs = OrdenServicioVentaVW.objects.using(DB_ALIAS).all()
        qs = self.aplicar_filtros(qs)
        qs = self.aplicar_ordenamiento(qs)
        return qs

    def aplicar_filtros(self, qs):
        params = self.request.query_params

        anio = params.get("anio")
        mes = params.get("mes")
        semana = params.get("semana")
        estado = params.get("estado")
        segmento = params.get("segmento")
        marca = params.get("marca")
        modelo = params.get("modelo")
        agencia = params.get("agencia")
        agencia_venta = params.get("agencia_venta")
        agencias_venta = params.get("agencias_venta")
        condicion = params.get("condicion")
        search = params.get("search")

        sin_venta = str(params.get("sin_venta", "")).strip().lower()
        es_sin_venta = sin_venta in ("1", "true", "si", "sí", "yes")

        if es_sin_venta:
            qs = qs.filter(fecha_venta__isnull=True, fecha_ultima_os__isnull=False)
        else:
            qs = qs.filter(fecha_venta__isnull=False)

        if not es_filtro_vacio(anio):
            try:
                qs = qs.filter(fecha_ultima_os__year=int(anio))
            except (ValueError, TypeError):
                pass

        if not es_filtro_vacio(mes):
            try:
                qs = qs.filter(fecha_ultima_os__month=int(mes))
            except (ValueError, TypeError):
                pass

        if not es_filtro_vacio(semana):
            try:
                qs = qs.filter(fecha_ultima_os__week=int(semana))
            except (ValueError, TypeError):
                pass

        if not es_filtro_vacio(estado):
            qs = qs.filter(estado_actividad__iexact=estado)

        if not es_filtro_vacio(segmento):
            aliases = aliases_segmento(segmento)
            filtro_segmento = Q()

            for alias in aliases:
                filtro_segmento |= Q(segmento__iexact=alias)

            qs = qs.filter(filtro_segmento)

        if not es_filtro_vacio(marca):
            qs = qs.filter(marca__iexact=marca)

        if not es_filtro_vacio(modelo):
            qs = qs.filter(modelo_nombre__iexact=modelo)

        if es_sin_venta:
            if not es_filtro_vacio(agencia):
                qs = qs.filter(agencia_servicio__iexact=agencia)
        else:
            if not es_filtro_vacio(agencias_venta):
                dealers = separar_valores(agencias_venta)

                if dealers:
                    filtro_dealers = Q()

                    for dealer in dealers:
                        filtro_dealers |= Q(agencia_venta__iexact=dealer)

                    qs = qs.filter(filtro_dealers)

            elif not es_filtro_vacio(agencia_venta):
                qs = qs.filter(agencia_venta__iexact=agencia_venta)

            elif not es_filtro_vacio(agencia):
                qs = qs.filter(agencia_venta__iexact=agencia)

        if not es_filtro_vacio(condicion):
            qs = qs.filter(condicion_vehiculo__iexact=condicion)

        if not es_filtro_vacio(search):
            texto = search.strip()

            qs = qs.filter(
                Q(vin__icontains=texto) |
                Q(nombre_cliente__icontains=texto) |
                Q(telefono_cliente__icontains=texto) |
                Q(correo_cliente__icontains=texto) |
                Q(placa_vehiculo__icontains=texto) |
                Q(numero_nota__icontains=texto) |
                Q(ultima_orden_servicio__icontains=texto) |
                Q(agencia_venta__icontains=texto) |
                Q(agencia_servicio__icontains=texto) |
                Q(modelo_nombre__icontains=texto)
            )

        return qs

    def aplicar_ordenamiento(self, qs):
        ordering = self.request.query_params.get("ordering", "-fecha_ultima_os")
        campo = self.ordering_permitido.get(ordering, "-fecha_ultima_os")

        # Próximos cumpleaños primero (0 a 5 días) para que los iconos del
        # pastelito vuelvan a verse en la primera página de Retención.
        hoy = datetime.now().date()
        proximos_cumple = [
            (hoy + timedelta(days=n)).month * 100 + (hoy + timedelta(days=n)).day
            for n in range(0, 6)
        ]

        return (
            qs.annotate(
                _md_cumple=(
                    ExtractMonth("cumpleaños") * Value(100)
                ) + ExtractDay("cumpleaños")
            ).annotate(
                _proximo_cumple=Case(
                    When(_md_cumple__in=proximos_cumple, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("_proximo_cumple", campo)
        )

    @action(detail=False, methods=["get"], url_path="ligero")
    def ligero(self, request):
        limite = request.query_params.get("limit", "10000")

        try:
            limite = int(limite)
        except ValueError:
            limite = 10000

        limite = max(100, min(limite, 100000))

        sin_venta = str(request.query_params.get("sin_venta", "")).strip().lower()
        es_sin_venta = sin_venta in ("1", "true", "si", "sí", "yes")

        campos = (
            "vin",
            "agencia_venta",
            "agencia_servicio",
            "fecha_venta",
            "fecha_salida",
            "numero_nota",
            "total_nota",
            "marca",
            "modelo_codigo",
            "modelo_nombre",
            "condicion_vehiculo",
            "nombre_cliente",
            "telefono_cliente",
            "correo_cliente",
            "cumpleaños",
            "rfc",
            "ultima_orden_servicio",
            "tipo_orden",
            "subtipo_orden",
            "fecha_ultima_os",
            "situacion_os",
            "cliente_vehiculo",
            "placa_vehiculo",
            "kilometraje",
            "medio_contacto",
            "total_ultimo_servicio",
            "estado_actividad",
            "meses_desde_venta",
            "segmento",
        )

        qs = self.get_queryset().values(*campos)[:limite]

        data = []

        for item in qs:
            agencia_actual = item.get("agencia_servicio") if es_sin_venta else item.get("agencia_venta")

            data.append({
                **{
                    k: (item.get(k) or "")
                    for k in campos
                    if k not in (
                        "fecha_venta",
                        "fecha_salida",
                        "fecha_ultima_os",
                        "cumpleaños",
                        "total_nota",
                        "total_ultimo_servicio",
                        "meses_desde_venta",
                    )
                },
                "agencia": agencia_actual or "",
                "fecha_venta": fecha_iso(item.get("fecha_venta")),
                "fecha_salida": fecha_iso(item.get("fecha_salida")),
                "fecha_ultima_os": fecha_iso(item.get("fecha_ultima_os")),
                "cumpleaños": fecha_iso(item.get("cumpleaños")),
                "total_nota": item.get("total_nota") or "",
                "total_nota_numero": decimal_desde_texto(item.get("total_nota")),
                "total_ultimo_servicio": item.get("total_ultimo_servicio") or "",
                "total_ultimo_servicio_numero": decimal_desde_texto(item.get("total_ultimo_servicio")),
                "meses_desde_venta": item.get("meses_desde_venta"),
            })

        return Response(data)

    @action(detail=False, methods=["get"], url_path="opciones")
    def opciones(self, request):
        limite = 100000

        sin_venta = str(request.query_params.get("sin_venta", "")).strip().lower()
        es_sin_venta = sin_venta in ("1", "true", "si", "sí", "yes")

        qs = OrdenServicioVentaVW.objects.using(DB_ALIAS).all()

        if es_sin_venta:
            qs = qs.filter(fecha_venta__isnull=True, fecha_ultima_os__isnull=False)
            campo_agencia = "agencia_servicio"
        else:
            qs = qs.filter(fecha_venta__isnull=False)
            campo_agencia = "agencia_venta"

        qs = qs.values(
            "fecha_ultima_os",
            "estado_actividad",
            "segmento",
            "marca",
            "modelo_nombre",
            campo_agencia,
            "condicion_vehiculo",
        )[:limite]

        anios = set()
        anio_mes_set = set()
        estados = set()
        segmentos = set()
        marcas = set()
        modelos = set()
        agencias = set()
        condiciones = set()

        for item in qs:
            fecha = item.get("fecha_ultima_os")

            if fecha:
                anios.add(fecha.year)
                anio_mes_set.add((fecha.year, fecha.month))

            estado = str(item.get("estado_actividad") or "").strip()
            segmento = normalizar_segmento(item.get("segmento"))
            marca = str(item.get("marca") or "").strip()
            modelo = str(item.get("modelo_nombre") or "").strip()
            agencia = str(item.get(campo_agencia) or "").strip()
            condicion = str(item.get("condicion_vehiculo") or "").strip()

            if estado:
                estados.add(estado)

            if segmento:
                segmentos.add(segmento)

            if marca:
                marcas.add(marca)

            if modelo:
                modelos.add(modelo)

            if agencia:
                agencias.add(agencia)

            if condicion:
                condiciones.add(condicion)

        anio_mes = [
            {"anio": anio, "mes": mes}
            for anio, mes in sorted(
                anio_mes_set,
                key=lambda valor: (valor[0], valor[1]),
                reverse=True,
            )
        ]

        meses_por_anio = {}

        for item in anio_mes:
            clave = str(item["anio"])
            meses_por_anio.setdefault(clave, []).append(item["mes"])

        for clave in meses_por_anio:
            meses_por_anio[clave] = sorted(set(meses_por_anio[clave]))

        def ordenar_segmento(valor):
            match = re.search(r"(\d+)", valor)
            return int(match.group(1)) if match else 999

        return Response({
            "anios": sorted(anios, reverse=True),
            "anio_mes": anio_mes,
            "meses_por_anio": meses_por_anio,
            "estados": sorted(estados, key=str.lower),
            "segmentos": sorted(segmentos, key=ordenar_segmento),
            "marcas": sorted(marcas, key=str.lower),
            "modelos": sorted(modelos, key=str.lower),
            "agencias": sorted(agencias, key=str.lower),
            "condiciones": sorted(condiciones, key=str.lower),
        })
    
    @action(detail=False, methods=["get"], url_path="resumen")
    def resumen(self, request):
        qs = self.get_queryset()

        datos = qs.aggregate(
            total_vehiculos=Count("vin", distinct=True),
            total_servicio=Sum("total_ultimo_servicio"),
        )

        activos = qs.filter(
            estado_actividad__iexact="Activo"
        ).aggregate(
            total=Count("vin", distinct=True)
        )["total"] or 0

        inactivos = qs.filter(
            estado_actividad__iexact="Inactivo"
        ).aggregate(
            total=Count("vin", distinct=True)
        )["total"] or 0

        total_vehiculos = datos["total_vehiculos"] or 0
        total_servicio = datos["total_servicio"] or Decimal("0")
        retorno = (activos / total_vehiculos * 100) if total_vehiculos else 0

        return Response({
            "total_vehiculos": total_vehiculos,
            "activos": activos,
            "inactivos": inactivos,
            "total_servicio": float(total_servicio),
            "retorno": retorno,
        })

    @action(detail=True, methods=["get"], url_path="historial")
    def historial(self, request, vin=None):
        """
        Historial completo de órdenes de servicio de un VIN,
        tomado de Ventas_Ordenes_Servicio_Completas_VW.
        """
        qs = (
            OrdenServicioCompletaVW.objects.using(DB_ALIAS)
            .filter(vin=vin)
            .order_by("-fecha_os")
        )
        serializer = OrdenServicioCompletaVWSerializer(qs, many=True)
        return Response(serializer.data)

from .serializers import (
    OrdenServicioCompletaVWSerializer,
    OrdenServicioVentaVWSerializer,
    TareaClienteSerializer,
)


class TareaClienteViewSet(viewsets.ModelViewSet):
    """
    CRUD completo de tareas ligadas al teléfono del cliente.
    A diferencia de OrdenServicioVentaViewSet, esta tabla sí es editable
    y vive en la base de datos default de Django.
    """
    serializer_class = TareaClienteSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = TareaCliente.objects.all()
        telefono = self.request.query_params.get("telefono")
        if telefono:
            qs = qs.filter(telefono_cliente=telefono.strip())
        return qs.order_by("-created_at")        