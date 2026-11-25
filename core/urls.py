from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from activos.views import (
    ActivoViewSet,
    DesignacionViewSet,
    TransferenciaViewSet,
    ActivoReporteViewSet,
    BajaActivoViewSet,
    detalle_activo_qr,
    CustomLoginView,
    RegisterView,
    UserProfileView,
    UserViewSet,
    NotificacionViewSet,
    AuditoriaViewSet,
)
from activos.views.backup import BackupAPIView
from activos.views.dashboard import DashboardStatsAPIView
from activos.views.reportes import (
    GrupoContableViewSet,
    RegionalViewSet,
    TipoActivoViewSet,
    GerenciaViewSet,
    CargoViewSet,
)
from activos.views.soporte import IntervencionViewSet, SolicitudServicioViewSet
from activos.views.health import health_check

router = DefaultRouter()
router.register(r"activos", ActivoViewSet)
router.register(r"designaciones", DesignacionViewSet)
router.register(r"transferencias", TransferenciaViewSet, basename="transferencia")
router.register(r"operacion-baja", BajaActivoViewSet, basename="operacion-baja")
router.register(r"solicitudes", SolicitudServicioViewSet, basename="solicitud")
router.register(r"intervenciones", IntervencionViewSet, basename="intervencion")

# gestion activos
router.register(r"gestion-activos", ActivoReporteViewSet, basename="gestion-activos")
router.register(r"regionales", RegionalViewSet)
router.register(r"grupos-contables", GrupoContableViewSet)
router.register(r"tipos-activos", TipoActivoViewSet)
router.register(r"gerencias", GerenciaViewSet)
router.register(r"cargos", CargoViewSet)
router.register(r"users", UserViewSet, basename="user")
router.register(r"notificaciones", NotificacionViewSet, basename="notificacion")
router.register(r"auditoria", AuditoriaViewSet, basename="auditoria")
urlpatterns = [
    path("api/register/", RegisterView.as_view(), name="register"),
    path("api/login/", CustomLoginView.as_view(), name="login"),
    path(
        "api/dashboard/stats/", DashboardStatsAPIView.as_view(), name="dashboard_stats"
    ),
    path("api/backup/", BackupAPIView.as_view(), name="backup"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/me/", UserProfileView.as_view(), name="my-profile"),
    path("activo/detalle/<str:codigo>/", detalle_activo_qr, name="detalle_activo_qr"),
    path("chaining/", include("smart_selects.urls")),
    path("health/", health_check, name="health-check"),
]

# En producción (Render) servimos media con Django como fallback (disco efímero).
# Cuando se migre a Cloudinary, esto se reemplaza por el storage backend.
from django.views.static import serve as _serve_media
from django.urls import re_path as _re_path
urlpatterns += [
    _re_path(r"^media/(?P<path>.*)$", _serve_media, {"document_root": settings.MEDIA_ROOT}),
]
