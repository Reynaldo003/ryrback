# Volkswagen
# Digitales/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .resultados_ia import resultados_ia_view
from .views import (
    bienvenido,
    webhook,
    privacidad_meta_view,
    eliminacion_datos_meta_view,
    chats_list,
    contacto_por_telefono,
    enviar_mensaje_view,
    enviar_plantilla_view,
    enviar_media_view,
    mark_read_view,
    ProspectosViewSet,
    campanas_meta_recientes,
    contacto_updates,
    editar_mensaje_view,
    media_proxy_view,
    media_descargar_mp3_view,
    generar_resumen_prospecto_view,
    plantillas_whatsapp_view,
    plantillas_whatsapp_admin_view,
    plantilla_whatsapp_admin_detail_view,
    analizar_plantilla_whatsapp_view,
    catalogo_precios_actuales,
    mark_unread_view,
    llamar_whatsapp,
    bloquear_contacto_whatsapp_view,
    desbloquear_contacto_whatsapp_view,
    plantilla_whatsapp_admin_media_view,
    subir_media_plantilla_view,
)


from .asesor_logs import (
    analitica_asesores_view,
    analitica_cliente_view,
    analitica_evento_resultado_view,
)

from .ia_config import (
    ia_config_list,
    ia_config_detail,
    ia_config_publicar,
    ia_pausar_conversacion,
    ia_reactivar_conversacion,
    ia_estado_conversacion,
    ia_lineas_whatsapp,
)

from .respuestas_rapidas import (
    respuestas_rapidas_view,
    respuesta_rapida_detail_view,
)

from .ia_catalogo import (
    catalogo_vehiculos_list,
    catalogo_vehiculo_detail,
    catalogo_vehiculo_upload_media,
    catalogo_vehiculo_eliminar_media,
)

router = DefaultRouter()
router.register(r"prospectos", ProspectosViewSet, basename="prospectos")

urlpatterns = [
    path("bienvenido/", bienvenido),
    path("webhook/", webhook),
    path("privacidad-meta/", privacidad_meta_view),
    path("eliminacion-datos-meta/", eliminacion_datos_meta_view),

    path("chats/", chats_list),
    path("chats/mark-read/", mark_read_view),
    path("chats/mark-unread/", mark_unread_view),
    path("chats/bloquear/", bloquear_contacto_whatsapp_view),
    path("chats/desbloquear/", desbloquear_contacto_whatsapp_view),
    path("contacto/", contacto_por_telefono),
    path("contacto/updates/", contacto_updates),

    path("llamar-whatsapp/", llamar_whatsapp),

    path("mensajes/enviar/", enviar_mensaje_view),
    path("mensajes/enviar-media/", enviar_media_view),
    path("mensajes/enviar-plantilla/", enviar_plantilla_view),
    path("mensajes/plantillas/subir-media/", subir_media_plantilla_view,),
    
    path("mensajes/plantillas/", plantillas_whatsapp_view),

    path("mensajes/plantillas/admin/",plantillas_whatsapp_admin_view,),
    path("mensajes/plantillas/admin/analizar/",analizar_plantilla_whatsapp_view,),
    path("mensajes/plantillas/admin/media/", plantilla_whatsapp_admin_media_view,),
    path("mensajes/plantillas/admin/<str:template_id>/", plantilla_whatsapp_admin_detail_view,),

    path("mensajes/editar/", editar_mensaje_view),

    path("respuestas-rapidas/", respuestas_rapidas_view, name="respuestas-rapidas-list"),
    path("respuestas-rapidas/<int:respuesta_id>/", respuesta_rapida_detail_view, name="respuestas-rapidas-detail"),

    path("analitica/asesores/", analitica_asesores_view, name="digitales-analitica-asesores"),
    path("analitica/asesores/cliente/<int:expediente_id>/", analitica_cliente_view, name="digitales-analitica-cliente",),
    path("analitica/eventos/<uuid:evento_id>/resultado/",analitica_evento_resultado_view,name="digitales-analitica-evento-resultado",),

    path("analitica/resultados-ia/",resultados_ia_view,name="digitales-resultados-ia",),

    path("api/", include(router.urls)),
    path("api/campanas-meta/", campanas_meta_recientes),
    path("api/prospectos/<int:prospecto_id>/generar-resumen/",generar_resumen_prospecto_view,),

    path("media/<str:media_id>/", media_proxy_view, name="digitales-media-proxy"),
    path("media/<str:media_id>/descargar/", media_descargar_mp3_view, name="digitales-media-descargar"),
    path("catalogo/precios/", catalogo_precios_actuales, name="catalogo-precios"),

    path("ia/config/", ia_config_list, name="ia-config-list"),
    path("ia/config/<str:numero_asesor>/", ia_config_detail, name="ia-config-detail"),
    path("ia/config/<str:numero_asesor>/publicar/",ia_config_publicar,name="ia-config-publicar",),
    path("ia/conversacion/pausar/", ia_pausar_conversacion, name="ia-conversacion-pausar"),
    path("ia/conversacion/reactivar/", ia_reactivar_conversacion, name="ia-conversacion-reactivar"),
    path("ia/conversacion/estado/", ia_estado_conversacion, name="ia-conversacion-estado"),
    path("ia/lineas/", ia_lineas_whatsapp, name="ia-lineas-whatsapp"),

    path("catalogo/vehiculos/", catalogo_vehiculos_list, name="catalogo-vehiculos-list"),
    path("catalogo/vehiculos/<int:vehiculo_id>/",catalogo_vehiculo_detail,name="catalogo-vehiculo-detail",),
    path("catalogo/vehiculos/<int:vehiculo_id>/upload/",catalogo_vehiculo_upload_media,name="catalogo-vehiculo-upload",),
    path("catalogo/vehiculos/<int:vehiculo_id>/media/",catalogo_vehiculo_eliminar_media,name="catalogo-vehiculo-eliminar-media",),
]