from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
import qrcode
from io import BytesIO
from django.core.files import File
from PIL import Image
from django.core.exceptions import ValidationError
from smart_selects.db_fields import ChainedForeignKey
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import transaction


class Regional(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name = "Regional"
        verbose_name_plural = "Regionales"

    def __str__(self):
        return self.nombre


class Ubicacion(models.Model):
    class Meta:
        verbose_name = "Ubicación"
        verbose_name_plural = "Ubicaciones"

    nombre_sala = models.CharField(max_length=100)
    regional = models.ForeignKey(
        Regional, on_delete=models.CASCADE, related_name="ubicaciones"
    )
    altitud = models.IntegerField(null=True, blank=True)
    temperatura_avg = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    humedad_avg = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    def __str__(self):
        return f"{self.nombre_sala} ({self.regional.nombre})"


class Gerencia(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    regional = models.ForeignKey(
        Regional, on_delete=models.CASCADE, related_name="gerencias"
    )

    class Meta:
        unique_together = ("nombre", "regional")

    def __str__(self):
        return f"{self.nombre} - {self.regional.nombre}"


class Cargo(models.Model):
    nombre = models.CharField(max_length=100)
    gerencia = models.ForeignKey(
        Gerencia, on_delete=models.CASCADE, related_name="cargos"
    )

    class Meta:
        unique_together = ("nombre", "gerencia")
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"

    def __str__(self):
        return f"{self.nombre} ({self.gerencia.nombre})"


class GrupoContable(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    vida_util_anos = models.IntegerField(verbose_name="Vida Útil (Años)")
    coeficiente_depreciacion = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="Coeficiente % Anual"
    )

    class Meta:
        verbose_name = "Grupo Contable"
        verbose_name_plural = "Grupos Contables"

    tiene_mantenimiento_predictivo = models.BooleanField(
        default=False, verbose_name="¿Habilitar IA Predictiva?"
    )

    def __str__(self):
        return f"{self.nombre} ({self.vida_util_anos} años)"


class TipoActivo(models.Model):
    nombre = models.CharField(max_length=100)
    grupo_contable = models.ForeignKey(
        GrupoContable, on_delete=models.CASCADE, related_name="tipos"
    )

    class Meta:
        verbose_name_plural = "Tipos de Activos"
        unique_together = ("nombre", "grupo_contable")

    def __str__(self):
        return f"{self.nombre} ({self.grupo_contable.nombre})"


class PerfilUsuario(models.Model):
    ROLES = [
        ("admin_informatico", "Administrador Informático"),
        ("admin_principal", "Administrador Principal"),
        ("admin_regional", "Administrador Regional"),
        ("usuario", "Usuario"),
        ("consultor", "Consultor"),
    ]
    EXTENSIONES = [
        ("LP", "La Paz"),
        ("OR", "Oruro"),
        ("PT", "Potosí"),
        ("CB", "Cochabamba"),
        ("SC", "Santa Cruz"),
        ("BN", "Beni"),
        ("PA", "Pando"),
        ("TJ", "Tarija"),
        ("CH", "Chuquisaca"),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="perfil")
    rol = models.CharField(
        max_length=25, choices=ROLES, default="usuario", verbose_name="Rol del Sistema"
    )
    regional = models.ForeignKey(
        Regional, on_delete=models.SET_NULL, null=True, blank=True
    )
    gerencia = ChainedForeignKey(
        Gerencia,
        chained_field="regional",
        chained_model_field="regional",
        show_all=False,
        auto_choose=True,
        sort=True,
        null=True,
        blank=True,
    )
    cargo = ChainedForeignKey(
        Cargo,
        chained_field="gerencia",
        chained_model_field="gerencia",
        show_all=False,
        auto_choose=True,
        sort=True,
        null=True,
        blank=True,
    )
    ci = models.CharField(
        max_length=20, verbose_name="Cédula de Identidad", null=True, blank=True
    )
    extension = models.CharField(
        max_length=2,
        choices=EXTENSIONES,
        verbose_name="Extensión",
        null=True,
        blank=True,
    )

    telefono = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.ci} {self.extension}"


class Activo(models.Model):
    ESTADOS_FISICOS = [
        ("Bueno", "Bueno"),
        ("Regular", "Regular"),
        ("Malo", "Malo"),
    ]
    SITUACION_ACTIVO = [
        ("Disponible", "Disponible (No asignado)"),
        ("Asignado", "Asignado (En uso)"),
        ("Mantenimiento", "En Mantenimiento"),
        ("Baja", "Dado de Baja"),
    ]
    PERFILES_USO = [
        ("N/A", "No Aplica (Activo Administrativo)"),
        ("Oficina", "Oficina (8h/5d)"),
        ("Intensivo", "Intensivo / Desarrollo (12h/6d)"),
        ("Critico", "Crítico / Servidor (24h/7d)"),
    ]

    codigo_tamep = models.CharField(
        max_length=50, unique=True, verbose_name="Código TAMEP"
    )
    codigo_tab = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="Historico"
    )
    nombre_especifico = models.CharField(
        max_length=255, help_text="Ej: Dell Latitude 5420"
    )
    descripcion = models.TextField(
        blank=True, help_text="Descripción general del equipo"
    )
    especificaciones = models.TextField(
        blank=True, help_text="Componentes internos o extras"
    )
    serie = models.CharField(max_length=100, unique=True)
    fecha_adquisicion = models.DateField(null=True, blank=True)
    costo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    grupo_contable_seleccionado = models.ForeignKey(
        GrupoContable,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Grupo Contable (Filtro)",
    )
    tipo_activo = ChainedForeignKey(
        TipoActivo,
        chained_field="grupo_contable_seleccionado",
        chained_model_field="grupo_contable",
        show_all=False,
        auto_choose=True,
        sort=True,
        on_delete=models.PROTECT,
        null=True,
    )
    ubicacion_base = models.ForeignKey(
        Ubicacion,
        on_delete=models.SET_NULL,
        null=True,
        related_name="activos_base",
        verbose_name="Ubicación Base/Origen",
        help_text="Ubicación donde se registró el activo originalmente.",
    )
    ubicacion_actual = models.ForeignKey(
        Ubicacion,
        on_delete=models.SET_NULL,
        null=True,
        related_name="activos_actuales",
        verbose_name="Ubicación Actual",
        help_text="Ubicación donde se encuentra físicamente ahora.",
    )
    vida_util_estimada = models.IntegerField(help_text="Meses")
    estado_actual = models.CharField(
        max_length=20, choices=ESTADOS_FISICOS, default="Bueno"
    )
    situacion_activo = models.CharField(
        max_length=20, choices=SITUACION_ACTIVO, default="Disponible"
    )
    uso_inicial_estimado = models.FloatField(default=0.0)
    horas_uso_actual = models.FloatField(default=0.0)
    contador_fallas = models.IntegerField(default=0)
    imagen_activo = models.ImageField(upload_to="activos_fotos/", null=True, blank=True)
    imagen_sn = models.ImageField(
        upload_to="activos_fotos/", verbose_name="Imagen SN ", null=True, blank=True
    )
    imagen_lateral = models.ImageField(
        upload_to="activos_fotos/",
        verbose_name="Imagen Placa Técnica",
        null=True,
        blank=True,
    )
    imagen_qr = models.ImageField(upload_to="qrs/", null=True, blank=True)
    contador_correctivos = models.PositiveIntegerField(default=0)
    contador_preventivos = models.PositiveIntegerField(default=0)
    contador_servicios = models.PositiveIntegerField(default=0)
    contador_mejoras = models.PositiveIntegerField(default=0)
    fecha_registro = models.DateTimeField(
        auto_now_add=True, null=True, verbose_name="Fecha de Registro"
    )
    registrado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activos_registrados",
        verbose_name="Registrado por",
    )
    perfil_uso = models.CharField(
        max_length=20,
        choices=PERFILES_USO,
        default="N/A",
        help_text="Impacta directamente en el cálculo de desgaste de la IA",
    )

    def clean(self):
        super().clean()
        # Si el grupo contable NO tiene IA, el perfil DEBE ser 'N/A'
        if self.tipo_activo and self.tipo_activo.grupo_contable:
            tiene_ia = self.tipo_activo.grupo_contable.tiene_mantenimiento_predictivo

            if not tiene_ia and self.perfil_uso != "N/A":
                raise ValidationError(
                    {
                        "perfil_uso": "Este grupo contable no tiene IA activa. Debe seleccionar 'No Aplica'."
                    }
                )

            if tiene_ia and self.perfil_uso == "N/A":
                raise ValidationError(
                    {
                        "perfil_uso": "Este activo requiere un perfil de uso para el análisis de IA."
                    }
                )

    @property
    def grupo_contable_info(self):  # Cambia el nombre aquí
        return self.tipo_activo.grupo_contable if self.tipo_activo else None

    @property
    def vida_util_total_meses(self):
        """Calcula la vida útil total basada en el Grupo Contable (Años * 12)"""
        if self.tipo_activo and self.tipo_activo.grupo_contable:
            return self.tipo_activo.grupo_contable.vida_util_anos * 12
        return 0

    @property
    def meses_restantes(self):
        """Calcula cuántos meses de vida le quedan desde la fecha de adquisición"""
        from datetime import date
        from dateutil.relativedelta import relativedelta

        if self.fecha_adquisicion and self.vida_util_total_meses > 0:
            diferencia = relativedelta(date.today(), self.fecha_adquisicion)
            meses_transcurridos = (diferencia.years * 12) + diferencia.months
            restante = self.vida_util_total_meses - meses_transcurridos
            return max(0, restante)
        return 0

    @property
    def edad_ajustada_meses(self):
        """
        Calcula la edad real pero resta 'meses de vida' por cada mejora (Upgrade).
        Un equipo con 2 mejoras se considera 'más joven' para el Random Forest.
        """
        if self.fecha_adquisicion:
            diferencia = relativedelta(date.today(), self.fecha_adquisicion)
            meses_reales = (diferencia.years * 12) + diferencia.months

            # Cada mejora resta, por ejemplo, 6 meses de 'vejez' percibida
            meses_rejuvenecidos = self.contador_mejoras * 6
            edad_final = meses_reales - meses_rejuvenecidos

            return max(0, edad_final)
        return 0

    def puede_ser_asignado(self):
        return self.situacion_activo == "Disponible"

    def puede_ser_transferido(self):
        return self.situacion_activo == "Asignado"

    def puede_darse_de_baja(self):
        return self.situacion_activo in ["Disponible", "Asignado"]

    def __str__(self):
        tipo = self.tipo_activo.nombre if self.tipo_activo else "Sin Tipo"
        return f"[{tipo}] {self.nombre_especifico} - {self.codigo_tamep}"

    def cambiar_estado(self, nuevo_estado, nueva_ubicacion=None):
        self.situacion_activo = nuevo_estado
        if nueva_ubicacion:
            self.ubicacion_actual = nueva_ubicacion
        if nuevo_estado == "Disponible" and self.ubicacion_base:
            self.ubicacion_actual = self.ubicacion_base
        self.save()

    def save(self, *args, **kwargs):
        with transaction.atomic():
            es_ia = (
                self.tipo_activo
                and self.tipo_activo.grupo_contable.tiene_mantenimiento_predictivo
            )
            if not es_ia:
                # 1. Forzamos valores administrativos simples
                self.perfil_uso = "N/A"
                self.horas_uso_actual = 0.0
                self.contador_fallas = 0
                # 2. Si por algún error existen métricas, las borramos
                if self.pk:
                    MetricaPredictiva.objects.filter(activo=self).delete()

            if self.tipo_activo and self.tipo_activo.grupo_contable:
                self.vida_util_estimada = (
                    self.tipo_activo.grupo_contable.vida_util_anos * 12
                )
            else:
                self.vida_util_estimada = 0

            # 2. LÓGICA DE UBICACIÓN INICIAL
            if not self.pk and self.ubicacion_base:
                self.ubicacion_actual = self.ubicacion_base

            # 3. DETECCIÓN DE CAMBIO DE CÓDIGO TAMEP (Para el QR)
            if self.pk:
                try:
                    old_instance = Activo.objects.get(pk=self.pk)
                    if old_instance.codigo_tamep != self.codigo_tamep:
                        # Si el código cambió, borramos el QR viejo para regenerarlo
                        if self.imagen_qr:
                            self.imagen_qr.delete(save=False)
                        self.imagen_qr = None
                except Activo.DoesNotExist:
                    pass

            # 4. GENERACIÓN O REGENERACIÓN DEL QR
            if not self.imagen_qr:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                url_acceso = f"{settings.BASE_URL}/activo/detalle/{self.codigo_tamep}/"

                qr.add_data(url_acceso)
                qr.make(fit=True)

                img = qr.make_image(fill_color="black", back_color="white")
                buffer = BytesIO()
                img.save(buffer, format="PNG")

                fname = f"qr-{self.codigo_tamep}.png"
                self.imagen_qr.save(fname, File(buffer), save=False)

            # 5. GUARDADO FINAL
            super().save(*args, **kwargs)


class Designacion(models.Model):
    TIPOS = [
        ("Permanente", "Asignación Permanente (Cargo)"),
        ("Temporal", "Préstamo Temporal"),
    ]

    grupo_contable = models.ForeignKey(
        GrupoContable,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Filtrar por Grupo",
    )

    tipo_activo_filtro = ChainedForeignKey(
        TipoActivo,
        chained_field="grupo_contable",
        chained_model_field="grupo_contable",
        show_all=False,
        auto_choose=True,
        sort=True,
        null=True,
        blank=True,
    )

    activo = ChainedForeignKey(
        Activo,
        chained_field="tipo_activo_filtro",
        chained_model_field="tipo_activo",
        show_all=False,
        auto_choose=True,
        sort=True,
        on_delete=models.CASCADE,
        related_name="designaciones",
    )
    regional = models.ForeignKey(Regional, on_delete=models.CASCADE)
    gerencia = models.ForeignKey(
        Gerencia, on_delete=models.SET_NULL, null=True, blank=True
    )

    cargo = ChainedForeignKey(
        Cargo,
        chained_field="gerencia",
        chained_model_field="gerencia",
        show_all=False,
        auto_choose=True,
        sort=True,
    )
    usuario = ChainedForeignKey(
        User,
        chained_field="cargo",
        chained_model_field="perfil__cargo",
        show_all=False,
        auto_choose=True,
        sort=True,
    )
    ubicacion = ChainedForeignKey(
        Ubicacion,
        chained_field="regional",
        chained_model_field="regional",
        show_all=False,
        auto_choose=True,
    )

    tipo = models.CharField(max_length=20, choices=TIPOS, default="Permanente")
    esta_activa = models.BooleanField(
        default=True,
        help_text="Desmarcar manualmente solo para devoluciones sin transferencia.",
    )
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    fecha_fin_estimada = models.DateTimeField(
        null=True, blank=True, verbose_name="Fecha Devolución (Solo Temporal)"
    )
    fecha_fin_real = models.DateTimeField(null=True, blank=True)

    observaciones = models.TextField(blank=True, null=True)
    motivo_cambio_o_baja = models.CharField(max_length=255, blank=True, null=True)
    documento_respaldo = models.FileField(
        upload_to="documentos_designaciones/", null=True, blank=True
    )
    num_acta = models.CharField(
        max_length=50,
        unique=False,
        null=True,
        blank=True,
        verbose_name="Nro. Correlativo de Baja",
    )

    class Meta:
        verbose_name = "Designación / Préstamo"
        verbose_name_plural = "Designaciones"
        ordering = ["-fecha_inicio"]

    def __str__(self):
        return f"{self.tipo} - {self.activo.codigo_tamep} -> {self.usuario.username}"

    def clean(self):
        """Validaciones de Negocio Simplificadas"""
        super().clean()
        if hasattr(self, "activo") and self.activo:
            if self.tipo == "Temporal" and not self.fecha_fin_estimada:
                raise ValidationError(
                    {
                        "fecha_fin_estimada": "Para préstamos temporales, la fecha de devolución es obligatoria."
                    }
                )
            if not self.pk and self.esta_activa:
                if self.activo.situacion_activo == "Asignado":
                    raise ValidationError(
                        f"El activo {self.activo.codigo_tamep} ya está asignado. Debe realizar una DEVOLUCIÓN o TRANSFERENCIA primero."
                    )
                if self.activo.situacion_activo == "Baja":
                    raise ValidationError(f"No puede asignar un activo dado de BAJA.")

    def save(self, *args, **kwargs):
        from django.utils import timezone

        if not hasattr(self, "activo") or self.activo is None:
            return super().save(*args, **kwargs)

        with transaction.atomic():
            if self.esta_activa:
                self.activo.cambiar_estado("Asignado", self.ubicacion)
                if not self.activo.ubicacion_base:
                    self.activo.ubicacion_base = self.ubicacion
            else:
                if not self.fecha_fin_real:
                    self.fecha_fin_real = timezone.now()
                if self.activo.situacion_activo != "Baja":
                    self.activo.cambiar_estado("Disponible")
                    if self.activo.ubicacion_base:
                        self.activo.ubicacion_actual = self.activo.ubicacion_base

        super().save(*args, **kwargs)


class Transferencia(models.Model):
    TIPO_MOVIMIENTO = [
        ("TR", "Transferencia entre Funcionarios"),
        ("DE", "Devolución a Almacén"),
    ]

    grupo_contable = models.ForeignKey(
        GrupoContable, on_delete=models.SET_NULL, null=True, blank=True
    )
    tipo_activo_filtro = ChainedForeignKey(
        TipoActivo,
        chained_field="grupo_contable",
        chained_model_field="grupo_contable",
        show_all=False,
        auto_choose=True,
        sort=True,
        null=True,
        blank=True,
    )
    activo = ChainedForeignKey(
        Activo,
        chained_field="tipo_activo_filtro",
        chained_model_field="tipo_activo",
        show_all=False,
        auto_choose=True,
        sort=True,
        on_delete=models.CASCADE,
    )

    reg_emisor = models.ForeignKey(
        Regional,
        on_delete=models.PROTECT,
        related_name="trans_reg_emisor",
        verbose_name="Regional Emisor",
        null=True,
    )
    ger_emisor = ChainedForeignKey(
        Gerencia,
        chained_field="reg_emisor",
        chained_model_field="regional",
        related_name="trans_ger_emisor",
        null=True,
    )
    car_emisor = ChainedForeignKey(
        Cargo,
        chained_field="ger_emisor",
        chained_model_field="gerencia",
        related_name="trans_car_emisor",
        null=True,
    )
    emisor = ChainedForeignKey(
        User,
        chained_field="car_emisor",
        chained_model_field="perfil__cargo",
        related_name="transferencias_enviadas",
    )

    reg_receptor = models.ForeignKey(
        Regional,
        on_delete=models.PROTECT,
        related_name="trans_reg_receptor",
        verbose_name="Regional Receptor",
        null=True,
    )
    ger_receptor = ChainedForeignKey(
        Gerencia,
        chained_field="reg_receptor",
        chained_model_field="regional",
        related_name="trans_ger_receptor",
        null=True,
    )
    car_receptor = ChainedForeignKey(
        Cargo,
        chained_field="ger_receptor",
        chained_model_field="gerencia",
        related_name="trans_car_receptor",
        null=True,
    )
    receptor = ChainedForeignKey(
        User,
        chained_field="car_receptor",
        chained_model_field="perfil__cargo",
        related_name="transferencias_recibidas",
    )

    tipo = models.CharField(max_length=2, choices=TIPO_MOVIMIENTO, default="TR")
    ubicacion_origen = models.ForeignKey(
        Ubicacion,
        on_delete=models.PROTECT,
        related_name="transferencias_origen",
        null=True,
        blank=True,
    )
    ubicacion_destino = models.ForeignKey(
        Ubicacion,
        on_delete=models.PROTECT,
        help_text="Nueva ubicación física del activo",
    )
    fecha = models.DateTimeField(auto_now_add=True)
    num_acta = models.CharField(
        max_length=50, unique=True, verbose_name="Nro. Acta de Transferencia"
    )
    motivo = models.TextField()
    documento_respaldo = models.FileField(
        upload_to="transferencias_docs/", null=True, blank=True
    )

    contador_correctivos = models.PositiveIntegerField(default=0)
    contador_preventivos = models.PositiveIntegerField(default=0)
    contador_servicios = models.PositiveIntegerField(default=0)
    contador_mejoras = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Transferencia"
        verbose_name_plural = "Transferencias"

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if self.activo:
            asignacion_actual = Designacion.objects.filter(
                activo=self.activo, esta_activa=True
            ).first()
            if not asignacion_actual:
                raise ValidationError(
                    f"El activo '{self.activo}' no tiene asignación activa."
                )
            if self.emisor and self.emisor != asignacion_actual.usuario:
                raise ValidationError(
                    f"El activo pertenece a '{asignacion_actual.usuario}', no a '{self.emisor}'."
                )

    def save(self, *args, **kwargs):

        if self.emisor and not self.car_emisor:
            perfil = self.emisor.perfil
            self.car_emisor = perfil.cargo
            self.ger_emisor = perfil.gerencia
            self.reg_emisor = perfil.regional

        self.full_clean()

        if not self.ubicacion_origen:
            self.ubicacion_origen = self.activo.ubicacion_actual

        with transaction.atomic():
            super().save(*args, **kwargs)

            activo = self.activo
            if self.tipo == "DE":
                activo.cambiar_estado("Disponible")
            else:
                activo.cambiar_estado("Asignado", self.ubicacion_destino)

            from django.utils import timezone

            Designacion.objects.filter(activo=activo, esta_activa=True).update(
                esta_activa=False,
                fecha_fin_real=timezone.now(),
                motivo_cambio_o_baja=f"Transferencia {self.tipo} - Acta {self.num_acta}",
            )

            if self.tipo == "TR" and self.receptor:
                Designacion.objects.create(
                    activo=activo,
                    usuario=self.receptor,
                    regional=self.reg_receptor,
                    gerencia=self.ger_receptor,
                    cargo=self.car_receptor,
                    ubicacion=self.ubicacion_destino,
                    tipo="Permanente",
                    esta_activa=True,
                    num_acta=self.num_acta,
                )


class SolicitudServicio(models.Model):
    TIPOS = [
        ("MANTENIMIENTO", "Mantenimiento"),
        ("SERVICIO", "Servicio Técnico"),
        ("AYUDA", "Ayudantía / Soporte"),
    ]
    SEVERIDAD_USUARIO = [
        ("1", "Baja - El equipo funciona con limitaciones"),
        ("2", "Media - Afecta mis tareas principales"),
        ("3", "Alta - No puedo trabajar / Equipo inoperativo"),
    ]
    activo = models.ForeignKey(
        Activo, on_delete=models.CASCADE, related_name="solicitudes"
    )
    solicitante = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="mis_solicitudes"
    )
    tipo_solicitud = models.CharField(
        max_length=20, choices=TIPOS, default="MANTENIMIENTO"
    )
    severidad = models.CharField(max_length=1, choices=SEVERIDAD_USUARIO, default="2")
    descripcion_problema = models.TextField(verbose_name="Descripción del Problema")
    requerimiento = models.TextField(verbose_name="¿Qué solicita?")
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    num_ticket = models.CharField(
        max_length=50, unique=True, null=True, blank=True, verbose_name="Nro. de Ticket"
    )

    class Meta:
        db_table = "activos_solicitudservicio"
        verbose_name = "Solicitud de Servicio"
        ordering = ["-severidad", "fecha_solicitud"]

    def __str__(self):
        return f"{self.num_ticket} | {self.activo.codigo_tamep} - {self.get_tipo_solicitud_display()}"

    @property
    def estado_actual(self):
        intervencion = self.intervenciones.last()
        if not intervencion:
            return "Pendiente"
        if not intervencion.fecha_fin:
            return "En Proceso"
        return "Cerrado"

    def save(self, *args, **kwargs):
        # Si es una nueva solicitud y no tiene ticket, lo generamos
        if not self.num_ticket:
            from django.utils import timezone

            anio = timezone.now().year

            # Usamos la misma lógica centralizada: TKT-2026-XXXX
            ultimo = SolicitudServicio.objects.filter(
                num_ticket__contains=f"-{anio}-"
            ).aggregate(models.Max("num_ticket"))["num_ticket__max"]

            if ultimo:
                import re

                match = re.search(r"-(\d+)$", ultimo)
                num = int(match.group(1)) + 1 if match else 1
            else:
                num = 1

            self.num_ticket = f"TKT-{anio}-{str(num).zfill(4)}"

        super().save(*args, **kwargs)


class HistorialEstadoActivo(models.Model):
    activo = models.ForeignKey(Activo, on_delete=models.CASCADE)
    estado = models.CharField(max_length=20)
    fecha = models.DateTimeField(auto_now_add=True)
    observacion = models.TextField(blank=True)


# --- 5. Intervenciones ---
class Intervencion(models.Model):
    TIPOS = [
        ("Preventivo", "Mantenimiento Preventivo"),
        ("Correctivo", "Mantenimiento Correctivo"),
        ("Servicio", "Servicio Técnico / Soporte"),
        ("Mejora", "Mejora / Actualización (Upgrade)"),
    ]
    CATEGORIAS = [("Hardware", "Hardware"), ("Software", "Software"), ("Otro", "Otro")]
    MODALIDAD = [
        ("Sitio", "Mantenimiento en Sitio"),
        ("Taller", "Mantenimiento en Taller"),
    ]
    ESTADO_RESULTANTE = [
        ("Bueno", "Bueno"),
        ("Regular", "Regular"),
        ("Malo", "Malo"),
        ("Baja", "Sugerir Baja"),
    ]
    solicitud = models.ForeignKey(
        "SolicitudServicio", on_delete=models.CASCADE, related_name="intervenciones"
    )
    tecnico = models.ForeignKey(User, on_delete=models.CASCADE)
    activo = models.ForeignKey(
        "Activo", on_delete=models.CASCADE, related_name="intervenciones"
    )
    tipo_mantenimiento = models.CharField(max_length=20, choices=TIPOS)
    categoria_falla = models.CharField(
        max_length=20, choices=CATEGORIAS, default="Hardware"
    )
    modalidad = models.CharField(max_length=10, choices=MODALIDAD, default="Sitio")
    diagnostico_previo = models.TextField(
        help_text="Diagnóstico previo y/o servicio requerido"
    )
    detalles_reparacion = models.TextField(
        help_text="Descripción técnica del trabajo realizado"
    )
    recomendacion_tecnica = models.TextField(blank=True, null=True)
    observaciones_entrega = models.TextField(blank=True, null=True)
    verificado_por = models.CharField(max_length=100)
    conclusion = models.TextField(blank=True, null=True)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    lectura_uso_equipo = models.FloatField(
        help_text="Horas de uso registradas en este momento"
    )
    costo_materiales = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    severidad_falla = models.IntegerField(
        default=1, choices=[(i, i) for i in range(1, 6)]
    )
    estado_post_intervencion = models.CharField(
        max_length=20, choices=ESTADO_RESULTANTE, default="Bueno"
    )

    class Meta:
        db_table = "intervencion"
        verbose_name = "Intervención"
        verbose_name_plural = "Intervenciones"

    def __str__(self):
        return f"{self.tipo_mantenimiento} - {self.activo.codigo_tamep} ({self.fecha_fin.date()})"

    def clean(self):
        super().clean()
        if self.activo and self.lectura_uso_equipo < self.activo.horas_uso_actual:
            raise ValidationError(
                f"La lectura de uso ({self.lectura_uso_equipo}) no puede ser menor a la actual ({self.activo.horas_uso_actual} hrs)."
            )

    def save(self, *args, **kwargs):
        """
        Los contadores del Activo se incrementan y se PERSISTEN aquí (y solo
        aquí). La señal actualizar_ia_por_intervencion() se limita a recalcular
        métricas e IA, así no hay doble conteo.
        """
        es_nueva = not self.pk
        self.full_clean()
        with transaction.atomic():
            if es_nueva:
                self._incrementar_contadores_activo()
            super().save(*args, **kwargs)

    def _incrementar_contadores_activo(self):
        """
        Única fuente de verdad del efecto de una intervención sobre el Activo:
        contadores por tipo, fallas acumuladas y horas de uso.
        """
        activo = self.activo

        if self.tipo_mantenimiento == "Correctivo":
            activo.contador_correctivos += 1
            activo.contador_fallas += 1
        elif self.tipo_mantenimiento == "Preventivo":
            activo.contador_preventivos += 1
        elif self.tipo_mantenimiento == "Servicio":
            activo.contador_servicios += 1
        elif self.tipo_mantenimiento == "Mejora":
            activo.contador_mejoras += 1

        if self.lectura_uso_equipo > activo.horas_uso_actual:
            activo.horas_uso_actual = self.lectura_uso_equipo

        activo.save()


class MetricaPredictiva(models.Model):
    activo = models.OneToOneField(
        "Activo", on_delete=models.CASCADE, related_name="prediccion"
    )
    mtbf = models.FloatField(default=0.0)
    mttr = models.FloatField(default=0.0)
    rul = models.FloatField(default=0.0)
    probabilidad_falla = models.FloatField(
        default=0.0, verbose_name="Probabilidad de Falla (%)"
    )
    indice_salud_fuzzy = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.0
    )
    horas_soporte_acumuladas = models.FloatField(
        default=0.0, help_text="Total de horas hombre invertidas en este equipo"
    )
    patron_falla_detectado = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Ej: Sobrecalentamiento, Disco Duro, etc.",
    )
    recomendacion_ia = models.TextField(blank=True, null=True)
    ultima_actualizacion = models.DateTimeField(auto_now=True)

    def generar_recomendacion_poa(self):
        """
        Genera el texto prescriptivo basado en el perfil y las mejoras
        """
        riesgo = self.obtener_nivel_riesgo()

        if riesgo == "CRÍTICO":
            if self.activo.contador_mejoras >= 2:
                return "SUGERENCIA: Reemplazo inmediato. A pesar de las mejoras realizadas, el equipo ha llegado a su límite de fatiga técnica."
            else:
                return "SUGERENCIA: Evaluar Upgrade de componentes críticos antes de considerar la baja definitiva."

        if self.activo.perfil_uso == "Critico" and self.indice_salud_fuzzy < 60:
            return "ALERTA: Equipo de uso 24/7 con salud degradada. Programar mantenimiento preventivo urgente."

        return "ESTADO OPTIMO: Continuar con el ciclo de mantenimiento preventivo estandar."

    def calcular_saturacion_tecnica(self):
        """
        Determina si el equipo consume demasiado tiempo del personal (MTTR vs MTBF)
        """
        if self.mtbf > 0:
            ratio = self.mttr / self.mtbf
            if ratio > 0.10:
                return True
        return False

    def obtener_nivel_riesgo(self):
        prob = float(self.probabilidad_falla)
        if prob > 80:
            return "CRÍTICO"
        if prob > 50:
            return "MODERADO"
        return "BAJO"

    def actualizar_horas_soporte(self):
        """
        Suma todas las horas invertidas en intervenciones
        """
        intervenciones = self.activo.intervenciones.all()
        total_segundos = sum(
            [(i.fecha_fin - i.fecha_inicio).total_seconds() for i in intervenciones]
        )
        self.horas_soporte_acumuladas = total_segundos / 3600
        self.save()


class BajaActivo(models.Model):
    MOTIVOS = [
        ("Obsolescencia", "Obsolescencia Tecnológica"),
        ("Daño", "Daño Irreparable / Siniestro"),
        ("Perdida", "Pérdida o Robo"),
    ]
    activo = models.OneToOneField(
        Activo, on_delete=models.PROTECT, related_name="baja_registro"
    )
    solicitante = models.ForeignKey(
        User, on_delete=models.PROTECT, help_text="Quien autoriza o solicita la baja"
    )
    num_baja = models.CharField(
        max_length=50, unique=True, verbose_name="Nro. Correlativo de Baja"
    )
    fecha = models.DateTimeField(auto_now_add=True)
    motivo = models.TextField(verbose_name="Motivos de la Baja")
    descripcion_tecnica = models.TextField(
        help_text="Justificación técnica (Informe de obsolescencia o denuncia policial)."
    )
    documento_respaldo = models.FileField(
        upload_to="bajas_docs/", help_text="PDF del informe técnico o denuncia."
    )
    num_baja = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Nro. Correlativo de Baja",
    )

    class Meta:
        verbose_name = "Baja de Activo"
        verbose_name_plural = "Bajas de Activos"

    def __str__(self):
        return f"BAJA: {self.activo.codigo_tamep} ({self.num_baja})"

    def save(self, *args, **kwargs):
        from django.utils import timezone

        with transaction.atomic():
            super().save(*args, **kwargs)

            Designacion.objects.filter(activo=self.activo, esta_activa=True).update(
                esta_activa=False,
                fecha_fin_real=timezone.now(),
                observaciones=f"CIERRE POR BAJA - REF: {self.num_baja}",
            )

            # 3. Actualizamos el activo una sola vez
            self.activo.situacion_activo = "Baja"
            self.activo.estado_actual = "Malo"
            self.activo.ubicacion_actual = None  # Sale de la sala física
            self.activo.save()


class Notificacion(models.Model):
    TIPOS = [
        ("registro", "Nueva Solicitud de Registro"),
        ("solicitud", "Nueva Solicitud de Mantenimiento"),
        ("mantenimiento", "Mantenimiento Atendido"),
    ]
    destinatario = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notificaciones"
    )
    tipo = models.CharField(max_length=20, choices=TIPOS)
    titulo = models.CharField(max_length=255)
    mensaje = models.TextField()
    url = models.CharField(
        max_length=500, blank=True, help_text="URL frontend a donde redirigir"
    )
    leida = models.BooleanField(default=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"[{self.get_tipo_display()}] -> {self.destinatario.username}: {self.titulo}"
