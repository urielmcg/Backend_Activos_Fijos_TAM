"""
Tests de la auditoría por API (Tarea 1).

`AuditoriaViewSet` lee `django.contrib.admin.LogEntry` (`django_admin_log`).
Antes de esta ronda esa tabla solo se llenaba desde `/admin/`, por lo que
toda escritura por API era invisible en `/auditoria`. Estos tests cubren que
los viewsets con escritura del frontend dejen rastro y que el change_message
no filtre credenciales.

Corren con el shim SQLite:
    DJANGO_SETTINGS_MODULE=djshim2 PYTHONPATH=/tmp/opencode python manage.py test
"""
import shutil
import tempfile

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import (
    Activo,
    BajaActivo,
    Cargo,
    Designacion,
    Gerencia,
    GrupoContable,
    PerfilUsuario,
    Regional,
    SolicitudServicio,
    TipoActivo,
    Ubicacion,
)
from django.contrib.auth.models import User

MEDIA_TEMP = tempfile.mkdtemp(prefix="siaem-test-media-aud-")


def tearDownModule():
    shutil.rmtree(MEDIA_TEMP, ignore_errors=True)


@override_settings(MEDIA_ROOT=MEDIA_TEMP)
class AuditoriaApiTests(TestCase):
    """Las mutaciones por API deben quedar en django_admin_log."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="admin_aud",
            password="x",
            first_name="Admin",
            last_name="Auditoria",
            is_staff=True,
        )
        perfil, _ = PerfilUsuario.objects.get_or_create(user=cls.admin)
        perfil.rol = "admin_informatico"
        perfil.save()
        cls.admin = User.objects.get(pk=cls.admin.pk)

        cls.regional = Regional.objects.create(nombre="Regional Aud")
        cls.ubicacion = Ubicacion.objects.create(
            nombre_sala="Sala Aud", regional=cls.regional
        )
        cls.grupo = GrupoContable.objects.create(
            nombre="Grupo Aud",
            vida_util_anos=5,
            coeficiente_depreciacion=20.00,
            tiene_mantenimiento_predictivo=False,
        )
        cls.tipo = TipoActivo.objects.create(nombre="Tipo Aud", grupo_contable=cls.grupo)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _payload_activo(self, codigo="TST-AUD"):
        return {
            "codigo_tamep": codigo,
            "nombre_especifico": "Equipo auditado",
            "serie": f"SN-{codigo}",
            "tipo_activo": self.tipo.id,
            "ubicacion_base": self.ubicacion.id,
            "ubicacion_actual": self.ubicacion.id,
            "vida_util_estimada": 60,
        }

    def _logs_de(self, modelo):
        content_type = ContentType.objects.get_for_model(modelo, for_concrete_model=False)
        return LogEntry.objects.filter(content_type=content_type).order_by("-action_time")

    def test_crear_activo_por_api_deja_log_entry(self):
        respuesta = self.client.post("/api/activos/", self._payload_activo(), format="json")

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        logs = self._logs_de(Activo)
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.action_flag, ADDITION)
        self.assertEqual(log.user, self.admin)
        self.assertEqual(log.content_type.model, "activo")
        self.assertIn("/api/activos/", log.change_message)

    def test_actualizar_activo_por_api_deja_log_entry(self):
        activo = Activo.objects.create(
            codigo_tamep="TST-AUD-UPD",
            nombre_especifico="Equipo a editar",
            serie="SN-AUD-UPD",
            tipo_activo=self.tipo,
            ubicacion_base=self.ubicacion,
            ubicacion_actual=self.ubicacion,
            vida_util_estimada=60,
        )

        respuesta = self.client.patch(
            f"/api/activos/{activo.id}/",
            {"nombre_especifico": "Equipo editado"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        log = self._logs_de(Activo).first()
        self.assertEqual(log.action_flag, CHANGE)
        self.assertIn("nombre_especifico=Equipo editado", log.change_message)

    def test_eliminar_activo_por_api_deja_log_entry(self):
        activo = Activo.objects.create(
            codigo_tamep="TST-AUD-DEL",
            nombre_especifico="Equipo a borrar",
            serie="SN-AUD-DEL",
            tipo_activo=self.tipo,
            ubicacion_base=self.ubicacion,
            ubicacion_actual=self.ubicacion,
            vida_util_estimada=60,
        )

        respuesta = self.client.delete(f"/api/activos/{activo.id}/")

        self.assertEqual(respuesta.status_code, 204, respuesta.content)
        log = self._logs_de(Activo).first()
        self.assertEqual(log.action_flag, DELETION)
        self.assertIn("TST-AUD-DEL", log.object_repr)

    def test_el_log_respeta_al_usuario_real_de_la_peticion(self):
        otro = User.objects.create_user(username="otro_editor", password="x")
        perfil, _ = PerfilUsuario.objects.get_or_create(user=otro)
        perfil.rol = "admin_regional"
        perfil.save()
        # Recargamos el usuario para que el reverse cache del perfil no quede
        # viejo (mismo truco que en BaseDatosPrueba.setUpTestData).
        otro = User.objects.get(pk=otro.pk)
        self.client.force_authenticate(user=otro)

        respuesta = self.client.post("/api/activos/", self._payload_activo("TST-AUD-2"), format="json")

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        log = self._logs_de(Activo).first()
        self.assertEqual(log.user, otro)
        self.assertEqual(log.user_id, otro.id)

    def test_el_change_message_no_expone_passwords(self):
        respuesta = self.client.post(
            "/api/users/",
            {
                "username": "usuario_nuevo",
                "password": "SuperSecreto-2026!",
                "first_name": "Nuevo",
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        log = self._logs_de(User).first()
        self.assertEqual(log.action_flag, ADDITION)
        self.assertNotIn("SuperSecreto-2026!", log.change_message)
        self.assertIn("password=[oculto]", log.change_message)

    def test_el_change_message_resume_los_cambios_y_el_endpoint(self):
        activo = Activo.objects.create(
            codigo_tamep="TST-AUD-RES",
            nombre_especifico="Equipo resumen",
            serie="SN-AUD-RES",
            tipo_activo=self.tipo,
            ubicacion_base=self.ubicacion,
            ubicacion_actual=self.ubicacion,
            vida_util_estimada=60,
        )

        respuesta = self.client.patch(
            f"/api/activos/{activo.id}/",
            {"estado_actual": "Regular", "horas_uso_actual": 12.5},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        log = self._logs_de(Activo).first()
        self.assertIn("PATCH", log.change_message)
        self.assertIn(f"/api/activos/{activo.id}/", log.change_message)
        self.assertIn("estado_actual=Regular", log.change_message)
        # horas_uso_actual es read_only en ActivoSerializer: la API lo ignora
        # y la auditoría refleja solo lo que realmente se aceptó.
        self.assertNotIn("horas_uso_actual", log.change_message)

    def test_transferencia_registra_su_creacion(self):
        gerencia = Gerencia.objects.create(nombre="Gerencia Aud", regional=self.regional)
        cargo = Cargo.objects.create(nombre="Cargo Aud", gerencia=gerencia)
        emisor = User.objects.create_user(username="emisor_aud", password="x")
        receptor = User.objects.create_user(username="receptor_aud", password="x")
        destino = Ubicacion.objects.create(nombre_sala="Sala Destino", regional=self.regional)
        designacion = Designacion.objects.create(
            activo=Activo.objects.create(
                codigo_tamep="TST-AUD-TRA",
                nombre_especifico="Equipo transferido",
                serie="SN-AUD-TRA",
                tipo_activo=self.tipo,
                ubicacion_base=self.ubicacion,
                ubicacion_actual=self.ubicacion,
                vida_util_estimada=60,
            ),
            usuario=emisor,
            regional=self.regional,
            gerencia=gerencia,
            cargo=cargo,
            ubicacion=self.ubicacion,
            tipo="Permanente",
            esta_activa=True,
        )

        respuesta = self.client.post(
            "/api/transferencias/",
            {
                "activo": designacion.activo.id,
                "emisor": emisor.id,
                "receptor": receptor.id,
                "reg_emisor": self.regional.id,
                "reg_receptor": self.regional.id,
                "ger_emisor": gerencia.id,
                "ger_receptor": gerencia.id,
                "car_emisor": cargo.id,
                "car_receptor": cargo.id,
                "ubicacion_origen": self.ubicacion.id,
                "ubicacion_destino": destino.id,
                "motivo": "Cambio de área",
                "num_acta": "ACT-AUD-001",
                "tipo": "TR",
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        from .models import Transferencia

        log = self._logs_de(Transferencia).first()
        self.assertIsNotNone(log, "La transferencia no dejó LogEntry")
        self.assertEqual(log.action_flag, ADDITION)
        self.assertEqual(log.user, self.admin)

    def test_solicitud_de_servicio_registra_su_creacion(self):
        activo = Activo.objects.create(
            codigo_tamep="TST-AUD-SOL",
            nombre_especifico="Equipo con falla",
            serie="SN-AUD-SOL",
            tipo_activo=self.tipo,
            ubicacion_base=self.ubicacion,
            ubicacion_actual=self.ubicacion,
            vida_util_estimada=60,
        )

        respuesta = self.client.post(
            "/api/solicitudes/",
            {
                "activo": activo.id,
                "descripcion_problema": "No enciende",
                "requerimiento": "Revisar fuente",
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        log = self._logs_de(SolicitudServicio).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.action_flag, ADDITION)
        # El serializer inyecta el solicitante: el log debe reflejarlo.
        self.assertIn("solicitante=", log.change_message)

    def test_baja_por_api_deja_log_entry(self):
        activo = Activo.objects.create(
            codigo_tamep="TST-AUD-BAJ",
            nombre_especifico="Equipo en baja",
            serie="SN-AUD-BAJ",
            tipo_activo=self.tipo,
            ubicacion_base=self.ubicacion,
            ubicacion_actual=self.ubicacion,
            vida_util_estimada=60,
        )
        gerencia = Gerencia.objects.create(nombre="Gerencia Baja", regional=self.regional)
        cargo = Cargo.objects.create(nombre="Cargo Baja", gerencia=gerencia)
        Designacion.objects.create(
            activo=activo,
            usuario=self.admin,
            regional=self.regional,
            gerencia=gerencia,
            cargo=cargo,
            ubicacion=self.ubicacion,
            tipo="Permanente",
            esta_activa=True,
        )

        respuesta = self.client.post(
            f"/api/operacion-baja/{activo.id}/procesar_baja/",
            {
                "regional_id": str(self.regional.id),
                "usuario_id": str(self.admin.id),
                "motivo": "Obsolescencia total",
            },
            format="multipart",
        )

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        log = self._logs_de(BajaActivo).first()
        self.assertIsNotNone(log, "procesar_baja no dejó LogEntry")
        self.assertEqual(log.action_flag, ADDITION)
        self.assertEqual(log.user, self.admin)

    def test_pantalla_auditoria_devuelve_los_registros_de_api(self):
        """Prueba integral: lo que escribe la API debe salir en /api/auditoria/."""
        respuesta_creacion = self.client.post(
            "/api/activos/", self._payload_activo("TST-AUD-UI"), format="json"
        )
        self.assertEqual(respuesta_creacion.status_code, 201, respuesta_creacion.content)

        respuesta = self.client.get("/api/auditoria/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        filas = respuesta.data["results"] if "results" in respuesta.data else respuesta.data
        api = [f for f in filas if f["tabla"] == "activo"]
        self.assertTrue(api, "El endpoint /api/auditoria/ no devolvió filas de 'activo'")
        self.assertEqual(api[0]["usuario"], self.admin.username)
        self.assertEqual(api[0]["accion"], "Creación")

    def test_peticion_sin_usuario_autenticado_no_escribe_log(self):
        self.client.force_authenticate(user=None)

        respuesta = self.client.post("/api/activos/", self._payload_activo("TST-AUD-401"), format="json")

        self.assertEqual(respuesta.status_code, 401, respuesta.content)
        self.assertEqual(self._logs_de(Activo).count(), 0)

    def test_devolver_designacion_registra_el_cierre_de_custodia(self):
        """Acción custom (no pasa por perform_update): debe quedar igual en el log."""
        custodio = User.objects.create_user(username="custodio_aud", password="x")
        activo = Activo.objects.create(
            codigo_tamep="TST-AUD-DEV",
            nombre_especifico="Equipo con custodia",
            serie="SN-AUD-DEV",
            tipo_activo=self.tipo,
            ubicacion_base=self.ubicacion,
            ubicacion_actual=self.ubicacion,
            vida_util_estimada=60,
            situacion_activo="Asignado",
        )
        gerencia = Gerencia.objects.create(nombre="Gerencia Dev", regional=self.regional)
        cargo = Cargo.objects.create(nombre="Cargo Dev", gerencia=gerencia)
        designacion = Designacion.objects.create(
            activo=activo,
            usuario=custodio,
            regional=self.regional,
            gerencia=gerencia,
            cargo=cargo,
            ubicacion=self.ubicacion,
            tipo="Permanente",
            esta_activa=True,
        )

        respuesta = self.client.post(f"/api/designaciones/{designacion.id}/devolver/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        log = self._logs_de(Designacion).first()
        self.assertIsNotNone(log, "devolver no dejó LogEntry")
        self.assertEqual(log.action_flag, CHANGE)
        self.assertIn("esta_activa=False", log.change_message)
