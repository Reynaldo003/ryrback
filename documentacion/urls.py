from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import ExpedienteViewSet,RequisitosView,DocumentoUploadView,DocumentoDeleteView,ExpedienteDownloadZipView

router = DefaultRouter()

router.register(r"expedientes",ExpedienteViewSet,basename="documentacion-expedientes",)

urlpatterns = [
    path("api/",include(router.urls),),
    path("api/requisitos/",RequisitosView.as_view(),name="documentacion-requisitos",),
    path("api/expedientes/<int:expediente_id>/documentos/",DocumentoUploadView.as_view(),name="documentacion-documentos-upload",),
    path("api/expedientes/<int:expediente_id>/descargar/",ExpedienteDownloadZipView.as_view(),name="documentacion-expediente-download",),
    path("api/documentos/<int:pk>/",DocumentoDeleteView.as_view(),name="documentacion-documentos-delete",),
]