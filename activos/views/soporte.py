from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q

from ..models import SolicitudServicio, Intervencion, Activo
from ..serializers import SolicitudServicioSerializer, IntervencionSerializer
from ..permissions import EsAdminRegionalOSuperior, obtener_rol
from ..utils_seguridad import exigir_turnstile
from .auditoria import AuditoriaApiMixin

class SolicitudServicioViewSet(AuditoriaApiMixin, viewsets.ModelViewSet):
    """
    Gestiona los tickets de soporte.
    - Los usuarios normales solo ven SUS solicitudes.
    - Los técnicos ven TODAS las solicitudes de su área.
    """
    queryset = SolicitudServicio.objects.select_related('activo', 'solicitante').all().order_by('-fecha_solicitud')
    serializer_class = SolicitudServicioSerializer
    permission_classes = [IsAuthenticated]
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['tipo_solicitud', 'severidad']
    search_fields = ['activo__codigo_tamep', 'descripcion_problema']

    def get_queryset(self):
        """
        FILTRO DE SEGURIDAD POR ROL:
        - admin_informatico/admin_principal: ven todo
        - admin_regional: solo solicitudes de activos de su regional
        - usuario/consultor: solo lo que ellos reportaron
        """
        user = self.request.user
        queryset = super().get_queryset()
        rol = obtener_rol(user)

        if rol in ('admin_informatico', 'admin_principal'):
            return queryset

        if rol == 'admin_regional' and hasattr(user, 'perfil') and user.perfil.regional:
            return queryset.filter(activo__ubicacion_actual__regional=user.perfil.regional)

        return queryset.filter(solicitante=user)

    def perform_create(self, serializer):
        # super() == AuditoriaApiMixin: serializer.save(solicitante=...) + LogEntry
        super().perform_create(serializer, solicitante=self.request.user)

    def create(self, request, *args, **kwargs):
        # Turnstile antes de cualquier escritura (POST /api/solicitudes/).
        guard = exigir_turnstile(request)
        if guard:
            return guard
        return super().create(request, *args, **kwargs)


class IntervencionViewSet(AuditoriaApiMixin, viewsets.ModelViewSet):
    """
    Registro de trabajos técnicos.
    ALERTA DE TESIS: Cada vez que se guarda aquí, se disparan los cálculos de IA
    (MTBF, MTTR) definidos en el modelo.
    """
    queryset = Intervencion.objects.select_related(
        'activo', 'tecnico', 'solicitud'
    ).all().order_by('-fecha_fin')
    
    serializer_class = IntervencionSerializer
    permission_classes = [EsAdminRegionalOSuperior]
    
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['tipo_mantenimiento', 'tecnico__username', 'activo__codigo_tamep']

    def create(self, request, *args, **kwargs):
        guard = exigir_turnstile(request)
        if guard:
            return guard
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {"detail": f"Error registrando intervención: {str(e)}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    def perform_create(self, serializer):
        # super() == AuditoriaApiMixin: serializer.save(tecnico=...) + LogEntry
        super().perform_create(serializer, tecnico=self.request.user)

    @action(detail=False, methods=['get'], url_path='historial/(?P<activo_id>\d+)')
    def historial_tecnico(self, request, activo_id=None):
        """
        Devuelve la hoja de vida técnica de un activo específico
        Útil para que el técnico vea qué se le hizo antes.
        """
        intervenciones = Intervencion.objects.filter(activo_id=activo_id).order_by('-fecha_fin')
        serializer = self.get_serializer(intervenciones, many=True)
        return Response(serializer.data)