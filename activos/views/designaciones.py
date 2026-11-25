from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_simplejwt.authentication import JWTAuthentication
from ..models import Designacion, Regional, Gerencia, Cargo, Activo, User
from ..serializers import DesignacionSerializer
from ..permissions import PuedeDesignarActivos
from ..utils_seguridad import exigir_turnstile
from .auditoria import AuditoriaApiMixin
from django.db.models import F
from django.contrib.admin.models import CHANGE

class DesignacionViewSet(AuditoriaApiMixin, viewsets.ModelViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [PuedeDesignarActivos]
    
    queryset = Designacion.objects.select_related(
        'activo', 'usuario', 'regional', 'gerencia', 'cargo', 'ubicacion'
    ).all().order_by('-fecha_inicio')
    
    serializer_class = DesignacionSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['activo__codigo_tamep', 'usuario__username', 'tipo', 'esta_activa']
    search_fields = ['activo__codigo_tamep', 'usuario__first_name', 'usuario__last_name']

    @transaction.atomic
    def perform_create(self, serializer):
        """
        Garantía de Robustez: El guardado de la designación y la actualización 
        del activo ocurren o no ocurren juntos (All or Nothing).
        """
        super().perform_create(serializer)  # serializer.save() + auditoría
        designacion = serializer.instance
        activo = designacion.activo
        activo.situacion_activo = 'Asignado'
        activo.save()

    def create(self, request, *args, **kwargs):
        # Turnstile antes de cualquier escritura (POST /api/designaciones/).
        guard = exigir_turnstile(request)
        if guard:
            return guard
        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def estructura_completa(self, request):
        """
        ENDPOINT MAESTRO: Devuelve todo el personal con su jerarquía 
        en una sola petición para alimentar los filtros de Vue.
        """
        personal = User.objects.filter(is_active=True).annotate(
            regional_id=F('perfil__regional_id'),
            regional_nombre=F('perfil__regional__nombre'),
            gerencia_id=F('perfil__gerencia_id'),
            gerencia_nombre=F('perfil__gerencia__nombre'),
            cargo_id=F('perfil__cargo_id'),
            cargo_nombre=F('perfil__cargo__nombre')
        ).values(
            'id', 'first_name', 'last_name', 'username',
            'regional_id', 'regional_nombre',
            'gerencia_id', 'gerencia_nombre',
            'cargo_id', 'cargo_nombre'
        )
        
        data = []
        for p in personal:
            data.append({
                "id": p['id'],
                "nombre_completo": f"{p['first_name']} {p['last_name']}".strip() or p['username'],
                "regional_id": p['regional_id'],
                "regional_nombre": p['regional_nombre'],
                "gerencia_id": p['gerencia_id'],
                "gerencia_nombre": p['gerencia_nombre'],
                "cargo_id": p['cargo_id'],
                "cargo_nombre": p['cargo_nombre'],
            })
        return Response(data)

    @action(detail=True, methods=['post'])
    def devolver(self, request, pk=None):
        """
        Cierre administrativo de la custodia.
        """
        designacion = self.get_object()
        if not designacion.esta_activa:
            return Response({"detail": "Designación ya cerrada."}, status=400)

        with transaction.atomic():
            designacion.esta_activa = False
            designacion.fecha_fin_real = timezone.now()
            designacion.save()
            
            # Liberamos el activo
            activo = designacion.activo
            activo.situacion_activo = 'Disponible'
            activo.save()

        # Acción custom: no pasa por perform_update, así que la auditoría es
        # explícita. Detalle de dominio: qué cambió y por qué.
        self.registrar_auditoria(
            CHANGE,
            designacion,
            {"esta_activa": False},
            detalle="Cierre administrativo de custodia (devolver)",
        )

        return Response({"detail": "Activo liberado y disponible para nueva asignación."})
