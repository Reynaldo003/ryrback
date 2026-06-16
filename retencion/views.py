# retencion/views.py
import re
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import OrdenServicioVW
from .serializers import OrdenServicioVWSerializer


DB_ALIAS = "sqlserver"


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


class OrdenServicioPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000


class OrdenServicioViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrdenServicioVWSerializer
    pagination_class = OrdenServicioPagination

    # IMPORTANTE:
    # Tu CRM no usa JWT ni TokenAuthentication de DRF.
    # Por eso IsAuthenticated genera 403.
    #
    # La vista se protege desde React con AuthContext/ProtectedRoute.
    # Si después quieres protegerlo también a nivel backend,
    # hay que crear una Authentication personalizada usando la misma lógica
    # de /conformidad/api/auth/me/.
    permission_classes = [permissions.AllowAny]

    ordering_permitido = {
        "fecha_os": "fecha_os",
        "-fecha_os": "-fecha_os",
        "fecha_emision": "fecha_emision",
        "-fecha_emision": "-fecha_emision",
        "fecha_salida": "fecha_salida",
        "-fecha_salida": "-fecha_salida",
        "estado": "estado",
        "-estado": "-estado",
        "segmento": "segmento",
        "-segmento": "-segmento",
        "marca": "marca_auto",
        "-marca": "-marca_auto",
        "modelo": "modelo_auto",
        "-modelo": "-modelo_auto",
        "dias": "dias_os_a_actual",
        "-dias": "-dias_os_a_actual",
        "meses": "meses_actual_a_emision",
        "-meses": "-meses_actual_a_emision",
    }

    def get_queryset(self):
        qs = OrdenServicioVW.objects.using(DB_ALIAS).all()
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
        subtipo = params.get("subtipo")
        search = params.get("search")

        if not es_filtro_vacio(anio):
            try:
                qs = qs.filter(fecha_os__year=int(anio))
            except ValueError:
                pass

        if not es_filtro_vacio(mes):
            try:
                qs = qs.filter(fecha_os__month=int(mes))
            except ValueError:
                pass

        if not es_filtro_vacio(estado):
            qs = qs.filter(estado__iexact=estado)

        if not es_filtro_vacio(segmento):
            qs = qs.filter(segmento__iexact=segmento)

        if not es_filtro_vacio(marca):
            qs = qs.filter(marca_auto__iexact=marca)

        if not es_filtro_vacio(modelo):
            qs = qs.filter(modelo_auto__iexact=modelo)

        if not es_filtro_vacio(subtipo):
            qs = qs.filter(subtipo_os__iexact=subtipo)

        if not es_filtro_vacio(search):
            texto = search.strip()

            qs = qs.filter(
                Q(num_os__icontains=texto)
                | Q(chassi__icontains=texto)
                | Q(serie__icontains=texto)
                | Q(cliente_veiculo__icontains=texto)
                | Q(nombre__icontains=texto)
                | Q(telefono__icontains=texto)
                | Q(correo__icontains=texto)
            )

        return qs

    def aplicar_ordenamiento(self, qs):
        ordering = self.request.query_params.get("ordering", "-fecha_os")
        campo = self.ordering_permitido.get(ordering, "-fecha_os")

        return qs.order_by(campo)

    @action(detail=False, methods=["get"], url_path="ligero")
    def ligero(self, request):
        limite = request.query_params.get("limit", "10000")

        try:
            limite = int(limite)
        except ValueError:
            limite = 10000

        limite = max(100, min(limite, 20000))

        campos = (
            "chassi",
            "cliente_veiculo",
            "marca_auto",
            "modelo_auto",
            "num_os",
            "fecha_os",
            "fecha_emision",
            "fecha_salida",
            "estado",
            "dias_os_a_actual",
            "segmento",
            "meses_actual_a_emision",
            "num_nota",
            "total_nota",
            "subtipo_os",
            "telefono",
            "correo",
            "nombre",
            "serie",
            "total_servicio",
        )

        qs = self.get_queryset().values(*campos)[:limite]

        data = []

        for item in qs:
            total_servicio_numero = decimal_desde_texto(item.get("total_servicio"))
            total_nota_numero = decimal_desde_texto(item.get("total_nota"))

            data.append(
                {
                    "chassi": item.get("chassi") or "",
                    "cliente_veiculo": item.get("cliente_veiculo") or "",
                    "marca_auto": item.get("marca_auto") or "",
                    "modelo_auto": item.get("modelo_auto") or "",
                    "num_os": item.get("num_os") or "",
                    "fecha_os": fecha_iso(item.get("fecha_os")),
                    "fecha_emision": fecha_iso(item.get("fecha_emision")),
                    "fecha_salida": fecha_iso(item.get("fecha_salida")),
                    "estado": item.get("estado") or "",
                    "dias_os_a_actual": item.get("dias_os_a_actual") or 0,
                    "segmento": item.get("segmento") or "",
                    "meses_actual_a_emision": item.get("meses_actual_a_emision") or 0,
                    "num_nota": item.get("num_nota") or "",
                    "total_nota": item.get("total_nota") or "",
                    "total_nota_numero": total_nota_numero,
                    "subtipo_os": item.get("subtipo_os") or "",
                    "telefono": item.get("telefono") or "",
                    "correo": item.get("correo") or "",
                    "nombre": item.get("nombre") or "",
                    "serie": item.get("serie") or "",
                    "total_servicio": item.get("total_servicio") or "",
                    "total_servicio_numero": total_servicio_numero,
                }
            )

        return Response(data)

    @action(detail=False, methods=["get"], url_path="opciones")
    def opciones(self, request):
        limite = 20000

        qs = (
            OrdenServicioVW.objects.using(DB_ALIAS)
            .all()
            .values(
                "fecha_os",
                "estado",
                "segmento",
                "marca_auto",
                "modelo_auto",
                "subtipo_os",
            )[:limite]
        )

        anios = set()
        anio_mes_set = set()
        estados = set()
        segmentos = set()
        marcas = set()
        modelos = set()
        subtipos = set()

        for item in qs:
            fecha = item.get("fecha_os")

            if fecha:
                anios.add(fecha.year)
                anio_mes_set.add((fecha.year, fecha.month))

            estado = str(item.get("estado") or "").strip()
            segmento = str(item.get("segmento") or "").strip()
            marca = str(item.get("marca_auto") or "").strip()
            modelo = str(item.get("modelo_auto") or "").strip()
            subtipo = str(item.get("subtipo_os") or "").strip()

            if estado:
                estados.add(estado)

            if segmento:
                segmentos.add(segmento)

            if marca:
                marcas.add(marca)

            if modelo:
                modelos.add(modelo)

            if subtipo:
                subtipos.add(subtipo)

        anio_mes = [
            {
                "anio": anio,
                "mes": mes,
            }
            for anio, mes in sorted(
                anio_mes_set,
                key=lambda valor: (valor[0], valor[1]),
                reverse=True,
            )
        ]

        meses_por_anio = {}

        for item in anio_mes:
            anio = str(item["anio"])

            if anio not in meses_por_anio:
                meses_por_anio[anio] = []

            meses_por_anio[anio].append(item["mes"])

        for anio in meses_por_anio:
            meses_por_anio[anio] = sorted(list(set(meses_por_anio[anio])))

        return Response(
            {
                "anios": sorted(list(anios), reverse=True),
                "anio_mes": anio_mes,
                "meses_por_anio": meses_por_anio,
                "estados": sorted(estados, key=lambda texto: texto.lower()),
                "segmentos": sorted(segmentos, key=lambda texto: texto.lower()),
                "marcas": sorted(marcas, key=lambda texto: texto.lower()),
                "modelos": sorted(modelos, key=lambda texto: texto.lower()),
                "subtipos": sorted(subtipos, key=lambda texto: texto.lower()),
            }
        )