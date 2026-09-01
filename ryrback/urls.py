# ryrback/urls.py
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static



urlpatterns = [
    path("admin/", admin.site.urls),
    path("conformidad/", include("CrmConformidad.urls")),
    path("digitales/", include("Digitales.urls")),
    path("flujo/", include("flujo.urls")),
    path("citas/", include("citas.urls")),
    path("api/clickup/", include("clickup.urls")),
    path("financieros/", include("Financieros.urls")),
    path("usados/", include("usados.urls")),
    path("api/", include("Encuestas.urls")),
    path("api/", include("PedidosPiezas.urls")),
    path("api/", include("Safety.urls")),
    path("api/rrhh/", include("rrhh.urls")),
    path("trafico-piso/", include("trafico_piso.urls")),
    path("campanas-meta/", include("meta_ads.urls")),
    path("retencion/", include("retencion.urls")),
    path("jdpower/", include("jdpower.urls")),
    path("inventario/", include("inventario.urls")),
    path("hojaingresos/", include("hojaingresos.urls")),
    path("api/notificaciones/", include("notificaciones.urls")),
    path("api/BitacoraMantenimiento/", include("BitacoraMantenimiento.urls")),
    path("documentacion/", include("documentacion.urls")),
    path("gestion_inversion/", include("gestion_inversion.urls"),),
    path("ventas-vn/",include("ventas_vn.urls"),
),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)