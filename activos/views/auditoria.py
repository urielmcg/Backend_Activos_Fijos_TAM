"""
Auditoría de las mutaciones hechas por la API.

`AuditoriaViewSet` (ver notificaciones.py) y la pantalla `/auditoria` del
frontend leen `django.contrib.admin.LogEntry`: la tabla `django_admin_log`.
Antes de este módulo esa tabla solo se llenaba desde `/admin/`, así que
cualquier create/update/delete hecho por la API quedaba invisible.

Decisión de diseño: NO hay modelos nuevos ni migraciones. La BD real es
compartida y el MariaDB local 10.4 no admite migrar con Django 5.2, así que
reusamos la tabla que Django admin ya crea y que el serializer de auditoría
ya conoce.

Superficie: mixin `AuditoriaApiMixin` para los ModelViewSet con escritura del
frontend (activos, designaciones, transferencias, operacion-baja, solicitudes,
intervenciones, users) + la función `registrar_log_api` para las acciones
custom que mutan sin pasar por perform_* (`devolver`, `procesar_baja`).
"""

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType

# Campos que NUNCA se escriben en el change_message (auditoría de credenciales).
CAMPOS_SENSIBLES = frozenset(
    {
        "password",
        "new_password",
        "old_password",
        "current_password",
        "token",
        "access",
        "refresh",
        "secret",
        "api_key",
        "apikey",
    }
)

# Límite de caracteres por valor resumido para no inflar el TextField.
_LIMITE_VALOR = 80
# Máximo de campos resumidos por operación.
_LIMITE_CAMPOS = 15


def _valor_resumido(valor):
    """Un valor legible y acotado del payload (archivos, fechas, etc.)."""
    if valor is None:
        return "vacío"
    # UploadedFile / FieldFile: solo el nombre, nunca el contenido.
    nombre = getattr(valor, "name", None)
    if nombre and not isinstance(valor, (str, bytes)):
        return nombre or "archivo"
    texto = str(valor)
    if len(texto) > _LIMITE_VALOR:
        return texto[: _LIMITE_VALOR - 3] + "..."
    return texto


def resumir_datos(datos, limite=_LIMITE_CAMPOS):
    """
    Resumen de campos en `clave=valor; clave=valor`, sin passwords ni tokens.

    Acepta `serializer.validated_data` o `request.data`. Los campos sensibles
    se listan como `[oculto]` para que se vea que llegaron pero sin el valor.
    """
    if not datos or not hasattr(datos, "items"):
        return ""

    partes = []
    for clave, valor in list(datos.items())[:limite]:
        if clave.lower() in CAMPOS_SENSIBLES:
            partes.append(f"{clave}=[oculto]")
        else:
            partes.append(f"{clave}={_valor_resumido(valor)}")
    return "; ".join(partes)


def registrar_log_api(request, action_flag, instance, detalle=""):
    """
    Escribe un LogEntry con el usuario REAL de la petición.

    Devuelve el LogEntry o None si la petición no tiene usuario autenticado
    (LogEntry.user es NOT NULL: no se puede auditar "nadie"). El content_type
    se resuelve con `for_concrete_model=False` para que la tabla reporte el
    modelo real y no el de una posible subclase.
    """
    usuario = getattr(request, "user", None)
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return None

    mensaje = f"{request.method} {request.path}"
    if detalle:
        mensaje += f" — {detalle}"

    return LogEntry.objects.log_actions(
        user_id=usuario.pk,
        queryset=[instance],
        action_flag=action_flag,
        change_message=mensaje,
        single_object=True,
    )


class AuditoriaApiMixin:
    """
    Registra en `django_admin_log` el create/update/delete de un ModelViewSet.

    Cómo se usa:
        class MiViewSet(AuditoriaApiMixin, ModelViewSet):
            ...

    Si la clase ya define `perform_create`/`perform_update`/`perform_destroy`
    (casi todas las del proyecto lo hacen para inyectar el usuario o capturar
    excepciones), DEBE llamar a `super().perform_x(serializer)` para que el
    mixin corra. MRO: la clase -> el mixin -> generics.

    El registro usa `serializer.validated_data` (lo que la API aceptó), no el
    payload crudo.
    """

    def perform_create(self, serializer, **kwargs):
        # `kwargs` va a serializer.save() (ej: solicitante=request.user).
        # Equivale a generics.CreateModelMixin.perform_create cuando no hay kwargs.
        serializer.save(**kwargs)
        # Los kwargs no quedan en validated_data (serializer.save() los asigna
        # directo sobre la instancia), pero son parte del hecho auditable:
        # hay que mostrar quién quedó como solicitante/técnico.
        datos = dict(serializer.validated_data)
        datos.update(kwargs)
        self.registrar_auditoria(ADDITION, serializer.instance, datos)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self.registrar_auditoria(CHANGE, serializer.instance, serializer.validated_data)

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        self.registrar_auditoria(DELETION, instance)

    def registrar_auditoria(self, action_flag, instance, datos=None, detalle=""):
        """
        Punto de entrada para las acciones custom que mutan un objeto sin
        pasar por perform_* (ej: `devolver`, `procesar_baja`).
        """
        if instance is None:
            return None
        resumen = resumir_datos(datos)
        if resumen:
            detalle = f"{detalle} — {resumen}" if detalle else resumen
        return registrar_log_api(self.request, action_flag, instance, detalle)
