# retencion/views.py
import re
from decimal import Decimal, InvalidOperation

from django.db.models import Q
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
        estado = params.get("estado")
        segmento = params.get("segmento")
        marca = params.get("marca")
        modelo = params.get("modelo")
        agencia = params.get("agencia")
        condicion = params.get("condicion")
        search = params.get("search")

        if not es_filtro_vacio(anio):
            try:
                qs = qs.filter(fecha_ultima_os__year=int(anio))
            except ValueError:
                pass

        if not es_filtro_vacio(mes):
            try:
                qs = qs.filter(fecha_ultima_os__month=int(mes))
            except ValueError:
                pass

        if not es_filtro_vacio(estado):
            qs = qs.filter(estado_actividad__iexact=estado)

        if not es_filtro_vacio(segmento):
            qs = qs.filter(segmento__iexact=segmento)

        if not es_filtro_vacio(marca):
            qs = qs.filter(marca__iexact=marca)

        if not es_filtro_vacio(modelo):
            qs = qs.filter(modelo_nombre__iexact=modelo)

        if not es_filtro_vacio(agencia):
            qs = qs.filter(agencia__iexact=agencia)

        if not es_filtro_vacio(condicion):
            qs = qs.filter(condicion_vehiculo__iexact=condicion)

        if not es_filtro_vacio(search):
            texto = search.strip()
            qs = qs.filter(
                Q(vin__icontains=texto)
                | Q(nombre_cliente__icontains=texto)
                | Q(telefono_cliente__icontains=texto)
                | Q(correo_cliente__icontains=texto)
                | Q(placa_vehiculo__icontains=texto)
                | Q(numero_nota__icontains=texto)
                | Q(ultima_orden_servicio__icontains=texto)
            )

        return qs

    def aplicar_ordenamiento(self, qs):
        ordering = self.request.query_params.get("ordering", "-fecha_ultima_os")
        campo = self.ordering_permitido.get(ordering, "-fecha_ultima_os")
        return qs.order_by(campo)

    @action(detail=False, methods=["get"], url_path="ligero")
    def ligero(self, request):
        limite = request.query_params.get("limit", "10000")
        try:
            limite = int(limite)
        except ValueError:
            limite = 10000
        limite = max(100, min(limite, 100000))

        campos = (
            "vin",
            "agencia",
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
            "telefono_cliente2",
            "telefono_cliente3",
            "correo_cliente",
            "correo_cliente",
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
            data.append(
                {
                    **{k: (item.get(k) or "") for k in campos if k not in (
                        "fecha_venta", "fecha_salida", "fecha_ultima_os",
                        "total_nota", "total_ultimo_servicio", "meses_desde_venta",
                    )},
                    "fecha_venta": fecha_iso(item.get("fecha_venta")),
                    "fecha_salida": fecha_iso(item.get("fecha_salida")),
                    "fecha_ultima_os": fecha_iso(item.get("fecha_ultima_os")),
                    "total_nota": item.get("total_nota") or "",
                    "total_nota_numero": decimal_desde_texto(item.get("total_nota")),
                    "total_ultimo_servicio": item.get("total_ultimo_servicio") or "",
                    "total_ultimo_servicio_numero": decimal_desde_texto(
                        item.get("total_ultimo_servicio")
                    ),
                    "meses_desde_venta": item.get("meses_desde_venta") or 0,
                }
            )

        return Response(data)

    @action(detail=False, methods=["get"], url_path="opciones")
    def opciones(self, request):
        limite = 100000
        qs = (
            OrdenServicioVentaVW.objects.using(DB_ALIAS)
            .all()
            .values(
                "fecha_ultima_os",
                "estado_actividad",
                "segmento",
                "marca",
                "modelo_nombre",
                "agencia",
                "condicion_vehiculo",
            )[:limite]
        )

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

            for campo, target in (
                ("estado_actividad", estados),
                ("segmento", segmentos),
                ("marca", marcas),
                ("modelo_nombre", modelos),
                ("agencia", agencias),
                ("condicion_vehiculo", condiciones),
            ):
                valor = str(item.get(campo) or "").strip()
                if valor:
                    target.add(valor)

        anio_mes = [
            {"anio": anio, "mes": mes}
            for anio, mes in sorted(anio_mes_set, key=lambda v: (v[0], v[1]), reverse=True)
        ]

        meses_por_anio = {}
        for item in anio_mes:
            anio = str(item["anio"])
            meses_por_anio.setdefault(anio, []).append(item["mes"])
        for anio in meses_por_anio:
            meses_por_anio[anio] = sorted(set(meses_por_anio[anio]))

        return Response(
            {
                "anios": sorted(anios, reverse=True),
                "anio_mes": anio_mes,
                "meses_por_anio": meses_por_anio,
                "estados": sorted(estados, key=str.lower),
                "segmentos": sorted(segmentos, key=str.lower),
                "marcas": sorted(marcas, key=str.lower),
                "modelos": sorted(modelos, key=str.lower),
                "agencias": sorted(agencias, key=str.lower),
                "condiciones": sorted(condiciones, key=str.lower),
            }
        )

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
    telefono = self.request.query_params.get("telefono_cliente")  
    if telefono:
        qs = qs.filter(telefono_cliente=telefono.strip())
    return qs.order_by("-created_at")      