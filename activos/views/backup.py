"""Respaldo completo de la base de datos (mysqldump) descargable como SQL."""

import logging
import os
import shutil
import subprocess
from datetime import datetime

from django.conf import settings
from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from ..permissions import EsAdminOSuperior

logger = logging.getLogger(__name__)

# Rutas fijas de Windows por si el PATH no incluye a mysqldump.
RUTAS_MYSQLDUMP_WINDOWS = (
    r"C:\Program Files\MySQL\MySQL Server 5.7\bin\mysqldump.exe",
    r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe",
    r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe",
    r"C:\Program Files (x86)\MySQL\MySQL Server 5.7\bin\mysqldump.exe",
    r"C:\xampp\mysql\bin\mysqldump.exe",
)

MENSAJE_SIN_MYSQLDUMP = (
    "No se encontró el ejecutable 'mysqldump'. Instale MySQL o defina la "
    "variable de entorno MYSQLDUMP_PATH con la ruta completa al binario."
)
MENSAJE_SIN_PERMISO = (
    "No tiene permisos para generar respaldos. Se requiere rol de administrador."
)


def encontrar_mysqldump():
    """Ubica mysqldump: MYSQLDUMP_PATH → PATH → rutas conocidas de Windows."""
    ruta_env = os.environ.get("MYSQLDUMP_PATH")
    if ruta_env and os.path.isfile(ruta_env):
        return ruta_env
    ruta_path = shutil.which("mysqldump")
    if ruta_path:
        return ruta_path
    for candidata in RUTAS_MYSQLDUMP_WINDOWS:
        if os.path.isfile(candidata):
            return candidata
    return None


def ejecutar_mysqldump(binario, credenciales, con_no_tablespaces=True):
    """Ejecuta mysqldump y retorna (código de salida, dump en bytes, error).

    La contraseña viaja en la variable de entorno MYSQL_PWD para que nunca
    aparezca en la lista de argumentos (visible en el monitor de procesos).
    """
    args = [binario]
    if con_no_tablespaces:
        # --no-tablespaces evita exigir el privilegio PROCESS; los servidores
        # antiguos no lo conocen y el llamador reintenta sin él.
        args.append("--no-tablespaces")
    args += [
        f"--host={credenciales['HOST']}",
        f"--port={credenciales['PORT']}",
        f"--user={credenciales['USER']}",
        "--single-transaction",
        "--routines",
        "--triggers",
        # Sin --result-file=-: en MySQL 5.7 esa opción crea un archivo
        # literal llamado "-" y deja stdout vacío; se captura stdout directo.
        credenciales["NAME"],
    ]

    entorno = os.environ.copy()
    entorno["MYSQL_PWD"] = credenciales.get("PASSWORD") or ""

    # shell=False (lista de argumentos): nunca interpretar la línea de comando.
    resultado = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=entorno,
        shell=False,
    )
    error = (resultado.stderr or b"").decode("utf-8", errors="replace")
    return resultado.returncode, resultado.stdout, error


class BackupAPIView(APIView):
    """GET /api/backup/: vuelca la base de datos y la devuelve como archivo."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, EsAdminOSuperior]

    def permission_denied(self, request, message=None, code=None):
        """403 con mensaje en español (el mensaje por defecto de DRF es inglés)."""
        if request.authenticators and not request.successful_authenticator:
            # Sin token válido: DRF responde 401 con cabecera WWW-Authenticate.
            super().permission_denied(request, message=message, code=code)
            return
        raise PermissionDenied(MENSAJE_SIN_PERMISO)

    def get(self, request):
        try:
            binario = encontrar_mysqldump()
            if not binario:
                return Response(
                    {"detail": MENSAJE_SIN_MYSQLDUMP},
                    status=status.HTTP_501_NOT_IMPLEMENTED,
                )

            base = settings.DATABASES["default"]
            codigo, dump, error = ejecutar_mysqldump(binario, base)

            # Versiones viejas de MySQL/MariaDB no reconocen --no-tablespaces:
            # un único reintento sin esa opción.
            if (
                codigo != 0
                and "unknown" in error.lower()
                and "no-tablespaces" in error.lower()
            ):
                codigo, dump, error = ejecutar_mysqldump(
                    binario, base, con_no_tablespaces=False
                )

            if codigo != 0:
                detalle = error.strip() or "error desconocido al ejecutar mysqldump"
                logger.warning("mysqldump falló (código %s): %s", codigo, detalle)
                return Response(
                    {"detail": f"No se pudo generar el respaldo: {detalle}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            nombre_archivo = (
                f"backup_{base['NAME']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
            )
            respuesta = HttpResponse(dump, content_type="application/sql")
            respuesta["Content-Disposition"] = (
                f'attachment; filename="{nombre_archivo}"'
            )
            return respuesta
        except Exception:
            # Nunca dejar que un traceback llegue al cliente.
            logger.exception("Error inesperado al generar el respaldo")
            return Response(
                {"detail": "Error interno al generar el respaldo de la base de datos."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
