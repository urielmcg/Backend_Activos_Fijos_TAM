from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.viewsets import ModelViewSet
from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth.models import User
from ..serializers import UserProfileSerializer, UserAdminSerializer
from ..models import PerfilUsuario
from ..permissions import PuedeGestionarUsuarios
from ..utils_seguridad import exigir_turnstile
from .auditoria import AuditoriaApiMixin


class UserViewSet(AuditoriaApiMixin, ModelViewSet):
    """Gestión de usuarios - admin_informatico: completo, admin_principal: activar/desactivar."""
    # Sin paginación: UsuariosRegistrados.vue asigna response.data directo y
    # pagina en el cliente con filter/slice (líneas 73, 146-170). Deuda del frontend.
    pagination_class = None
    queryset = User.objects.select_related('perfil', 'perfil__cargo', 'perfil__regional', 'perfil__gerencia').order_by('-date_joined')
    serializer_class = UserAdminSerializer
    permission_classes = [PuedeGestionarUsuarios]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['is_active', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name']

    def create(self, request, *args, **kwargs):
        guard = exigir_turnstile(request)
        if guard:
            return guard
        return super().create(request, *args, **kwargs)

class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        user = request.user
        data = request.data
        
        serializer = UserProfileSerializer(user, data=data, partial=True)
        
        if serializer.is_valid():
            # --- 1. ACTUALIZACIÓN DE USERNAME ---
            new_username = data.get('username')
            if new_username and new_username != user.username:
                if User.objects.filter(username=new_username).exclude(id=user.id).exists():
                    return Response({"detail": "Este nombre de usuario ya está en uso."}, 
                                    status=status.HTTP_400_BAD_REQUEST)
                user.username = new_username

            # --- 2. ACTUALIZACIÓN DE CAMPOS DE USER ---
            user.first_name = data.get('first_name', user.first_name)
            user.last_name = data.get('last_name', user.last_name)
            user.email = data.get('email', user.email)
            
            password = data.get('password')
            if password:
                user.set_password(password)
            user.save()

            # --- 3. ACTUALIZACIÓN DE CAMPOS DE PERFIL (CI, EXTENSIÓN, TELÉFONO) ---

            perfil, created = PerfilUsuario.objects.get_or_create(user=user)
            
            if 'ci' in data:
                perfil.ci = data.get('ci')
            
            if 'extension' in data:
                perfil.extension = data.get('extension')
                
            if 'telefono' in data:
                perfil.telefono = data.get('telefono')
            
            perfil.save() 
                
            return Response(UserProfileSerializer(user).data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)