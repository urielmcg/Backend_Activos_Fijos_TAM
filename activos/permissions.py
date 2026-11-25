from rest_framework.permissions import BasePermission

ROLES_ADMIN = ('admin_informatico', 'admin_principal')
ROLES_ADMIN_REGIONAL = ('admin_informatico', 'admin_principal', 'admin_regional')
ROLES_PUEDEN_DESIGNAR = ('admin_informatico', 'admin_principal', 'admin_regional', 'consultor')
ROLES_PUEDEN_CREAR_ACTIVOS = ('admin_informatico', 'admin_principal', 'admin_regional', 'consultor')

# Campos del payload que solo admin_informatico (o superusuario) puede enviar
# a /api/users/: permiten escalar privilegios, cambiar el rol de la cuenta
# o tomarla (password es write-only y permite takeover de cualquier cuenta).
CAMPOS_PRIVILEGIADOS_USUARIO = ('rol', 'is_staff', 'is_superuser', 'password')

# Métodos que pueden llevar cuerpo y por lo tanto estos campos.
METODOS_CON_CUERPO = ('POST', 'PUT', 'PATCH')


def obtener_rol(user):
    """Obtiene el rol del usuario desde su perfil."""
    if hasattr(user, 'perfil'):
        return user.perfil.rol
    return 'usuario'


class EsAdminInformatico(BasePermission):
    """Solo permite acceso al administrador informático."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and obtener_rol(request.user) == 'admin_informatico'


class EsAdminOSuperior(BasePermission):
    """Permite acceso a admin_informatico y admin_principal."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and obtener_rol(request.user) in ROLES_ADMIN


class EsAdminRegionalOSuperior(BasePermission):
    """Permite acceso a admin_informatico, admin_principal y admin_regional."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and obtener_rol(request.user) in ROLES_ADMIN_REGIONAL


class PuedeGestionarActivos(BasePermission):
    """
    Permisos para gestión de activos:
    - GET: todos los autenticados
    - POST: admins + consultor
    - PUT/PATCH/DELETE: solo admins (informatico, principal, regional)
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        rol = obtener_rol(request.user)
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        if request.method == 'POST':
            return rol in ROLES_PUEDEN_CREAR_ACTIVOS
        # PUT, PATCH, DELETE
        return rol in ROLES_ADMIN_REGIONAL


class PuedeDesignarActivos(BasePermission):
    """Permite designar activos: admins + consultor."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and obtener_rol(request.user) in ROLES_PUEDEN_DESIGNAR


class PuedeAccederModuloIA(BasePermission):
    """Solo admin_informatico puede acceder al módulo de IA."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and obtener_rol(request.user) == 'admin_informatico'


class PuedeGestionarUsuarios(BasePermission):
    """
    Permisos para gestión de usuarios:
    - admin_informatico (o superusuario): acceso completo
    - admin_principal: solo listar y activar/desactivar (PATCH is_active)
    - admin_principal: prohibido enviar campos privilegiados en el payload
      (rol, is_staff, is_superuser, password); solo admin_informatico o
      superusuario. Si el payload trae cualquiera de esos campos, se responde 403.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        rol = obtener_rol(request.user)
        if rol == 'admin_informatico' or request.user.is_superuser:
            return True
        if rol != 'admin_principal':
            return False
        if request.method not in ('GET', 'PATCH', 'HEAD', 'OPTIONS'):
            return False
        if request.method in METODOS_CON_CUERPO and self.envia_campos_privilegiados(request):
            return False
        return True

    @staticmethod
    def envia_campos_privilegiados(request):
        """True si el payload contiene campos privilegiados (o no se puede inspeccionar)."""
        datos = request.data
        # QueryDict (form-data) es subclase de dict; cualquier otra forma
        # (JSON inválido, lista, etc.) se rechaza por seguridad.
        if not isinstance(datos, dict):
            return True
        return any(campo in datos for campo in CAMPOS_PRIVILEGIADOS_USUARIO)
