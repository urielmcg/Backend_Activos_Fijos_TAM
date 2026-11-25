import logging

import requests
from django.conf import settings
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def validar_captcha(token):
    """
    Función puente legacy: siempre devuelve True para no romper tests/code
    que todavía dependen de Cloudflare Turnstile deshabilitado.
    """
    return True


def validar_turnstile(token, remoteip=None):
    """
    Valida un token de Cloudflare Turnstile contra el endpoint oficial
    (settings.TURNSTILE_VERIFY_URL).

    - Si Turnstile está deshabilitado (TURNSTILE_ENABLED=False, p. ej. en
      `manage.py test`) devuelve True sin tocar la red.
    - Token vacío en blanco -> False.
    - Falla cerrado: cualquier excepción (red, JSON inválido) se registra
      en el log sin secretos y devuelve False.
    """
    if not settings.TURNSTILE_ENABLED:
        return True
    if not token or not str(token).strip():
        return False

    # La API actual de siteverify exige el parámetro `response` (el
    # histórico `token` ya no se lee: responde missing-input-response).
    # Se envían ambos por compatibilidad con la documentación de Cloudflare.
    datos = {
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": token,
        "token": token,
    }
    if remoteip:
        datos["remoteip"] = remoteip

    try:
        resp = requests.post(settings.TURNSTILE_VERIFY_URL, data=datos, timeout=5)
        return resp.json().get("success") is True
    except Exception as exc:
        # Sin secretos ni token en el mensaje: solo el tipo de error.
        logger.warning("Turnstile: no se pudo verificar el token (%s)", type(exc).__name__)
        return False


def exigir_turnstile(request):
    """
    Guard compartido por los endpoints de creación de registros.

    Lee `turnstile_token` de request.data (funciona igual con JSON y con
    multipart/form-data) y devuelve:
    - None si la verificación pasa (o Turnstile está deshabilitado),
    - Response 400 {"detail": "Verificación Turnstile requerida."} si falta,
    - Response 400 {"detail": "Verificación Turnstile falló. Intente de nuevo."}
      si el token está presente pero no valida.

    Uso en la vista (al inicio del handler, antes de cualquier escritura):
        guard = exigir_turnstile(request)
        if guard:
            return guard
    """
    if not settings.TURNSTILE_ENABLED:
        return None

    token = request.data.get("turnstile_token")
    if not token or not str(token).strip():
        return Response({"detail": "Verificación Turnstile requerida."}, status=400)
    if not validar_turnstile(token, request.META.get("REMOTE_ADDR")):
        return Response({"detail": "Verificación Turnstile falló. Intente de nuevo."}, status=400)
    return None
