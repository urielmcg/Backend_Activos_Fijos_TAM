from rest_framework import viewsets, status, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from django.contrib.admin.models import ADDITION
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404, render
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.db import transaction
from datetime import date

# Importamos todos los modelos necesarios
from ..models import (
    Activo, Designacion, Transferencia, Intervencion, 
    User, MetricaPredictiva, SolicitudServicio,
    GrupoContable, TipoActivo, Ubicacion
)
from ..serializers import ActivoSerializer, GrupoContableSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from ..permissions import PuedeGestionarActivos, obtener_rol
from ..utils_seguridad import exigir_turnstile
from .auditoria import AuditoriaApiMixin
from django.utils import timezone
from datetime import timedelta

class ActivoViewSet(AuditoriaApiMixin, viewsets.ModelViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [PuedeGestionarActivos]
    # Sin paginación: AsingActivos.vue consume /api/activos/?search= como
    # array plano (data.length / data[0], líneas 92-95) y una página paginada
    # rompería la búsqueda de asignación en silencio. Deuda del frontend.
    pagination_class = None

    queryset = Activo.objects.select_related(
        'tipo_activo', 'tipo_activo__grupo_contable',
        'ubicacion_actual', 'ubicacion_actual__regional', 'prediccion'
    ).all().order_by('-id')

    serializer_class = ActivoSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['situacion_activo', 'estado_actual', 'ubicacion_actual', 'codigo_tamep', 'codigo_tab']
    search_fields = ['codigo_tamep', 'serie', 'nombre_especifico', 'codigo_tab']

    def get_queryset(self):
        qs = super().get_queryset()
        rol = obtener_rol(self.request.user)
        if rol == 'admin_regional' and hasattr(self.request.user, 'perfil'):
            regional = self.request.user.perfil.regional
            if regional:
                qs = qs.filter(ubicacion_actual__regional=regional)
        return qs

    # --- ENDPOINTS PARA EL FORMULARIO (URLS CORREGIDAS) ---

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def parametros_iniciales(self, request):
        """URL: /api/activos/parametros_iniciales/"""
        grupos_qs = GrupoContable.objects.all()
        grupos_data = GrupoContableSerializer(grupos_qs, many=True).data
        ubics = Ubicacion.objects.select_related('regional').all()
        ubicaciones_data = [{"id": u.id, "nombre_sala": f"{u.nombre_sala} ({u.regional.nombre})"} for u in ubics]
    
        return Response({
            "grupos": grupos_data, # Ahora lleva ID, nombre, vida_util y tiene_mantenimiento_predictivo
            "ubicaciones": ubicaciones_data
        })

    @action(detail=False, methods=['get'])
    def personal_list(self, request):
        """URL: /api/activos/personal_list/"""
        # Aquí obtenemos la estructura para el modal de asignación
        from django.db.models import F
        # Asumiendo que tienes un método o consulta que trae esta estructura
        # Si prefieres, usa la lógica que ya tenías en 'estructura_completa'
        personal = User.objects.filter(perfil__isnull=False).values(
            'id', 
            nombre_completo=F('first_name'), # O el campo que uses
            regional_id=F('perfil__regional_id'),
            regional_nombre=F('perfil__regional__nombre'),
            gerencia_id=F('perfil__gerencia_id'),
            gerencia_nombre=F('perfil__gerencia__nombre'),
            cargo_id=F('perfil__cargo_id'),
            cargo_nombre=F('perfil__cargo__nombre')
        )
        return Response(list(personal))

    @action(detail=False, methods=['get'], url_path='tipos_por_grupo/(?P<grupo_id>\d+)')
    def tipos_por_grupo(self, request, grupo_id=None):
        tipos = TipoActivo.objects.filter(grupo_contable_id=grupo_id).values('id', 'nombre')
        return Response(list(tipos))

    @action(detail=False, methods=['get'])
    def grupos_contables(self, request):
        """URL: /api/activos/grupos_contables/"""
        grupos = GrupoContable.objects.all().values('id', 'nombre', 'vida_util_anos')
        return Response(list(grupos))


    @action(detail=False, methods=['get'])
    def ubicaciones_list(self, request):
        """URL: /api/activos/ubicaciones_list/"""
        ubics = Ubicacion.objects.select_related('regional').all()
        data = [{
            "id": u.id,
            "nombre_sala": u.nombre_sala,
            "regional_nombre": u.regional.nombre
        } for u in ubics]
        return Response(data)

    # --- MÉTODOS DE LÓGICA DE NEGOCIO ---

    def create(self, request, *args, **kwargs):
        guard = exigir_turnstile(request)
        if guard:
            return guard
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                serializer.save(registrado_por=request.user)
                # Este create no pasa por perform_create (inyecta
                # registrado_por), así que la auditoría se registra acá.
                self.registrar_auditoria(
                    ADDITION, serializer.instance, serializer.validated_data
                )
                headers = self.get_success_headers(serializer.data)
                return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except Exception as e:
            return Response(
                {"detail": f"Error interno al crear activo: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        rol = obtener_rol(request.user)

        if rol == 'consultor':
            # Solo puede editar activos que el mismo registro
            if instance.registrado_por != request.user:
                return Response(
                    {"detail": "Solo puede editar activos que usted haya registrado."},
                    status=status.HTTP_403_FORBIDDEN
                )
            # Solo dentro de los 30 minutos posteriores al registro
            if instance.fecha_registro and timezone.now() - instance.fecha_registro > timedelta(minutes=30):
                return Response(
                    {"detail": "El periodo de edición de 30 minutos ha expirado."},
                    status=status.HTTP_403_FORBIDDEN
                )
            # No puede modificar codigos
            if 'codigo_tamep' in request.data or 'codigo_tab' in request.data:
                return Response(
                    {"detail": "No tiene permisos para modificar los códigos de identificación."},
                    status=status.HTTP_403_FORBIDDEN
                )

        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    def historial(self, request, pk=None):
        activo = self.get_object()
        historial = activo.historialestadoactivo_set.all().order_by('-fecha').values()
        return Response(list(historial))

    @action(detail=False, methods=['get'])
    def resumen_ia(self, request):
        total = Activo.objects.count()
        criticos = MetricaPredictiva.objects.filter(probabilidad_falla__gt=80).count()
        salud_baja = MetricaPredictiva.objects.filter(indice_salud_fuzzy__lt=40).count()
        
        return Response({
            "total_activos": total,
            "riesgo_critico": criticos,
            "salud_degradada": salud_baja,
            "mantenimientos_pendientes": SolicitudServicio.objects.filter(intervenciones__isnull=True).count()
        })

def detalle_activo_qr(request, codigo):
    # 1. Traemos el Activo con todas sus relaciones
    activo = get_object_or_404(
        Activo.objects.select_related(
            'tipo_activo__grupo_contable', 
            'ubicacion_actual__regional',
            'ubicacion_base__regional',
            'prediccion',                 
        ), 
        codigo_tamep=codigo
    )

    # 2. CONSULTA ROBUSTA: Intentamos traer la activa, si no, la más reciente
    designacion_actual = Designacion.objects.filter(
        activo=activo, 
        esta_activa=True
    ).select_related('usuario', 'cargo', 'gerencia', 'ubicacion').first()

    # Si el activo está "Asignado" pero no hay una designación con el check 'True'
    # traemos la última cronológicamente (Igual que hace el historial del Admin)
    if not designacion_actual and activo.situacion_activo == 'Asignado':
        designacion_actual = Designacion.objects.filter(
            activo=activo
        ).select_related('usuario', 'cargo', 'gerencia', 'ubicacion').order_by('-fecha_inicio').first()

    # 3. Traemos las transferencias (asegúrate de incluir gerencias para la trazabilidad)
    transferencias = Transferencia.objects.filter(activo=activo).select_related(
        'emisor', 'receptor', 'ger_emisor', 'ger_receptor'
    ).order_by('-fecha')[:5]

    context = {
        'activo': activo, 
        'designacion': designacion_actual, 
        'transferencias': transferencias
    }
    
    return render(request, 'activos/detalle_qr.html', context)