from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from ..models import Activo, Regional, GrupoContable, TipoActivo, Gerencia, Cargo
from ..serializers import ActivoReporteSerializer, RegionalSerializer, GrupoContableSerializer, TipoActivoSerializer, GerenciaSerializer, CargoSerializer
from ..permissions import obtener_rol


class OrderingConAlias(filters.OrderingFilter):
    """
    OrderingFilter que traduce nombres amigables a rutas del ORM.

    El frontend pide `?ordering=-probabilidad_falla` (ModuloPredictivo.vue),
    pero ese campo vive en la relación OneToOne `prediccion`
    (MetricaPredictiva.probabilidad_falla). DRF valida el nombre contra
    `view.ordering_fields` y luego hace `order_by()` con el literal, así que
    sin este puente terminaría en `FieldError` en vez de ordenar.

    Los alias se declaran en `view.ORDERING_ALIASES`.
    """

    def get_ordering(self, request, queryset, view):
        aliases = getattr(view, "ORDERING_ALIASES", None) or {}
        ordering = super().get_ordering(request, queryset, view) or []
        traducido = []
        for campo in ordering:
            invertido = campo.startswith("-")
            base = campo[1:] if invertido else campo
            ruta = aliases.get(base, base)
            traducido.append(f"{'-' if invertido else ''}{ruta}")
        return traducido

class ActivoReporteViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Vista de gestión avanzada para TAMEP.
    Optimiza la relación jerárquica: Grupo Contable -> Tipo de Activo.
    """
    permission_classes = [IsAuthenticated]
    # Sin paginación: ManagementActivos.vue asigna response.data directo y
    # pagina en el cliente con slice/length (líneas 63, 77-85). Los demás
    # consumidores (Reportes, Monitoreo, ModuloPredictivo) leen
    # `results || data` y toleran ambos formatos. Deuda del frontend.
    pagination_class = None
    queryset = Activo.objects.select_related(
        'grupo_contable_seleccionado',  
        'tipo_activo',                  
        'tipo_activo__grupo_contable',  
        'ubicacion_actual__regional',    
        'prediccion'                    
    ).prefetch_related('designaciones__usuario', 
        'transferencia_set__emisor', 
        'transferencia_set__receptor',
        'baja_registro').all()
    
    serializer_class = ActivoReporteSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingConAlias]
    
    # --- FILTROS CONFIGURADOS SEGÚN TU MODELO ---
    filterset_fields = {
        'grupo_contable_seleccionado': ['exact'], 
        'tipo_activo': ['exact'],
        'ubicacion_actual__regional': ['exact'],
        'ubicacion_actual': ['exact'],
        'situacion_activo': ['exact'], 
        'estado_actual': ['exact'],    

        'perfil_uso': ['exact'],
    }
    search_fields = [
        'codigo_tamep', 
        'nombre_especifico', 
        'serie', 
        'descripcion', 
        'codigo_tab'
    ]
    
    # La probabilidad de falla y la salud fuzzy viven en MetricaPredictiva
    # (OneToOne de Activo, related_name="prediccion"), no en el propio Activo.
    # El frontend pide `?ordering=-probabilidad_falla` (ModuloPredictivo.vue
    # L16): OrderingConAlias traduce ese nombre amigable a la ruta del ORM.
    ORDERING_ALIASES = {
        'probabilidad_falla': 'prediccion__probabilidad_falla',
        'indice_salud_fuzzy': 'prediccion__indice_salud_fuzzy',
    }

    ordering_fields = [
        'fecha_adquisicion',
        'costo',
        'horas_uso_actual',
        # Nombres amigables que consume el frontend.
        'probabilidad_falla',
        'indice_salud_fuzzy',
        # Y la ruta ORM explícita, por si un cliente la usa tal cual.
        'prediccion__probabilidad_falla',
        'prediccion__indice_salud_fuzzy',
    ]

    def get_queryset(self):
        qs = super().get_queryset()
        rol = obtener_rol(self.request.user)
        if rol == 'admin_regional' and hasattr(self.request.user, 'perfil'):
            regional = self.request.user.perfil.regional
            if regional:
                qs = qs.filter(ubicacion_actual__regional=regional)
        return qs

class RegionalViewSet(viewsets.ReadOnlyModelViewSet):
    # Dropdown: UsuariosRegistrados.vue y ManagementActivos.vue consumen la
    # respuesta como array plano (sin .results). Sin paginación.
    pagination_class = None
    queryset = Regional.objects.all()
    serializer_class = RegionalSerializer

class GrupoContableViewSet(viewsets.ReadOnlyModelViewSet):
    # Dropdown: ManagementActivos.vue consume la respuesta como array plano.
    pagination_class = None
    queryset = GrupoContable.objects.all()
    serializer_class = GrupoContableSerializer

class TipoActivoViewSet(viewsets.ReadOnlyModelViewSet):
    # Dropdown: ManagementActivos.vue consume la respuesta como array plano.
    pagination_class = None
    queryset = TipoActivo.objects.all()
    serializer_class = TipoActivoSerializer
    filterset_fields = ['grupo_contable']

class GerenciaViewSet(viewsets.ReadOnlyModelViewSet):
    # Dropdown en cascada: UsuariosRegistrados.vue (cargarGerencias) usa
    # la respuesta como array plano. Sin paginación.
    pagination_class = None
    queryset = Gerencia.objects.all()
    serializer_class = GerenciaSerializer
    filterset_fields = ['regional']

class CargoViewSet(viewsets.ReadOnlyModelViewSet):
    # Dropdown en cascada: UsuariosRegistrados.vue (cargarCargos) usa la
    # respuesta como array plano. Sin paginación.
    pagination_class = None
    queryset = Cargo.objects.all()
    serializer_class = CargoSerializer
    filterset_fields = ['gerencia']