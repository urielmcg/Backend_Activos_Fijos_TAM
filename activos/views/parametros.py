from ..models import GrupoContable, TipoActivo, Ubicacion
from django.contrib.auth.models import User
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from ..serializers import GrupoContableSerializer, TipoActivoSerializer, UbicacionSerializer

permission_classes = [IsAuthenticated]

class ParametrosActivoViewSet(viewsets.ViewSet):
    def list(self, request):
        grupos = GrupoContable.objects.all()
        ubicaciones = Ubicacion.objects.all()
        
        return Response({
            "grupos": GrupoContableSerializer(grupos, many=True).data,
            "ubicaciones": UbicacionSerializer(ubicaciones, many=True).data
        })

    @action(detail=False, methods=['get'], url_path='tipos/(?P<grupo_id>\d+)')
    def tipos_por_grupo(self, request, grupo_id=None):
        tipos = TipoActivo.objects.filter(grupo_contable_id=grupo_id)
        serializer = TipoActivoSerializer(tipos, many=True)
        return Response(serializer.data)
    @action(detail=False, methods=['get'])
    def personal(self, request):
        usuarios = User.objects.filter(is_active=True).select_related(
            'perfil__regional', 
            'perfil__gerencia', 
            'perfil__cargo'
    )
    
        data = []
        for u in usuarios:
            p = getattr(u, 'perfil', None)
            if p and p.regional and p.gerencia and p.cargo:
                data.append({
                    'id': u.id,
                    'nombre_completo': f"{u.first_name} {u.last_name}".strip() or u.username,
                    'regional_id': p.regional.id,
                    'regional_nombre': p.regional.nombre,
                    'gerencia_id': p.gerencia.id,
                    'gerencia_nombre': p.gerencia.nombre,
                    'cargo_id': p.cargo.id,
                    'cargo_nombre': p.cargo.nombre
                })
        return Response(data)
