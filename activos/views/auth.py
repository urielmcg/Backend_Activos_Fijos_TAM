from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.exceptions import Throttled
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import exception_handler as exception_handler_drf
from ..serializers import CustomTokenObtainPairSerializer, RegisterSerializer
from ..utils_seguridad import exigir_turnstile

from django.conf import settings


def manejar_throttling(exc, context):
    """
    EXCEPTION_HANDLER global de DRF (REST_FRAMEWORK["EXCEPTION_HANDLER"]).

    El 429 de throttling se expone en español con formato amigable; el resto
    de excepciones se delega al handler nativo de DRF.
    """
    if isinstance(exc, Throttled):
        espera = exc.wait
        if espera:
            mensaje = f"Demasiadas solicitudes. Intente de nuevo en {int(espera)} segundos."
        else:
            mensaje = "Demasiadas solicitudes. Espere unos segundos antes de reintentar."
        return Response(
            {"success": False, "error": mensaje},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    return exception_handler_drf(exc, context)


# --- THROTTLING DEL REFRESH DE TOKEN ---
# core/urls.py registra TokenRefreshView de simplejwt directamente y urls.py
# no es superficie de edición de esta tarea. Para aplicarle throttling sin
# tocarlo, fijamos el scope en la clase importada: DRF lo lee por request.
# Tasas por scope: REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] en core/settings.py.
TokenRefreshView.throttle_classes = (ScopedRateThrottle,)
TokenRefreshView.throttle_scope = "refresh"


class CustomLoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        try:
            response = super().post(request, *args, **kwargs)

            if response.status_code == 200:
                response.data["success"] = True
                response.data["message"] = "Bienvenido a TAMEP"

            return response

        except Exception as e:
            return Response({
                "success": False,
                "error": "Credenciales incorrectas."
            }, status=status.HTTP_401_UNAUTHORIZED)


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "register"

    def post(self, request):
        guard = exigir_turnstile(request)
        if guard:
            return guard
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "success": True,
                "message": "Solicitud de registro enviada. Un administrador revisará y activará su cuenta.",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                }
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
