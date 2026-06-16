# jdpower/views.py
from django.db.models import Q
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import EncuestaJDPower, EncuestaJDPowerServicio
from .serializers import EncuestaJDPowerSerializer, EncuestaJDPowerServicioSerializer


DB_ALIAS = "sqlserver"


def es_filtro_vacio(valor):
    return valor in (None, "", "Todos", "Todas", "all", "null", "undefined")


def fecha_iso(valor):
    if not valor:
        return None
    return valor.isoformat()


def numero_seguro(valor):
    try:
        if valor is None:
            return 0
        return int(valor)
    except (TypeError, ValueError):
        return 0

class EncuestaJDPowerPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000


class EncuestaJDPowerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EncuestaJDPowerSerializer
    pagination_class = EncuestaJDPowerPagination

    permission_classes = [permissions.AllowAny]

    ordering_permitido = {
        "periodo": "periodo",
        "-periodo": "-periodo",
        "fecha_encuesta": "fecha_encuesta",
        "-fecha_encuesta": "-fecha_encuesta",
        "fecha_entrega": "fecha_entrega",
        "-fecha_entrega": "-fecha_entrega",
        "fecha_registro": "fecha_registro",
        "-fecha_registro": "-fecha_registro",
        "id_ventas": "id_ventas",
        "-id_ventas": "-id_ventas",
        "concesionaria": "concesionaria",
        "-concesionaria": "-concesionaria",
        "modelo": "modelo",
        "-modelo": "-modelo",
        "satisfaccion": "q1_satisfaccion_general",
        "-satisfaccion": "-q1_satisfaccion_general",
        "recomendacion": "p3_recomendacion_distribuidor",
        "-recomendacion": "-p3_recomendacion_distribuidor",
    }

    def get_queryset(self):
        qs = EncuestaJDPower.objects.using(DB_ALIAS).all()
        qs = self.aplicar_filtros(qs)
        qs = self.aplicar_ordenamiento(qs)
        return qs

    def aplicar_filtros(self, qs):
        params = self.request.query_params

        anio = params.get("anio")
        mes = params.get("mes")
        tipo = params.get("tipo")
        canal_envio = params.get("canal_envio")
        estatus = params.get("estatus")
        concesionaria = params.get("concesionaria")
        codigo_concesionaria = params.get("codigo_concesionaria")
        asesor = params.get("asesor")
        modelo = params.get("modelo")
        anio_vehiculo = params.get("anio_vehiculo")
        region = params.get("region")
        zona = params.get("zona")
        estado = params.get("estado")
        ciudad = params.get("ciudad")
        search = params.get("search")

        if not es_filtro_vacio(anio):
            try:
                qs = qs.filter(periodo__year=int(anio))
            except ValueError:
                pass

        if not es_filtro_vacio(mes):
            try:
                qs = qs.filter(periodo__month=int(mes))
            except ValueError:
                pass

        if not es_filtro_vacio(tipo):
            qs = qs.filter(tipo__iexact=tipo)

        if not es_filtro_vacio(canal_envio):
            qs = qs.filter(canal_envio__iexact=canal_envio)

        if not es_filtro_vacio(estatus):
            qs = qs.filter(estatus__iexact=estatus)

        if not es_filtro_vacio(concesionaria):
            qs = qs.filter(concesionaria__iexact=concesionaria)

        if not es_filtro_vacio(codigo_concesionaria):
            qs = qs.filter(codigo_concesionaria__iexact=codigo_concesionaria)

        if not es_filtro_vacio(asesor):
            qs = qs.filter(id_asesor__iexact=asesor)

        if not es_filtro_vacio(modelo):
            qs = qs.filter(modelo__iexact=modelo)

        if not es_filtro_vacio(anio_vehiculo):
            try:
                qs = qs.filter(anio_vehiculo=int(anio_vehiculo))
            except ValueError:
                pass

        if not es_filtro_vacio(region):
            qs = qs.filter(region__iexact=region)

        if not es_filtro_vacio(zona):
            qs = qs.filter(zona__iexact=zona)

        if not es_filtro_vacio(estado):
            qs = qs.filter(estado__iexact=estado)

        if not es_filtro_vacio(ciudad):
            qs = qs.filter(ciudad__iexact=ciudad)

        if not es_filtro_vacio(search):
            texto = search.strip()
            qs = qs.filter(
                Q(id_muestra__icontains=texto)
                | Q(id_encuesta__icontains=texto)
                | Q(chasis__icontains=texto)
                | Q(modelo__icontains=texto)
                | Q(concesionaria__icontains=texto)
                | Q(codigo_concesionaria__icontains=texto)
                | Q(id_asesor__icontains=texto)
                | Q(ciudad__icontains=texto)
                | Q(estado__icontains=texto)
                | Q(q1_1_razones_calificacion__icontains=texto)
                | Q(q3_comentarios_adicionales__icontains=texto)
                | Q(p1_1_comentarios_auto__icontains=texto)
            )

        return qs

    def aplicar_ordenamiento(self, qs):
        ordering = self.request.query_params.get("ordering", "-periodo")
        campo = self.ordering_permitido.get(ordering, "-periodo")
        return qs.order_by(campo)

    @action(detail=False, methods=["get"], url_path="ligero")
    def ligero(self, request):
        limite = request.query_params.get("limit", "10000")

        try:
            limite = int(limite)
        except ValueError:
            limite = 10000

        limite = max(100, min(limite, 30000))

        campos = (
            "id_ventas",
            "id_muestra",
            "id_encuesta",
            "tipo",
            "canal_envio",
            "estatus",
            "chasis",
            "modelo",
            "anio_vehiculo",
            "region",
            "zona",
            "estado",
            "ciudad",
            "codigo_concesionaria",
            "concesionaria",
            "id_asesor",
            "vwsf",
            "s1_entrega_vehiculo",
            "pn1_forma_compra",
            "pn2_empresa_financiamiento",
            "q1_satisfaccion_general",
            "q1_1_razones_calificacion",
            "qr_2_1_proceso_entrega",
            "qr_2_1_1_efectividad_explicacion",
            "qr_2_1_2_puntualidad_entrega",
            "qr_2_1_3_condiciones_vehiculo",
            "qr_2_1_4_conexion_bluetooth",
            "qr_2_2_atencion_personal",
            "qr_2_2_1_conocimiento_vehiculo",
            "qr_2_2_2_amabilidad",
            "qr_2_2_3_respuesta",
            "qr_2_2_4_comunicacion_fuera",
            "qr_2_2_5_uso_tecnologia",
            "qr_2_2_6_info_tiempo_entrega",
            "qr_2_3_instalaciones",
            "qr_2_3_1_apariencia",
            "qr_2_3_2_facilidad_inventario",
            "qr_2_3_3_variedad_modelos",
            "qr_2_3_4_calidad_amenidades",
            "qr_2_3_5_opciones_estacionamiento",
            "qr_2_4_documentacion",
            "qr_2_4_1_claridad_documentos",
            "qr_2_4_2_transparencia_papeleo",
            "qr_2_4_3_prontitud_papeleo",
            "qr_2_5_negociacion",
            "qr_2_5_1_acuerdo_precio",
            "qr_2_5_2_precio_justo",
            "qr_2_5_3_comodidad_negociacion",
            "q3_comentarios_adicionales",
            "p1_satisfaccion_producto",
            "p1_1_comentarios_auto",
            "p3_recomendacion_distribuidor",
            "q8_transferencia_datos",
            "q10_autoriza_publicacion",
            "fecha_registro",
            "fecha_entrega",
            "fecha_encuesta",
            "periodo",
        )

        qs = self.get_queryset().values(*campos)[:limite]

        data = []

        for item in qs:
            data.append(
                {
                    "id_ventas": item.get("id_ventas"),
                    "id_muestra": item.get("id_muestra") or "",
                    "id_encuesta": item.get("id_encuesta") or "",
                    "tipo": item.get("tipo") or "",
                    "canal_envio": item.get("canal_envio") or "",
                    "estatus": item.get("estatus") or "",
                    "chasis": item.get("chasis") or "",
                    "modelo": item.get("modelo") or "",
                    "anio_vehiculo": numero_seguro(item.get("anio_vehiculo")),
                    "region": item.get("region") or "",
                    "zona": item.get("zona") or "",
                    "estado": item.get("estado") or "",
                    "ciudad": item.get("ciudad") or "",
                    "codigo_concesionaria": item.get("codigo_concesionaria") or "",
                    "concesionaria": item.get("concesionaria") or "",
                    "id_asesor": item.get("id_asesor") or "",
                    "vwsf": item.get("vwsf") or "",
                    "s1_entrega_vehiculo": item.get("s1_entrega_vehiculo") or "",
                    "pn1_forma_compra": item.get("pn1_forma_compra") or "",
                    "pn2_empresa_financiamiento": item.get("pn2_empresa_financiamiento") or "",
                    "q1_satisfaccion_general": numero_seguro(item.get("q1_satisfaccion_general")),
                    "q1_1_razones_calificacion": item.get("q1_1_razones_calificacion") or "",
                    "qr_2_1_proceso_entrega": numero_seguro(item.get("qr_2_1_proceso_entrega")),
                    "qr_2_1_1_efectividad_explicacion": numero_seguro(item.get("qr_2_1_1_efectividad_explicacion")),
                    "qr_2_1_2_puntualidad_entrega": numero_seguro(item.get("qr_2_1_2_puntualidad_entrega")),
                    "qr_2_1_3_condiciones_vehiculo": numero_seguro(item.get("qr_2_1_3_condiciones_vehiculo")),
                    "qr_2_1_4_conexion_bluetooth": numero_seguro(item.get("qr_2_1_4_conexion_bluetooth")),
                    "qr_2_2_atencion_personal": numero_seguro(item.get("qr_2_2_atencion_personal")),
                    "qr_2_2_1_conocimiento_vehiculo": numero_seguro(item.get("qr_2_2_1_conocimiento_vehiculo")),
                    "qr_2_2_2_amabilidad": numero_seguro(item.get("qr_2_2_2_amabilidad")),
                    "qr_2_2_3_respuesta": numero_seguro(item.get("qr_2_2_3_respuesta")),
                    "qr_2_2_4_comunicacion_fuera": numero_seguro(item.get("qr_2_2_4_comunicacion_fuera")),
                    "qr_2_2_5_uso_tecnologia": numero_seguro(item.get("qr_2_2_5_uso_tecnologia")),
                    "qr_2_2_6_info_tiempo_entrega": numero_seguro(item.get("qr_2_2_6_info_tiempo_entrega")),
                    "qr_2_3_instalaciones": numero_seguro(item.get("qr_2_3_instalaciones")),
                    "qr_2_3_1_apariencia": numero_seguro(item.get("qr_2_3_1_apariencia")),
                    "qr_2_3_2_facilidad_inventario": numero_seguro(item.get("qr_2_3_2_facilidad_inventario")),
                    "qr_2_3_3_variedad_modelos": numero_seguro(item.get("qr_2_3_3_variedad_modelos")),
                    "qr_2_3_4_calidad_amenidades": numero_seguro(item.get("qr_2_3_4_calidad_amenidades")),
                    "qr_2_3_5_opciones_estacionamiento": numero_seguro(item.get("qr_2_3_5_opciones_estacionamiento")),
                    "qr_2_4_documentacion": numero_seguro(item.get("qr_2_4_documentacion")),
                    "qr_2_4_1_claridad_documentos": numero_seguro(item.get("qr_2_4_1_claridad_documentos")),
                    "qr_2_4_2_transparencia_papeleo": numero_seguro(item.get("qr_2_4_2_transparencia_papeleo")),
                    "qr_2_4_3_prontitud_papeleo": numero_seguro(item.get("qr_2_4_3_prontitud_papeleo")),
                    "qr_2_5_negociacion": numero_seguro(item.get("qr_2_5_negociacion")),
                    "qr_2_5_1_acuerdo_precio": numero_seguro(item.get("qr_2_5_1_acuerdo_precio")),
                    "qr_2_5_2_precio_justo": numero_seguro(item.get("qr_2_5_2_precio_justo")),
                    "qr_2_5_3_comodidad_negociacion": numero_seguro(item.get("qr_2_5_3_comodidad_negociacion")),
                    "q3_comentarios_adicionales": item.get("q3_comentarios_adicionales") or "",
                    "p1_satisfaccion_producto": numero_seguro(item.get("p1_satisfaccion_producto")),
                    "p1_1_comentarios_auto": item.get("p1_1_comentarios_auto") or "",
                    "p3_recomendacion_distribuidor": numero_seguro(item.get("p3_recomendacion_distribuidor")),
                    "q8_transferencia_datos": item.get("q8_transferencia_datos") or "",
                    "q10_autoriza_publicacion": item.get("q10_autoriza_publicacion") or "",
                    "fecha_registro": fecha_iso(item.get("fecha_registro")),
                    "fecha_entrega": fecha_iso(item.get("fecha_entrega")),
                    "fecha_encuesta": fecha_iso(item.get("fecha_encuesta")),
                    "periodo": fecha_iso(item.get("periodo")),
                }
            )

        return Response(data)

    @action(detail=False, methods=["get"], url_path="opciones")
    def opciones(self, request):
        limite = 30000

        qs = (
            EncuestaJDPower.objects.using(DB_ALIAS)
            .all()
            .values(
                "periodo",
                "tipo",
                "canal_envio",
                "estatus",
                "concesionaria",
                "codigo_concesionaria",
                "id_asesor",
                "modelo",
                "anio_vehiculo",
                "region",
                "zona",
                "estado",
                "ciudad",
            )[:limite]
        )

        anios = set()
        anio_mes_set = set()
        tipos = set()
        canales = set()
        estatuses = set()
        concesionarias = set()
        codigos_concesionaria = set()
        asesores = set()
        modelos = set()
        anios_vehiculo = set()
        regiones = set()
        zonas = set()
        estados = set()
        ciudades = set()

        for item in qs:
            periodo = item.get("periodo")

            if periodo:
                anios.add(periodo.year)
                anio_mes_set.add((periodo.year, periodo.month))

            valores = {
                "tipo": tipos,
                "canal_envio": canales,
                "estatus": estatuses,
                "concesionaria": concesionarias,
                "codigo_concesionaria": codigos_concesionaria,
                "id_asesor": asesores,
                "modelo": modelos,
                "region": regiones,
                "zona": zonas,
                "estado": estados,
                "ciudad": ciudades,
            }

            for campo, destino in valores.items():
                valor = str(item.get(campo) or "").strip()
                if valor:
                    destino.add(valor)

            if item.get("anio_vehiculo"):
                anios_vehiculo.add(item["anio_vehiculo"])

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
                "tipos": sorted(tipos, key=lambda texto: texto.lower()),
                "canales_envio": sorted(canales, key=lambda texto: texto.lower()),
                "estatuses": sorted(estatuses, key=lambda texto: texto.lower()),
                "concesionarias": sorted(concesionarias, key=lambda texto: texto.lower()),
                "codigos_concesionaria": sorted(codigos_concesionaria, key=lambda texto: texto.lower()),
                "asesores": sorted(asesores, key=lambda texto: texto.lower()),
                "modelos": sorted(modelos, key=lambda texto: texto.lower()),
                "anios_vehiculo": sorted(list(anios_vehiculo), reverse=True),
                "regiones": sorted(regiones, key=lambda texto: texto.lower()),
                "zonas": sorted(zonas, key=lambda texto: texto.lower()),
                "estados": sorted(estados, key=lambda texto: texto.lower()),
                "ciudades": sorted(ciudades, key=lambda texto: texto.lower()),
            }
        )


#  SERVICIO  
class EncuestaJDPowerServicioPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000


class EncuestaJDPowerServicioViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EncuestaJDPowerServicioSerializer
    pagination_class = EncuestaJDPowerServicioPagination
    permission_classes = [permissions.AllowAny]

    ordering_permitido = {
        "periodo": "periodo",
        "-periodo": "-periodo",
        "fecha_servicio": "fecha_servicio",
        "-fecha_servicio": "-fecha_servicio",
        "fecha_completo_encuesta": "fecha_completo_encuesta",
        "-fecha_completo_encuesta": "-fecha_completo_encuesta",
        "id_encuesta": "id_encuesta",
        "-id_encuesta": "-id_encuesta",
        "concesionaria": "concesionaria",
        "-concesionaria": "-concesionaria",
        "modelo": "modelo",
        "-modelo": "-modelo",
        "satisfaccion": "q1_satisfaccion_general",
        "-satisfaccion": "-q1_satisfaccion_general",
        "recomendacion": "q3_recomendacion",
        "-recomendacion": "-q3_recomendacion",
        "indice": "indice_satisfaccion_general",
        "-indice": "-indice_satisfaccion_general",
    }

    def get_queryset(self):
        qs = EncuestaJDPowerServicio.objects.using(DB_ALIAS).all()
        qs = self.aplicar_filtros(qs)
        qs = self.aplicar_ordenamiento(qs)
        return qs

    def aplicar_filtros(self, qs):
        params = self.request.query_params

        anio = params.get("anio")
        mes = params.get("mes")
        tipo = params.get("tipo")
        tipo_servicio = params.get("tipo_servicio")
        canal_envio = params.get("canal_envio")
        estatus = params.get("estatus")
        concesionaria = params.get("concesionaria")
        codigo_concesionaria = params.get("codigo_concesionaria")
        asesor = params.get("asesor")
        modelo = params.get("modelo")
        anio_vehiculo = params.get("anio_vehiculo")
        region = params.get("region")
        zona = params.get("zona")
        estado = params.get("estado")
        search = params.get("search")

        if not es_filtro_vacio(anio):
            try:
                qs = qs.filter(periodo__year=int(anio))
            except ValueError:
                pass

        if not es_filtro_vacio(mes):
            try:
                qs = qs.filter(periodo__month=int(mes))
            except ValueError:
                pass

        if not es_filtro_vacio(tipo):
            qs = qs.filter(tipo__iexact=tipo)

        if not es_filtro_vacio(tipo_servicio):
            qs = qs.filter(tipo_servicio__iexact=tipo_servicio)

        if not es_filtro_vacio(canal_envio):
            qs = qs.filter(canal_envio__iexact=canal_envio)

        if not es_filtro_vacio(estatus):
            qs = qs.filter(estatus__iexact=estatus)

        if not es_filtro_vacio(concesionaria):
            qs = qs.filter(concesionaria__iexact=concesionaria)

        if not es_filtro_vacio(codigo_concesionaria):
            qs = qs.filter(codigo_concesionaria__iexact=codigo_concesionaria)

        if not es_filtro_vacio(asesor):
            qs = qs.filter(id_asesor__iexact=asesor)

        if not es_filtro_vacio(modelo):
            qs = qs.filter(modelo__iexact=modelo)

        if not es_filtro_vacio(anio_vehiculo):
            try:
                qs = qs.filter(anio_vehiculo=int(anio_vehiculo))
            except ValueError:
                pass

        if not es_filtro_vacio(region):
            qs = qs.filter(region__iexact=region)

        if not es_filtro_vacio(zona):
            qs = qs.filter(zona__iexact=zona)

        if not es_filtro_vacio(estado):
            qs = qs.filter(estado__iexact=estado)

        if not es_filtro_vacio(search):
            texto = search.strip()
            qs = qs.filter(
                Q(id_servicio__icontains=texto)
                | Q(chasis__icontains=texto)
                | Q(modelo__icontains=texto)
                | Q(concesionaria__icontains=texto)
                | Q(codigo_concesionaria__icontains=texto)
                | Q(id_asesor__icontains=texto)
                | Q(estado__icontains=texto)
                | Q(q1_1_razones_calificacion__icontains=texto)
                | Q(q4_comentarios_servicio__icontains=texto)
                | Q(p1_1_comentarios_auto__icontains=texto)
            )

        return qs

    def aplicar_ordenamiento(self, qs):
        ordering = self.request.query_params.get("ordering", "-periodo")
        campo = self.ordering_permitido.get(ordering, "-periodo")
        return qs.order_by(campo)

    @action(detail=False, methods=["get"], url_path="ligero")
    def ligero(self, request):
        limite = request.query_params.get("limit", "10000")

        try:
            limite = int(limite)
        except ValueError:
            limite = 10000

        limite = max(100, min(limite, 30000))

        campos = (
            "id",
            "id_servicio",
            "id_muestra",
            "id_encuesta",
            "tipo",
            "periodo",
            "canal_envio",
            "estatus",
            "fecha_registro_procesado",
            "fecha_servicio",
            "fecha_completo_encuesta",
            "tipo_servicio",
            "chasis",
            "modelo",
            "anio_vehiculo",
            "region",
            "zona",
            "estado",
            "codigo_concesionaria",
            "concesionaria",
            "id_asesor",
            "s1_confirma_concesionario",
            "q1_satisfaccion_general",
            "q1_1_razones_calificacion",
            "q2_1_calidad_servicio",
            "q2_1a_problema_no_resuelto",
            "q2_1b_sin_refacciones",
            "q2_1c_condiciones_auto",
            "q2_1d_tiempo_taller",
            "q2_2_cita_servicio",
            "q2_2c_sin_cita",
            "q2_3_atendido_valorado",
            "q2_3a_amabilidad_personal",
            "q2_3b_recepcion_rapida",
            "q2_3c_informado_estatus",
            "q2_3d_transparencia",
            "q2_4_explicacion_info",
            "q2_4a_explico_trabajos_costo",
            "q2_4b_enfocado_necesidades",
            "q2_4c_conocimiento_respuesta",
            "q2_4d_reviso_trabajos_entrega",
            "q2_4e_monto_justo",
            "q2_5_entrega",
            "q2_5a_atendido_inmediato",
            "q2_5b_auto_listo_fecha",
            "q2_5c_tiempo_recoger_auto",
            "q2_6_instalaciones_amenidades",
            "q2_6a_entrada_salida",
            "q2_6b_agencia_limpia",
            "q2_6c_sala_espera",
            "q2_6d_amenidades",
            "q3_recomendacion",
            "q4_comentarios_servicio",
            "p1_satisfaccion_producto",
            "p1_1_comentarios_auto",
            "ot1_autoriza_compartir_datos",
            "q9_autoriza_seguimiento",
            "q9a_autoriza_transferencia",
            "q10_autoriza_publicacion",
            "indice_satisfaccion_general",
            "fecha_carga",
        )

        qs = self.get_queryset().values(*campos)[:limite]

        data = []

        for item in qs:
            data.append(
                {
                    "id": item.get("id"),
                    "id_servicio": item.get("id_servicio") or "",
                    "id_muestra": numero_seguro(item.get("id_muestra")),
                    "id_encuesta": numero_seguro(item.get("id_encuesta")),
                    "tipo": item.get("tipo") or "",
                    "periodo": fecha_iso(item.get("periodo")),
                    "canal_envio": item.get("canal_envio") or "",
                    "estatus": item.get("estatus") or "",
                    "fecha_registro_procesado": fecha_iso(item.get("fecha_registro_procesado")),
                    "fecha_servicio": fecha_iso(item.get("fecha_servicio")),
                    "fecha_completo_encuesta": fecha_iso(item.get("fecha_completo_encuesta")),
                    "tipo_servicio": item.get("tipo_servicio") or "",
                    "chasis": item.get("chasis") or "",
                    "modelo": item.get("modelo") or "",
                    "anio_vehiculo": numero_seguro(item.get("anio_vehiculo")),
                    "region": item.get("region") or "",
                    "zona": item.get("zona") or "",
                    "estado": item.get("estado") or "",
                    "codigo_concesionaria": item.get("codigo_concesionaria") or "",
                    "concesionaria": item.get("concesionaria") or "",
                    "id_asesor": item.get("id_asesor") or "",
                    "s1_confirma_concesionario": item.get("s1_confirma_concesionario") or "",
                    "q1_satisfaccion_general": numero_seguro(item.get("q1_satisfaccion_general")),
                    "q1_1_razones_calificacion": item.get("q1_1_razones_calificacion") or "",
                    "q2_1_calidad_servicio": numero_seguro(item.get("q2_1_calidad_servicio")),
                    "q2_1a_problema_no_resuelto": item.get("q2_1a_problema_no_resuelto") or "",
                    "q2_1b_sin_refacciones": item.get("q2_1b_sin_refacciones") or "",
                    "q2_1c_condiciones_auto": item.get("q2_1c_condiciones_auto") or "",
                    "q2_1d_tiempo_taller": item.get("q2_1d_tiempo_taller") or "",
                    "q2_2_cita_servicio": numero_seguro(item.get("q2_2_cita_servicio")),
                    "q2_2c_sin_cita": item.get("q2_2c_sin_cita") or "",
                    "q2_3_atendido_valorado": numero_seguro(item.get("q2_3_atendido_valorado")),
                    "q2_3a_amabilidad_personal": item.get("q2_3a_amabilidad_personal") or "",
                    "q2_3b_recepcion_rapida": item.get("q2_3b_recepcion_rapida") or "",
                    "q2_3c_informado_estatus": item.get("q2_3c_informado_estatus") or "",
                    "q2_3d_transparencia": item.get("q2_3d_transparencia") or "",
                    "q2_4_explicacion_info": numero_seguro(item.get("q2_4_explicacion_info")),
                    "q2_4a_explico_trabajos_costo": item.get("q2_4a_explico_trabajos_costo") or "",
                    "q2_4b_enfocado_necesidades": item.get("q2_4b_enfocado_necesidades") or "",
                    "q2_4c_conocimiento_respuesta": item.get("q2_4c_conocimiento_respuesta") or "",
                    "q2_4d_reviso_trabajos_entrega": item.get("q2_4d_reviso_trabajos_entrega") or "",
                    "q2_4e_monto_justo": item.get("q2_4e_monto_justo") or "",
                    "q2_5_entrega": numero_seguro(item.get("q2_5_entrega")),
                    "q2_5a_atendido_inmediato": item.get("q2_5a_atendido_inmediato") or "",
                    "q2_5b_auto_listo_fecha": item.get("q2_5b_auto_listo_fecha") or "",
                    "q2_5c_tiempo_recoger_auto": item.get("q2_5c_tiempo_recoger_auto") or "",
                    "q2_6_instalaciones_amenidades": numero_seguro(item.get("q2_6_instalaciones_amenidades")),
                    "q2_6a_entrada_salida": item.get("q2_6a_entrada_salida") or "",
                    "q2_6b_agencia_limpia": item.get("q2_6b_agencia_limpia") or "",
                    "q2_6c_sala_espera": item.get("q2_6c_sala_espera") or "",
                    "q2_6d_amenidades": item.get("q2_6d_amenidades") or "",
                    "q3_recomendacion": numero_seguro(item.get("q3_recomendacion")),
                    "q4_comentarios_servicio": item.get("q4_comentarios_servicio") or "",
                    "p1_satisfaccion_producto": numero_seguro(item.get("p1_satisfaccion_producto")),
                    "p1_1_comentarios_auto": item.get("p1_1_comentarios_auto") or "",
                    "ot1_autoriza_compartir_datos": item.get("ot1_autoriza_compartir_datos") or "",
                    "q9_autoriza_seguimiento": item.get("q9_autoriza_seguimiento") or "",
                    "q9a_autoriza_transferencia": item.get("q9a_autoriza_transferencia") or "",
                    "q10_autoriza_publicacion": item.get("q10_autoriza_publicacion") or "",
                    "indice_satisfaccion_general": item.get("indice_satisfaccion_general"),
                    "fecha_carga": fecha_iso(item.get("fecha_carga")),
                }
            )

        return Response(data)

    @action(detail=False, methods=["get"], url_path="opciones")
    def opciones(self, request):
        limite = 30000

        qs = (
            EncuestaJDPowerServicio.objects.using(DB_ALIAS)
            .all()
            .values(
                "periodo",
                "tipo",
                "tipo_servicio",
                "canal_envio",
                "estatus",
                "concesionaria",
                "codigo_concesionaria",
                "id_asesor",
                "modelo",
                "anio_vehiculo",
                "region",
                "zona",
                "estado",
            )[:limite]
        )

        anios = set()
        anio_mes_set = set()
        tipos = set()
        tipos_servicio = set()
        canales = set()
        estatuses = set()
        concesionarias = set()
        codigos_concesionaria = set()
        asesores = set()
        modelos = set()
        anios_vehiculo = set()
        regiones = set()
        zonas = set()
        estados = set()

        for item in qs:
            periodo = item.get("periodo")

            if periodo:
                anios.add(periodo.year)
                anio_mes_set.add((periodo.year, periodo.month))

            valores = {
                "tipo": tipos,
                "tipo_servicio": tipos_servicio,
                "canal_envio": canales,
                "estatus": estatuses,
                "concesionaria": concesionarias,
                "codigo_concesionaria": codigos_concesionaria,
                "id_asesor": asesores,
                "modelo": modelos,
                "region": regiones,
                "zona": zonas,
                "estado": estados,
            }

            for campo, destino in valores.items():
                valor = str(item.get(campo) or "").strip()
                if valor:
                    destino.add(valor)

            if item.get("anio_vehiculo"):
                anios_vehiculo.add(item["anio_vehiculo"])

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
                "tipos": sorted(tipos, key=lambda texto: texto.lower()),
                "tipos_servicio": sorted(tipos_servicio, key=lambda texto: texto.lower()),
                "canales_envio": sorted(canales, key=lambda texto: texto.lower()),
                "estatuses": sorted(estatuses, key=lambda texto: texto.lower()),
                "concesionarias": sorted(concesionarias, key=lambda texto: texto.lower()),
                "codigos_concesionaria": sorted(codigos_concesionaria, key=lambda texto: texto.lower()),
                "asesores": sorted(asesores, key=lambda texto: texto.lower()),
                "modelos": sorted(modelos, key=lambda texto: texto.lower()),
                "anios_vehiculo": sorted(list(anios_vehiculo), reverse=True),
                "regiones": sorted(regiones, key=lambda texto: texto.lower()),
                "zonas": sorted(zonas, key=lambda texto: texto.lower()),
                "estados": sorted(estados, key=lambda texto: texto.lower()),
            }
        )