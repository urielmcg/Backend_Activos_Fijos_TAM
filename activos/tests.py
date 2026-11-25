import shutil
import tempfile
from datetime import date
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    Activo,
    BajaActivo,
    Cargo,
    Designacion,
    Gerencia,
    GrupoContable,
    HistorialEstadoActivo,
    Intervencion,
    MetricaPredictiva,
    PerfilUsuario,
    Regional,
    SolicitudServicio,
    TipoActivo,
    Ubicacion,
)

# Los QR se generan en Activo.save(); redirigimos MEDIA_ROOT a un temporal
# para no escribir dentro del repositorio durante los tests.
MEDIA_TEMP = tempfile.mkdtemp(prefix="siaem-test-media-")


def tearDownModule():
    shutil.rmtree(MEDIA_TEMP, ignore_errors=True)


class BaseDatosPrueba(TestCase):
    """Arma un árbol de datos mínimo: regional, ubicación, grupo y activo."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="tecnico_prueba", password="x", first_name="Tecnico", last_name="Prueba"
        )
        cls.admin = User.objects.create_user(
            username="admin_prueba",
            password="x",
            first_name="Admin",
            last_name="Prueba",
            is_staff=True,
        )
        perfil, _ = PerfilUsuario.objects.get_or_create(user=cls.admin)
        perfil.rol = "admin_informatico"
        perfil.save()
        # Recargamos el usuario para que el reverse cache del perfil no quede viejo.
        cls.admin = User.objects.get(pk=cls.admin.pk)

    def crear_activo(self, codigo, con_ia=False):
        grupo = GrupoContable.objects.create(
            nombre=f"Grupo {codigo}",
            vida_util_anos=5,
            coeficiente_depreciacion=20.00,
            tiene_mantenimiento_predictivo=con_ia,
        )
        tipo = TipoActivo.objects.create(nombre=f"Tipo {codigo}", grupo_contable=grupo)
        regional = Regional.objects.create(nombre=f"Regional {codigo}")
        ubicacion = Ubicacion.objects.create(nombre_sala=f"Sala {codigo}", regional=regional)
        activo = Activo.objects.create(
            codigo_tamep=codigo,
            nombre_especifico="Equipo de prueba",
            serie=f"SN-{codigo}",
            tipo_activo=tipo,
            ubicacion_base=ubicacion,
            ubicacion_actual=ubicacion,
            vida_util_estimada=60,
            fecha_adquisicion=date(2020, 1, 1),
        )
        return activo, regional, ubicacion

    def crear_intervencion(self, activo, tipo, lectura=5.0):
        ahora = timezone.now()
        solicitud = SolicitudServicio.objects.create(
            activo=activo,
            solicitante=self.user,
            descripcion_problema="Falla reportada por el usuario",
            requerimiento="Reparación del equipo",
        )
        return Intervencion.objects.create(
            solicitud=solicitud,
            tecnico=self.user,
            activo=activo,
            tipo_mantenimiento=tipo,
            diagnostico_previo="Diagnóstico de prueba",
            detalles_reparacion="Trabajo realizado de prueba",
            verificado_por="Verificador de prueba",
            fecha_inicio=ahora - timedelta(hours=2),
            fecha_fin=ahora,
            lectura_uso_equipo=lectura,
        )


@override_settings(MEDIA_ROOT=MEDIA_TEMP)
class ContadoresIntervencionTests(BaseDatosPrueba):
    def test_cada_intervencion_incrementa_su_contador_una_sola_vez(self):
        activo, _, _ = self.crear_activo("TST-CNT")
        self.crear_intervencion(activo, "Correctivo")
        self.crear_intervencion(activo, "Preventivo")
        self.crear_intervencion(activo, "Servicio")
        self.crear_intervencion(activo, "Mejora")

        activo.refresh_from_db()

        self.assertEqual(activo.contador_correctivos, 1)
        self.assertEqual(activo.contador_preventivos, 1)
        self.assertEqual(activo.contador_servicios, 1)
        self.assertEqual(activo.contador_mejoras, 1)

    def test_contador_fallas_se_acumula_en_activos_con_ia(self):
        # Activo.save() pone contador_fallas en 0 cuando el grupo no tiene IA,
        # así que la acumulación solo aplica a los activos con IA.
        activo, _, _ = self.crear_activo("TST-FAL", con_ia=True)
        self.crear_intervencion(activo, "Correctivo")
        self.crear_intervencion(activo, "Correctivo")

        activo.refresh_from_db()

        self.assertEqual(activo.contador_correctivos, 2)
        self.assertEqual(activo.contador_fallas, 2)

    def test_guardar_intervencion_no_vuelve_a_contarla_al_editarla(self):
        activo, _, _ = self.crear_activo("TST-EDT")
        intervencion = self.crear_intervencion(activo, "Correctivo")
        intervencion.detalles_reparacion = "Detalle corregido"
        intervencion.save()

        activo.refresh_from_db()
        self.assertEqual(activo.contador_correctivos, 1)

    def test_horas_de_uso_se_persisten_en_activos_con_ia(self):
        activo, _, _ = self.crear_activo("TST-HRS", con_ia=True)
        self.crear_intervencion(activo, "Preventivo", lectura=120.0)

        activo.refresh_from_db()
        self.assertEqual(activo.horas_uso_actual, 120.0)


@override_settings(MEDIA_ROOT=MEDIA_TEMP)
class PuertaIaTests(BaseDatosPrueba):
    def test_grupo_sin_ia_no_genera_metricas_predictivas(self):
        activo, _, _ = self.crear_activo("TST-NIA", con_ia=False)
        self.crear_intervencion(activo, "Preventivo")

        self.assertFalse(MetricaPredictiva.objects.filter(activo=activo).exists())

    def test_grupo_con_ia_genera_metricas_predictivas(self):
        activo, _, _ = self.crear_activo("TST-IA", con_ia=True)
        self.crear_intervencion(activo, "Correctivo")

        self.assertTrue(MetricaPredictiva.objects.filter(activo=activo).exists())


@override_settings(MEDIA_ROOT=MEDIA_TEMP)
class ProcesarBajaTests(BaseDatosPrueba):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _designar(self, activo, regional, ubicacion):
        gerencia = Gerencia.objects.create(
            nombre=f"Gerencia {activo.codigo_tamep}", regional=regional
        )
        cargo = Cargo.objects.create(nombre=f"Cargo {activo.codigo_tamep}", gerencia=gerencia)
        return Designacion.objects.create(
            activo=activo,
            usuario=self.user,
            regional=regional,
            gerencia=gerencia,
            cargo=cargo,
            ubicacion=ubicacion,
            tipo="Permanente",
            esta_activa=True,
        )

    def test_procesar_baja_cierra_designacion_y_cambia_estado(self):
        activo, regional, ubicacion = self.crear_activo("TST-BJA")
        designacion = self._designar(activo, regional, ubicacion)

        respuesta = self.client.post(
            f"/api/operacion-baja/{activo.id}/procesar_baja/",
            {
                "regional_id": str(regional.id),
                "usuario_id": str(self.admin.id),
                "motivo": "Obsolescencia total del equipo",
            },
            format="multipart",
        )

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        activo.refresh_from_db()
        self.assertEqual(activo.situacion_activo, "Baja")
        self.assertEqual(activo.estado_actual, "Malo")

        baja = BajaActivo.objects.get(activo=activo)
        self.assertEqual(baja.solicitante, self.admin)
        self.assertTrue(baja.num_baja)

        designacion.refresh_from_db()
        self.assertFalse(designacion.esta_activa)

        self.assertTrue(
            HistorialEstadoActivo.objects.filter(
                activo=activo, observacion__contains="Situación: Asignado → Baja"
            ).exists()
        )

    def test_no_permite_dos_bajas_para_el_mismo_activo(self):
        activo, regional, _ = self.crear_activo("TST-DUP")
        datos = {
            "regional_id": str(regional.id),
            "usuario_id": str(self.admin.id),
            "motivo": "Daño irreparable",
        }
        primera = self.client.post(
            f"/api/operacion-baja/{activo.id}/procesar_baja/", datos, format="multipart"
        )
        self.assertEqual(primera.status_code, 201, primera.content)

        segunda = self.client.post(
            f"/api/operacion-baja/{activo.id}/procesar_baja/", datos, format="multipart"
        )
        self.assertEqual(segunda.status_code, 400, segunda.content)

    def test_motivo_es_obligatorio(self):
        activo, regional, _ = self.crear_activo("TST-MOT")

        respuesta = self.client.post(
            f"/api/operacion-baja/{activo.id}/procesar_baja/",
            {
                "regional_id": str(regional.id),
                "usuario_id": str(self.admin.id),
                "motivo": "   ",
            },
            format="multipart",
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(BajaActivo.objects.filter(activo=activo).count(), 0)

    def test_procesar_baja_sin_designacion_activa(self):
        # El activo puede estar 'Disponible' (sin custodia) y la baja debe funcionar.
        activo, regional, _ = self.crear_activo("TST-SIN")

        respuesta = self.client.post(
            f"/api/operacion-baja/{activo.id}/procesar_baja/",
            {
                "regional_id": str(regional.id),
                "usuario_id": str(self.admin.id),
                "motivo": "Obsolescencia total del equipo",
            },
            format="multipart",
        )

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        activo.refresh_from_db()
        self.assertEqual(activo.situacion_activo, "Baja")
        self.assertFalse(Designacion.objects.filter(activo=activo).exists())

    def test_rechaza_autorizador_de_otra_regional(self):
        activo, regional, _ = self.crear_activo("TST-REG")
        regional_ajena = Regional.objects.create(nombre="Regional Ajena")
        otro = User.objects.create_user(username="otro_admin", password="x")
        perfil, _ = PerfilUsuario.objects.get_or_create(user=otro)
        perfil.regional = regional_ajena
        perfil.save()

        respuesta = self.client.post(
            f"/api/operacion-baja/{activo.id}/procesar_baja/",
            {
                "regional_id": str(regional.id),
                "usuario_id": str(otro.id),
                "motivo": "Daño irreparable",
            },
            format="multipart",
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("usuario_id", respuesta.data)
        self.assertEqual(BajaActivo.objects.filter(activo=activo).count(), 0)

    def test_documento_que_no_es_pdf_se_rechaza(self):
        activo, regional, _ = self.crear_activo("TST-DOC")
        archivo = SimpleUploadedFile("informe.txt", b"texto", content_type="text/plain")

        respuesta = self.client.post(
            f"/api/operacion-baja/{activo.id}/procesar_baja/",
            {
                "regional_id": str(regional.id),
                "usuario_id": str(self.admin.id),
                "motivo": "Daño irreparable",
                "documento": archivo,
            },
            format="multipart",
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("documento", respuesta.data)

    def test_documento_pdf_se_adjunta_al_registro(self):
        activo, regional, _ = self.crear_activo("TST-PDF")
        archivo = SimpleUploadedFile(
            "informe.pdf", b"%PDF-1.4 contenido de prueba", content_type="application/pdf"
        )

        respuesta = self.client.post(
            f"/api/operacion-baja/{activo.id}/procesar_baja/",
            {
                "regional_id": str(regional.id),
                "usuario_id": str(self.admin.id),
                "motivo": "Daño irreparable",
                "documento": archivo,
            },
            format="multipart",
        )

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        baja = BajaActivo.objects.get(activo=activo)
        self.assertTrue(baja.documento_respaldo.name.endswith(".pdf"))


@override_settings(MEDIA_ROOT=MEDIA_TEMP)
class DatosFormularioTests(BaseDatosPrueba):
    def test_usuarios_declaran_su_regional(self):
        # RealizarBaja.vue filtra los usuarios por regional_id.
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

        respuesta = self.client.get("/api/operacion-baja/datos_formulario/")

        self.assertEqual(respuesta.status_code, 200)
        usuarios = {u["id"]: u for u in respuesta.data["usuarios"]}
        self.assertIn(self.admin.id, usuarios)
        self.assertIn("regional_id", usuarios[self.admin.id])


@override_settings(MEDIA_ROOT=MEDIA_TEMP)
class ActivoSerializerTests(BaseDatosPrueba):
    def test_activo_expone_ubicacion_actual_detalle(self):
        # RealizarBaja.vue precarga la regional desde ubicacion_actual_detalle.regional.
        from .serializers import ActivoSerializer

        activo, regional, _ = self.crear_activo("TST-SER")

        data = ActivoSerializer(activo).data

        self.assertEqual(data["ubicacion_actual_detalle"]["regional"], regional.id)
