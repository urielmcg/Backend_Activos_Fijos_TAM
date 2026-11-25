"""
Tests del endpoint de gestión avanzada (Tarea 2).

El frontend envía `?ordering=-probabilidad_falla` (ModuloPredictivo.vue L16)
pero el campo vive en la relación OneToOne `prediccion`
(MetricaPredictiva.probabilidad_falla), no en Activo: DRF descartaba el
ordering en silencio. Acá se cubre el alias, el orden real de las filas y
los campos que los componentes leen por fila.

Corren con el shim SQLite:
    DJANGO_SETTINGS_MODULE=djshim2 PYTHONPATH=/tmp/opencode python manage.py test
"""
import shutil
import tempfile
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import (
    Activo,
    Designacion,
    GrupoContable,
    MetricaPredictiva,
    Regional,
    TipoActivo,
    Ubicacion,
)

MEDIA_TEMP = tempfile.mkdtemp(prefix="siaem-test-media-ges-")


def tearDownModule():
    shutil.rmtree(MEDIA_TEMP, ignore_errors=True)


@override_settings(MEDIA_ROOT=MEDIA_TEMP)
class GestionActivosOrderingTests(TestCase):
    """`/api/gestion-activos/` debe honrar el ordering que pide el frontend."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="usuario_ges", password="x", first_name="Usuario", last_name="Gestion"
        )
        cls.regional = Regional.objects.create(nombre="Regional Ges")
        cls.ubicacion = Ubicacion.objects.create(nombre_sala="Sala Ges", regional=cls.regional)
        cls.grupo = GrupoContable.objects.create(
            nombre="Grupo Ges",
            vida_util_anos=5,
            coeficiente_depreciacion=20.00,
            tiene_mantenimiento_predictivo=True,
        )
        cls.tipo = TipoActivo.objects.create(nombre="Tipo Ges", grupo_contable=cls.grupo)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _crear_activo(self, codigo, probabilidad=None, salud=None):
        activo = Activo.objects.create(
            codigo_tamep=codigo,
            nombre_especifico=f"Equipo {codigo}",
            serie=f"SN-{codigo}",
            tipo_activo=self.tipo,
            ubicacion_base=self.ubicacion,
            ubicacion_actual=self.ubicacion,
            vida_util_estimada=60,
            fecha_adquisicion=date(2020, 1, 1),
        )
        if probabilidad is not None:
            # La señal inicializar_ia_nuevo_activo ya crea una métrica vacía
            # cuando el grupo tiene IA habilitada: actualizamos, no duplicamos.
            MetricaPredictiva.objects.update_or_create(
                activo=activo,
                defaults={
                    "probabilidad_falla": probabilidad,
                    "indice_salud_fuzzy": salud if salud is not None else 50,
                },
            )
        return activo

    def _codigos(self, query):
        respuesta = self.client.get(f"/api/gestion-activos/?{query}")
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        return [a["codigo_tamep"] for a in respuesta.data]

    def test_ordering_negativo_ordena_por_probabilidad_de_falla_desc(self):
        # ModuloPredictivo.vue: `gestion-activos/?ordering=-probabilidad_falla`
        self._crear_activo("GES-BAJA", probabilidad=10)
        self._crear_activo("GES-CRIT", probabilidad=90)
        self._crear_activo("GES-MOD", probabilidad=50)

        codigos = self._codigos("ordering=-probabilidad_falla")

        self.assertEqual(codigos, ["GES-CRIT", "GES-MOD", "GES-BAJA"])

    def test_ordering_positivo_ordena_por_probabilidad_de_falla_asc(self):
        self._crear_activo("GES-BAJA", probabilidad=10)
        self._crear_activo("GES-CRIT", probabilidad=90)
        self._crear_activo("GES-MOD", probabilidad=50)

        codigos = self._codigos("ordering=probabilidad_falla")

        self.assertEqual(codigos, ["GES-BAJA", "GES-MOD", "GES-CRIT"])

    def test_ordering_por_indice_de_salud_fuzzy(self):
        self._crear_activo("GES-SAL-1", probabilidad=30, salud=15)
        self._crear_activo("GES-SAL-2", probabilidad=30, salud=85)

        codigos = self._codigos("ordering=-indice_salud_fuzzy")

        self.assertEqual(codigos, ["GES-SAL-2", "GES-SAL-1"])

    def test_ordering_inexistente_se_descarta_sin_romper(self):
        self._crear_activo("GES-X1", probabilidad=40)

        codigos = self._codigos("ordering=campo_que_no_existe")

        self.assertEqual(codigos, ["GES-X1"])

    def test_ordering_sigue_respeta_los_demas_campos(self):
        # ordering_fields heredado: fecha_adquisicion y costo siguen funcionando.
        self._crear_activo("GES-COST-1", probabilidad=10)
        Activo.objects.filter(codigo_tamep="GES-COST-1").update(costo=100)
        self._crear_activo("GES-COST-2", probabilidad=10)
        Activo.objects.filter(codigo_tamep="GES-COST-2").update(costo=900)

        codigos = self._codigos("ordering=costo")

        self.assertEqual(codigos, ["GES-COST-1", "GES-COST-2"])

    def test_activos_sin_metricas_no_rompen_el_ordering(self):
        # LEFT JOIN: un activo sin MetricaPredictiva no debe tumbar la lista.
        self._crear_activo("GES-SIN-IA")  # sin predicción
        self._crear_activo("GES-CON-IA", probabilidad=80)

        codigos = self._codigos("ordering=-probabilidad_falla")

        self.assertEqual(len(codigos), 2)
        self.assertEqual(codigos[0], "GES-CON-IA")


@override_settings(MEDIA_ROOT=MEDIA_TEMP)
class GestionActivosSerializerTests(TestCase):
    """Campos que los componentes leen por fila desde /gestion-activos/."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="usuario_ser", password="x")
        cls.regional = Regional.objects.create(nombre="Regional Ser")
        cls.ubicacion = Ubicacion.objects.create(nombre_sala="Sala Ser", regional=cls.regional)
        cls.grupo = GrupoContable.objects.create(
            nombre="Grupo Ser",
            vida_util_anos=5,
            coeficiente_depreciacion=20.00,
            tiene_mantenimiento_predictivo=True,
        )
        cls.tipo = TipoActivo.objects.create(nombre="Tipo Ser", grupo_contable=cls.grupo)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _fila(self, codigo="SER-001", probabilidad=88.5, salud=35.25):
        activo = Activo.objects.create(
            codigo_tamep=codigo,
            nombre_especifico="Equipo reportado",
            serie=f"SN-{codigo}",
            tipo_activo=self.tipo,
            ubicacion_base=self.ubicacion,
            ubicacion_actual=self.ubicacion,
            vida_util_estimada=60,
            horas_uso_actual=120.0,
            contador_preventivos=3,
        )
        MetricaPredictiva.objects.update_or_create(
            activo=activo,
            defaults={
                "probabilidad_falla": probabilidad,
                "indice_salud_fuzzy": salud,
                "mtbf": 400.0,
                "mttr": 12.0,
                "recomendacion_ia": "Programar mantenimiento preventivo urgente.",
            },
        )
        respuesta = self.client.get("/api/gestion-activos/")
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        return next(a for a in respuesta.data if a["codigo_tamep"] == codigo)

    def test_expone_probabilidad_de_falla_plana(self):
        # ModuloPredictivo/Reportes/Monitoreo leen `a.probabilidad_falla`.
        fila = self._fila()

        self.assertEqual(fila["probabilidad_falla"], 88.5)

    def test_expone_indice_de_salud_anidado_en_prediccion(self):
        # ViewDetails.vue: `activo.prediccion?.indice_salud_fuzzy`
        fila = self._fila()

        self.assertEqual(fila["prediccion"]["indice_salud_fuzzy"], "35.25")

    def test_prediccion_anidada_trae_los_campos_del_modal_predictivo(self):
        # ModuloPredictivo.vue (modal): mtbf, mttr, recomendacion_ia y
        # horas_soporte_acumuladas salen del objeto anidado.
        fila = self._fila()

        prediccion = fila["prediccion"]
        self.assertEqual(prediccion["mtbf"], 400.0)
        self.assertEqual(prediccion["mttr"], 12.0)
        self.assertIn("mantenimiento preventivo", prediccion["recomendacion_ia"])
        self.assertIn("horas_soporte_acumuladas", prediccion)

    def test_expone_contador_de_preventivos(self):
        # ViewDetails.vue: `activo.contador_preventivos`
        fila = self._fila()

        self.assertEqual(fila["contador_preventivos"], 3)

    def test_expone_al_custodio_actual_desde_la_designacion_activa(self):
        # Reportes.vue y Monitoreo.vue: `a.custodio_actual || 'Sin asignar'`
        from django.contrib.auth.models import User as Usuario

        activo = Activo.objects.create(
            codigo_tamep="SER-CUST",
            nombre_especifico="Equipo con custodio",
            serie="SN-SER-CUST",
            tipo_activo=self.tipo,
            ubicacion_base=self.ubicacion,
            ubicacion_actual=self.ubicacion,
            vida_util_estimada=60,
            situacion_activo="Asignado",
        )
        custodio = Usuario.objects.create_user(
            username="custodio_ser", password="x", first_name="Ana", last_name="Cruz"
        )
        gerencia = self.regional.gerencias.create(nombre="Gerencia Ser")
        cargo = gerencia.cargos.create(nombre="Cargo Ser")
        Designacion.objects.create(
            activo=activo,
            usuario=custodio,
            regional=self.regional,
            gerencia=gerencia,
            cargo=cargo,
            ubicacion=self.ubicacion,
            tipo="Permanente",
            esta_activa=True,
        )

        respuesta = self.client.get("/api/gestion-activos/")
        fila = next(a for a in respuesta.data if a["codigo_tamep"] == "SER-CUST")

        self.assertEqual(fila["custodio_actual"], "Ana Cruz")

    def test_sin_custodio_el_campo_queda_vacio(self):
        activo = Activo.objects.create(
            codigo_tamep="SER-SIN-CUST",
            nombre_especifico="Equipo en almacén",
            serie="SN-SER-SIN-CUST",
            tipo_activo=self.tipo,
            ubicacion_base=self.ubicacion,
            ubicacion_actual=self.ubicacion,
            vida_util_estimada=60,
        )

        respuesta = self.client.get("/api/gestion-activos/")
        fila = next(a for a in respuesta.data if a["codigo_tamep"] == "SER-SIN-CUST")

        self.assertIn(fila["custodio_actual"], (None, ""))
