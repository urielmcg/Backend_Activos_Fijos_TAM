from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.admin.models import LogEntry
from ..models import Notificacion
from ..serializers import NotificacionSerializer, AuditoriaSerializer
from ..permissions import EsAdminOSuperior


class NotificacionViewSet(viewsets.ModelViewSet):
    serializer_class = NotificacionSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        return Notificacion.objects.filter(destinatario=self.request.user).order_by(
            "-fecha_creacion"
        )

    @action(detail=False, methods=["get"])
    def no_leidas(self, request):
        count = self.get_queryset().filter(leida=False).count()
        return Response({"count": count})

    @action(detail=True, methods=["patch"])
    def marcar_leida(self, request, pk=None):
        notif = self.get_object()
        notif.leida = True
        notif.save(update_fields=["leida"])
        return Response(NotificacionSerializer(notif).data)

    @action(detail=False, methods=["post"])
    def marcar_todas_leidas(self, request):
        self.get_queryset().filter(leida=False).update(leida=True)
        return Response({"detail": "Todas marcadas como leídas"})

    def create(self, request, *args, **kwargs):
        return Response(
            {"detail": "No permitido"}, status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def update(self, request, *args, **kwargs):
        # Permitir PATCH leida
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": "No permitido"}, status=status.HTTP_405_METHOD_NOT_ALLOWED
        )


class AuditoriaViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditoriaSerializer
    permission_classes = [IsAuthenticated, EsAdminOSuperior]

    def get_queryset(self):
        return LogEntry.objects.select_related("content_type", "user").order_by(
            "-action_time"
        )[:500]
