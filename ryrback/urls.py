from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path("conformidad/", include("CrmConformidad.urls")),
    path("digitales/", include("Digitales.urls")),
    path("citas/", include("citas.urls")),
    path("api/clickup/", include("clickup.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
