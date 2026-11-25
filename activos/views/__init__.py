"""
Exportes públicos del paquete ``activos.views``.

Los ViewSets se cargan de forma perezosa (PEP 562) por arquitectura de
imports, no por estética:

``core.settings`` apunta ``REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]`` a
``activos.views.paginacion.PaginacionEstandar``. DRF resuelve esa ruta a
mitad de la importación de ``rest_framework.generics`` (cuando define
``GenericAPIView.pagination_class``). Con imports eager aquí, ese primer
import de ``activos.views`` termina trayendo ``rest_framework.viewsets``,
que necesita ``generics.GenericAPIView`` todavía a medio cargar y revienta
``manage.py check`` con:

    AttributeError: partially initialized module
    'rest_framework.generics' has no attribute 'GenericAPIView'

Con ``__getattr__`` el paquete termina de cargarse sin tocar DRF. DRF carga
``activos.views.paginacion`` sin ciclar y recién después ``core/urls.py``
pide los ViewSets, cuando ``generics`` ya está completo.
"""

from importlib import import_module

_EXPORTS = {
    "ActivoViewSet": ".activos",
    "detalle_activo_qr": ".activos",
    "DesignacionViewSet": ".designaciones",
    "TransferenciaViewSet": ".transferencias",
    "BajaActivoViewSet": ".baja",
    "SolicitudServicioViewSet": ".soporte",
    "IntervencionViewSet": ".soporte",
    "CustomLoginView": ".auth",
    "RegisterView": ".auth",
    "ActivoReporteViewSet": ".reportes",
    "UserProfileView": ".usuarios",
    "UserViewSet": ".usuarios",
    "NotificacionViewSet": ".notificaciones",
    "AuditoriaViewSet": ".notificaciones",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name):
    """Importa el módulo que define `name` la primera vez que se pide."""
    try:
        modulo = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
    valor = getattr(import_module(modulo, __name__), name)
    globals()[name] = valor  # cachea: las siguientes lecturas no re-importan
    return valor


def __dir__():
    return sorted(set(globals()) | set(__all__))
