"""
Tests de las reglas de throttling (Tarea 1) y paginación (Tarea 2).

- Throttling: ScopedRateThrottle con rates por scope en los endpoints de
  autenticación (login, register, refresh) y mensaje de error en español.
- Paginación: las listas/tablas responden paginadas (Página 2 y tope de
  page_size); los endpoints de dropdown/estructura quedan sin paginación
  porque el frontend los consume como array plano.

Corren con el shim SQLite:
    DJANGO_SETTINGS_MODULE=djshim PYTHONPATH=/tmp/opencode python manage.py test
"""
import shutil
import tempfile

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from .models import (
    Activo,
    GrupoContable,
    Notificacion,
    PerfilUsuario,
    Regional,
    SolicitudServicio,
    TipoActivo,
    Ubicacion,
)

# Los QR se generan en Activo.save(); redirigimos MEDIA_ROOT a un temporal
# para no escribir dentro del repositorio durante los tests.
MEDIA_TEMP = tempfile.mkdtemp(prefix="siaem-test-media-pag-")


def tearDownModule():
    shutil.rmtree(MEDIA_TEMP, ignore_errors=True)


def rest_framework_con_rates(rates):
    """Copia la configuración real de DRF y reemplaza solo las tasas."""
    config = dict(settings.REST_FRAMEWORK)
    config["DEFAULT_THROTTLE_RATES"] = rates
    return config


# Tasas bajas para provocar el 429 en pocas peticiones de test.
RATES_PRUEBA = {
    "login": "2/min",
    "register": "2/min",
    "refresh": "2/min",
}


@override_settings(REST_FRAMEWORK=rest_framework_con_rates(RATES_PRUEBA))
class ThrottlingAuthTests(TestCase):
    """Tarea 1: login, register y refresh limitados por IP."""

    def setUp(self):
        # GOTCHA de DRF: SimpleRateThrottle.THROTTLE_RATES se enlaza al dict
        # de REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] EN LA DEFINICIÓN DE LA
        # CLASE (rest_framework/throttling.py). override_settings recarga
        # api_settings pero NO reenlaza ese atributo de clase, así que el
        # rate real seguiría siendo el de producción (20/min) y el 429 nunca
        # llegaría. Por eso cambiamos el atributo directamente y lo
        # restauramos en tearDown.
        self._rates_originales = SimpleRateThrottle.THROTTLE_RATES
        SimpleRateThrottle.THROTTLE_RATES = RATES_PRUEBA
        # El throttle cachea por IP en el cache por defecto: limpiamos para
        # que cada test empiece con el contador en cero.
        cache.clear()
        self.client = APIClient()

    def tearDown(self):
        SimpleRateThrottle.THROTTLE_RATES = self._rates_originales

    def test_login_responde_429_en_espanol_al_exceder_el_limite(self):
        credenciales = {"username": "fantasma", "password": "incorrecta"}

        for _ in range(2):
            respuesta = self.client.post("/api/login/", credenciales, format="json")
            self.assertEqual(respuesta.status_code, 401, respuesta.content)

        bloqueada = self.client.post("/api/login/", credenciales, format="json")

        self.assertEqual(bloqueada.status_code, 429, bloqueada.content)
        self.assertIn("Demasiadas solicitudes", bloqueada.data["error"])

    def test_register_responde_429_en_espanol_al_exceder_el_limite(self):
        for _ in range(2):
            # Payload inválido: el throttle corre antes de validar el serializer.
            respuesta = self.client.post("/api/register/", {}, format="json")
            self.assertEqual(respuesta.status_code, 400, respuesta.content)

        bloqueada = self.client.post("/api/register/", {}, format="json")

        self.assertEqual(bloqueada.status_code, 429, bloqueada.content)
        self.assertIn("Demasiadas solicitudes", bloqueada.data["error"])

    def test_refresh_responde_429_en_espanol_al_exceder_el_limite(self):
        for _ in range(2):
            respuesta = self.client.post(
                "/api/token/refresh/", {"refresh": "invalido"}, format="json"
            )
            self.assertEqual(respuesta.status_code, 401, respuesta.content)

        bloqueada = self.client.post(
            "/api/token/refresh/", {"refresh": "invalido"}, format="json"
        )

        self.assertEqual(bloqueada.status_code, 429, bloqueada.content)
        self.assertIn("Demasiadas solicitudes", bloqueada.data["error"])

    def test_endpoints_de_aplicacion_no_estan_throttled_globalmente(self):
        # El throttling es solo por scope: /api/me/ no debe verse afectado.
        usuario = User.objects.create_user(username="normal", password="x")
        self.client.force_authenticate(user=usuario)

        for _ in range(5):
            respuesta = self.client.get("/api/me/")
            self.assertEqual(respuesta.status_code, 200, respuesta.content)


class BasePaginacionPrueba(TestCase):
    """Usuario normal y admin informático reutilizables."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="usuario_pag",
            password="x",
            first_name="Usuario",
            last_name="Paginacion",
        )
        cls.admin = User.objects.create_user(
            username="admin_pag",
            password="x",
            is_staff=True,
            first_name="Admin",
            last_name="Paginacion",
        )
        perfil, _ = PerfilUsuario.objects.get_or_create(user=cls.admin)
        perfil.rol = "admin_informatico"
        perfil.save()
        # Recargamos el usuario para que el reverse cache del perfil no quede viejo.
        cls.admin = User.objects.get(pk=cls.admin.pk)

    @override_settings(MEDIA_ROOT=MEDIA_TEMP)
    def crear_activo_basico(self, codigo="TST-PAG"):
        grupo = GrupoContable.objects.create(
            nombre=f"Grupo {codigo}",
            vida_util_anos=5,
            coeficiente_depreciacion=20.00,
        )
        tipo = TipoActivo.objects.create(nombre=f"Tipo {codigo}", grupo_contable=grupo)
        regional = Regional.objects.create(nombre=f"Regional {codigo}")
        ubicacion = Ubicacion.objects.create(nombre_sala=f"Sala {codigo}", regional=regional)
        return Activo.objects.create(
            codigo_tamep=codigo,
            nombre_especifico="Equipo de prueba",
            serie=f"SN-{codigo}",
            tipo_activo=tipo,
            ubicacion_base=ubicacion,
            ubicacion_actual=ubicacion,
            vida_util_estimada=60,
            fecha_adquisicion="2020-01-01",
        )


@override_settings(MEDIA_ROOT=MEDIA_TEMP)
class PaginacionListasTests(BasePaginacionPrueba):
    """Tarea 2: listas/tablas paginadas y dropdowns sin paginación."""

    def setUp(self):
        self.client = APIClient()

    def _crear_notificaciones(self, cantidad):
        Notificacion.objects.bulk_create(
            [
                Notificacion(
                    destinatario=self.user,
                    tipo="registro",
                    titulo=f"Notificación {i}",
                    mensaje="Mensaje de prueba",
                )
                for i in range(cantidad)
            ]
        )

    def _pagina_size(self):
        return settings.REST_FRAMEWORK.get("PAGE_SIZE", 50)

    # --- LISTAS/TABLAS PAGINADAS ---

    def test_notificaciones_devuelve_segunda_pagina(self):
        tamano = self._pagina_size()
        self._crear_notificaciones(tamano + 1)
        self.client.force_authenticate(user=self.user)

        primera = self.client.get("/api/notificaciones/")
        segunda = self.client.get("/api/notificaciones/?page=2")

        self.assertEqual(primera.status_code, 200, primera.content)
        self.assertEqual(primera.data["count"], tamano + 1)
        self.assertEqual(len(primera.data["results"]), tamano)
        self.assertEqual(segunda.status_code, 200, segunda.content)
        self.assertEqual(len(segunda.data["results"]), 1)

    def test_page_size_no_supera_el_tope_maximo(self):
        from .views.paginacion import PaginacionEstandar

        tope = PaginacionEstandar.max_page_size
        self._crear_notificaciones(tope + 1)
        self.client.force_authenticate(user=self.user)

        respuesta = self.client.get(f"/api/notificaciones/?page_size={tope * 999}")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.data["count"], tope + 1)
        self.assertEqual(len(respuesta.data["results"]), tope)

    def test_page_size_parametrizable_respeta_el_pedido(self):
        self._crear_notificaciones(30)
        self.client.force_authenticate(user=self.user)

        respuesta = self.client.get("/api/notificaciones/?page_size=10")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(len(respuesta.data["results"]), 10)

    def test_solicitudes_paginadas_para_componentes_que_toleren_results(self):
        # HistorialMantenimiento.vue y Solicitud-mantenimiento.vue leen
        # `res.data.results || res.data`: ambos formatos funcionan.
        activo = self.crear_activo_basico("TST-SOL")
        for i in range(2):
            SolicitudServicio.objects.create(
                activo=activo,
                solicitante=self.user,
                descripcion_problema=f"Problema reportado {i}",
                requerimiento="Revisión técnica",
            )
        self.client.force_authenticate(user=self.user)

        respuesta = self.client.get("/api/solicitudes/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.data["count"], 2)
        self.assertIn("results", respuesta.data)

    # --- DROPDOWNS / ESTRUCTURA SIN PAGINACIÓN ---

    def test_estructura_completa_sigue_siendo_lista_plana(self):
        # AsingActivos.vue y Telemetria.vue: `listaPersonalMaster = res.data`
        self.client.force_authenticate(user=self.admin)

        respuesta = self.client.get("/api/designaciones/estructura_completa/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertIsInstance(respuesta.data, list)

    def test_personal_list_sigue_siendo_lista_plana(self):
        # NewActivos.vue: `listaPersonal.value = resPers.data`
        self.client.force_authenticate(user=self.admin)

        respuesta = self.client.get("/api/activos/personal_list/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertIsInstance(respuesta.data, list)

    def test_ubicaciones_list_sigue_siendo_lista_plana(self):
        # AsingActivos.vue: `listas.ubicaciones = resUbis.data`
        self.client.force_authenticate(user=self.user)

        respuesta = self.client.get("/api/activos/ubicaciones_list/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertIsInstance(respuesta.data, list)

    def test_datos_formulario_sigue_siendo_objeto_completo(self):
        # RealizarBaja.vue y AsingActivos.vue leen .regionales y .usuarios
        self.client.force_authenticate(user=self.admin)

        respuesta = self.client.get("/api/operacion-baja/datos_formulario/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertIn("regionales", respuesta.data)
        self.assertIn("usuarios", respuesta.data)

    def test_regionales_del_viewset_sin_paginacion(self):
        # UsuariosRegistrados.vue: `regionales.value = data` (array plano)
        Regional.objects.create(nombre="Regional Norte")
        self.client.force_authenticate(user=self.user)

        respuesta = self.client.get("/api/regionales/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertIsInstance(respuesta.data, list)

    def test_transferencias_regionales_dropdown_sin_paginacion(self):
        # Transferencias.vue: `listas.regionales = resReg.data`
        self.client.force_authenticate(user=self.admin)

        respuesta = self.client.get("/api/transferencias/regionales/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertIsInstance(respuesta.data, list)

    def test_gestion_activos_sin_paginacion_por_management_activos(self):
        # ManagementActivos.vue: `activos.value = response.data` y paginación
        # client-side con slice/length sobre el array plano (líneas 63, 77-85).
        self.client.force_authenticate(user=self.user)

        respuesta = self.client.get("/api/gestion-activos/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertIsInstance(respuesta.data, list)

    def test_users_sin_paginacion_por_usuarios_registrados(self):
        # UsuariosRegistrados.vue: `usuarios.value = response.data` y
        # paginación client-side con filter/slice (líneas 73, 146-170).
        self.client.force_authenticate(user=self.admin)

        respuesta = self.client.get("/api/users/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertIsInstance(respuesta.data, list)

    def test_activos_lista_sin_paginacion_por_asignacion(self):
        # AsingActivos.vue: `data.length > 0` y `data[0]` en ?search= (92-95)
        self.client.force_authenticate(user=self.user)

        respuesta = self.client.get("/api/activos/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertIsInstance(respuesta.data, list)

    def test_me_no_esta_paginado(self):
        self.client.force_authenticate(user=self.user)

        respuesta = self.client.get("/api/me/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertNotIn("results", respuesta.data)
