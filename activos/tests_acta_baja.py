"""
Tests del acta de baja en PDF (Tarea 3).

`imprimir_acta_baja` devolvía un stub JSON
(`{"detail": "Acta de baja N lista para impresión."}`) mientras que el acta
de transferencia (`generar_pdf`) sí arma un PDF con reportlab. El frontend
NO llama a `imprimir_acta_baja` hoy (cero referencias en src/), así que el
contrato se fija copiando el de transferencias: FileResponse PDF con
`as_attachment=False` y nombre `Acta_Baja_<correlativo>.pdf`.

Corren con el shim SQLite:
    DJANGO_SETTINGS_MODULE=djshim2 PYTHONPATH=/tmp/opencode python manage.py test
"""
import io
import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from pypdf import PdfReader
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
    TipoActivo,
    Ubicacion,
)

MEDIA_TEMP = tempfile.mkdtemp(prefix="siaem-test-media-acta-")


def tearDownModule():
    shutil.rmtree(MEDIA_TEMP, ignore_errors=True)


def contenido_de(respuesta):
    """
    FileResponse es una respuesta streaming: no expone `.content` (Django
    levanta AttributeError si se accede) y `streaming_content` se consume
    UNA sola vez. Guardá el resultado en una variable.
    """
    if getattr(respuesta, "streaming", False):
        return b"".join(respuesta.streaming_content)
    return respuesta.content


def texto_del_pdf(contenido):
    """
    Texto visible de un PDF.

    reportlab comprime los streams de contenido con /ASCII85Decode +
    /FlateDecode, así que hay que descomprimirlos de verdad: pypdf hace
    exactamente eso. `pypdf` ya es dependencia del proyecto (requirements.txt).
    """
    lector = PdfReader(io.BytesIO(contenido))
    return "\n".join(pagina.extract_text() or "" for pagina in lector.pages)


@override_settings(MEDIA_ROOT=MEDIA_TEMP)
class ImprimirActaBajaTests(TestCase):
    """GET /api/operacion-baja/{id_baja}/imprimir_acta_baja/"""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="admin_acta",
            password="x",
            first_name="Rosa",
            last_name="Quispe",
            is_staff=True,
        )
        perfil, _ = PerfilUsuario.objects.get_or_create(user=cls.admin)
        perfil.rol = "admin_informatico"
        perfil.save()
        cls.admin = User.objects.get(pk=cls.admin.pk)

        cls.custodio = User.objects.create_user(
            username="custodio_acta",
            password="x",
            first_name="Juan",
            last_name="Mamani",
        )
        cls.regional = Regional.objects.create(nombre="Regional Acta")
        cls.ubicacion = Ubicacion.objects.create(nombre_sala="Sala Acta", regional=cls.regional)
        cls.grupo = GrupoContable.objects.create(
            nombre="Grupo Acta",
            vida_util_anos=5,
            coeficiente_depreciacion=20.00,
            tiene_mantenimiento_predictivo=False,
        )
        cls.tipo = TipoActivo.objects.create(nombre="Tipo Acta", grupo_contable=cls.grupo)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _dar_de_baja(self, codigo="ACT-BJA-001", motivo="Obsolescencia total del equipo"):
        """Replicate el flujo real: designación activa -> procesar_baja."""
        activo = Activo.objects.create(
            codigo_tamep=codigo,
            nombre_especifico="Notebook Dell Latitude 5420",
            serie=f"SN-{codigo}",
            tipo_activo=self.tipo,
            ubicacion_base=self.ubicacion,
            ubicacion_actual=self.ubicacion,
            vida_util_estimada=60,
            situacion_activo="Asignado",
        )
        gerencia = Gerencia.objects.create(nombre=f"Gerencia {codigo}", regional=self.regional)
        cargo = Cargo.objects.create(nombre=f"Cargo {codigo}", gerencia=gerencia)
        Designacion.objects.create(
            activo=activo,
            usuario=self.custodio,
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
                "motivo": motivo,
            },
            format="multipart",
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        return BajaActivo.objects.get(activo=activo)

    def test_devuelve_un_pdf_y_no_json(self):
        baja = self._dar_de_baja()

        respuesta = self.client.get(f"/api/operacion-baja/{baja.id}/imprimir_acta_baja/")

        contenido = contenido_de(respuesta)
        self.assertEqual(respuesta.status_code, 200, contenido)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertTrue(
            contenido.startswith(b"%PDF"),
            f"No es un PDF: {contenido[:40]!r}",
        )

    def test_el_nombre_del_archivo_lleva_el_correlativo(self):
        baja = self._dar_de_baja(codigo="ACT-BJA-002")

        respuesta = self.client.get(f"/api/operacion-baja/{baja.id}/imprimir_acta_baja/")

        disposition = respuesta["Content-Disposition"]
        self.assertIn(f"Acta_Baja_{baja.num_baja}.pdf", disposition)
        self.assertIn("inline", disposition)

    def test_el_acta_incluye_al_activo_y_al_correlativo(self):
        baja = self._dar_de_baja(codigo="ACT-BJA-003")

        respuesta = self.client.get(f"/api/operacion-baja/{baja.id}/imprimir_acta_baja/")
        texto = texto_del_pdf(contenido_de(respuesta))

        self.assertIn("ACTA DE BAJA", texto.upper())
        self.assertIn(baja.num_baja, texto)
        self.assertIn("ACT-BJA-003", texto)
        self.assertIn("Notebook Dell Latitude 5420", texto)
        self.assertIn("SN-ACT-BJA-003", texto)

    def test_el_acta_incluye_al_custodio_de_la_designacion_cerrada(self):
        baja = self._dar_de_baja(codigo="ACT-BJA-004")

        respuesta = self.client.get(f"/api/operacion-baja/{baja.id}/imprimir_acta_baja/")
        texto = texto_del_pdf(contenido_de(respuesta))

        self.assertIn("Juan Mamani", texto)  # custodio de la designación cerrada
        self.assertIn("Rosa Quispe", texto)  # autorizó la baja

    def test_el_acta_incluye_el_motivo(self):
        baja = self._dar_de_baja(
            codigo="ACT-BJA-005", motivo="Daño irreparable por ingreso de agua"
        )

        respuesta = self.client.get(f"/api/operacion-baja/{baja.id}/imprimir_acta_baja/")
        texto = texto_del_pdf(contenido_de(respuesta))

        self.assertIn("Daño irreparable por ingreso de agua", texto)

    def test_baja_sin_designacion_no_rompe_el_acta(self):
        """Triangulación: un activo sin custodia previa también se puede dar de baja."""
        activo = Activo.objects.create(
            codigo_tamep="ACT-BJA-SIN",
            nombre_especifico="Proyector Epson",
            serie="SN-SIN-DESIG",
            tipo_activo=self.tipo,
            ubicacion_base=self.ubicacion,
            vida_util_estimada=60,
            situacion_activo="Disponible",
        )
        respuesta = self.client.post(
            f"/api/operacion-baja/{activo.id}/procesar_baja/",
            {
                "regional_id": str(self.regional.id),
                "usuario_id": str(self.admin.id),
                "motivo": "Fin de uso institucional",
            },
            format="multipart",
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        baja = BajaActivo.objects.get(activo=activo)

        pdf = self.client.get(f"/api/operacion-baja/{baja.id}/imprimir_acta_baja/")
        texto = texto_del_pdf(contenido_de(pdf))

        self.assertIn("Sin designación", texto)
        self.assertIn("ACT-BJA-SIN", texto)

    def test_baja_inexistente_responde_404(self):
        respuesta = self.client.get("/api/operacion-baja/999999/imprimir_acta_baja/")

        self.assertEqual(respuesta.status_code, 404, contenido_de(respuesta))

    def test_el_acta_tiene_el_mismo_formato_que_la_de_transferencia(self):
        """Misma página (carta/letter) que el acta de transferencia."""
        from reportlab.lib.pagesizes import letter

        ancho, alto = letter
        baja = self._dar_de_baja(codigo="ACT-BJA-006")
        respuesta = self.client.get(f"/api/operacion-baja/{baja.id}/imprimir_acta_baja/")
        pagina = PdfReader(io.BytesIO(contenido_de(respuesta))).pages[0]

        self.assertEqual(float(pagina.mediabox.width), ancho)
        self.assertEqual(float(pagina.mediabox.height), alto)
