from rest_framework import serializers
from .models import (
    Activo,
    SolicitudServicio,
    GrupoContable,
    TipoActivo,
    Transferencia,
    Ubicacion,
    Designacion,
    User,
    PerfilUsuario,
    Regional,
    Gerencia,
    Cargo,
    BajaActivo,
    Intervencion,
    MetricaPredictiva,
    Notificacion,
)
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.utils import timezone
# --- 1. SERIALIZADORES AUXILIARES (Para Selectores) ---


class RegionalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Regional
        fields = ["id", "nombre"]


class UbicacionSerializer(serializers.ModelSerializer):
    regional_nombre = serializers.CharField(source="regional.nombre", read_only=True)

    class Meta:
        model = Ubicacion
        fields = ["id", "nombre_sala", "regional", "regional_nombre"]


class GerenciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gerencia
        fields = ["id", "nombre", "regional"]


class CargoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cargo
        fields = ["id", "nombre", "gerencia"]


class GrupoContableSerializer(serializers.ModelSerializer):
    class Meta:
        model = GrupoContable
        fields = ["id", "nombre", "vida_util_anos", "tiene_mantenimiento_predictivo"]


class TipoActivoSerializer(serializers.ModelSerializer):
    grupo_nombre = serializers.CharField(source="grupo_contable.nombre", read_only=True)

    class Meta:
        model = TipoActivo
        fields = "__all__"


class UserProfileSerializer(serializers.ModelSerializer):
    # Campos del perfil (aplanados)
    ci = serializers.CharField(source="perfil.ci", read_only=True)
    extension = serializers.CharField(source="perfil.extension", read_only=True)
    # Quitamos la validación automática para manejarlo manualmente o permitir vacíos
    telefono = serializers.CharField(
        source="perfil.telefono", required=False, allow_blank=True
    )

    cargo_nombre = serializers.CharField(source="perfil.cargo.nombre", read_only=True)
    regional_nombre = serializers.CharField(
        source="perfil.regional.nombre", read_only=True
    )
    gerencia_nombre = serializers.CharField(
        source="perfil.gerencia.nombre", read_only=True
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "ci",
            "extension",
            "telefono",
            "cargo_nombre",
            "regional_nombre",
            "gerencia_nombre",
        ]
        # Esto evita que Django se queje de que el username ya existe al editar tu propio perfil
        extra_kwargs = {"username": {"validators": []}, "email": {"validators": []}}


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        # Permitir login con email: si el username contiene '@', buscar el username real
        username = attrs.get("username", "")
        if "@" in username:
            try:
                user_obj = User.objects.get(email=username)
                attrs["username"] = user_obj.username
            except User.DoesNotExist:
                pass  # Dejar que simplejwt maneje el error
        data = super().validate(attrs)
        user = self.user

        # Buscamos el cargo en el PerfilUsuario
        # Usamos un valor por defecto por si el usuario aún no tiene perfil
        cargo_nombre = "Personal TAMEP"
        if hasattr(user, "perfil") and user.perfil.cargo:
            cargo_nombre = user.perfil.cargo.nombre

        # Rol del sistema
        rol = "usuario"
        regional_id = None
        if hasattr(user, "perfil"):
            rol = user.perfil.rol
            regional_id = user.perfil.regional_id

        # Esta es la estructura que recibirá tu Login.vue
        data["user"] = {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "nombre_completo": f"{user.first_name} {user.last_name}",
            "cargo_nombre": cargo_nombre,
            "es_admin": user.is_staff or user.is_superuser,
            "rol": rol,
            "regional_id": regional_id,
        }
        return data


# --- REGISTRO DE USUARIOS ---


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirmation = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "password_confirmation",
            "first_name",
            "last_name",
        ]

    def validate_email(self, value):
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta con este correo electrónico."
            )
        return value

    def validate(self, data):
        confirmation = data.get("password_confirmation")
        if confirmation is not None and data["password"] != confirmation:
            raise serializers.ValidationError(
                {"password_confirmation": "Las contraseñas no coinciden."}
            )
        return data

    def create(self, validated_data):
        validated_data.pop("password_confirmation", None)
        user = User(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            is_active=False,
        )
        user.set_password(validated_data["password"])
        user.save()
        return user


class UserAdminSerializer(serializers.ModelSerializer):
    cargo_nombre = serializers.CharField(
        source="perfil.cargo.nombre", read_only=True, default="Sin asignar"
    )
    regional_nombre = serializers.CharField(
        source="perfil.regional.nombre", read_only=True, default="Sin asignar"
    )
    gerencia_nombre = serializers.CharField(
        source="perfil.gerencia.nombre", read_only=True, default="Sin asignar"
    )

    rol = serializers.CharField(source="perfil.rol", required=False)
    regional_id = serializers.IntegerField(
        source="perfil.regional_id", required=False, allow_null=True
    )
    gerencia_id = serializers.IntegerField(
        source="perfil.gerencia_id", required=False, allow_null=True
    )
    cargo_id = serializers.IntegerField(
        source="perfil.cargo_id", required=False, allow_null=True
    )
    ci = serializers.CharField(
        source="perfil.ci", required=False, allow_blank=True, allow_null=True
    )
    extension = serializers.CharField(
        source="perfil.extension", required=False, allow_blank=True, allow_null=True
    )
    telefono = serializers.CharField(
        source="perfil.telefono", required=False, allow_blank=True
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "is_staff",
            "date_joined",
            "cargo_nombre",
            "regional_nombre",
            "gerencia_nombre",
            "rol",
            "regional_id",
            "gerencia_id",
            "cargo_id",
            "ci",
            "extension",
            "telefono",
            "password",
        ]
        read_only_fields = ["id", "date_joined"]
        extra_kwargs = {"password": {"write_only": True}}

    def create(self, validated_data):
        perfil_data = validated_data.pop("perfil", {})
        password = validated_data.pop("password", None)
        if "is_active" not in validated_data:
            validated_data["is_active"] = True
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_password(User.objects.make_random_password())
        user.save()
        perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
        for attr, value in perfil_data.items():
            setattr(perfil, attr, value)
        if not perfil.rol:
            perfil.rol = "usuario"
        perfil.save()
        return user

    def update(self, instance, validated_data):
        perfil_data = validated_data.pop("perfil", {})
        instance = super().update(instance, validated_data)
        if perfil_data:
            perfil, _ = PerfilUsuario.objects.get_or_create(user=instance)
            for attr, value in perfil_data.items():
                setattr(perfil, attr, value)
            perfil.save()
        return instance


# --- 3. METRICAS E IA (Corazón de la Tesis) ---


class MetricaPredictivaSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricaPredictiva
        fields = [
            "mtbf",
            "mttr",
            "probabilidad_falla",
            "indice_salud_fuzzy",
            "recomendacion_ia",
            "horas_soporte_acumuladas",
        ]


# --- 4. ACTIVO (Núcleo) ---


class ActivoSerializer(serializers.ModelSerializer):
    tipo_nombre = serializers.CharField(source="tipo_activo.nombre", read_only=True)
    grupo_nombre = serializers.CharField(
        source="tipo_activo.grupo_contable.nombre", read_only=True
    )
    ubicacion_nombre = serializers.CharField(
        source="ubicacion_actual.nombre_sala", read_only=True
    )
    regional_nombre = serializers.CharField(
        source="ubicacion_actual.regional.nombre", read_only=True
    )

    prediccion = MetricaPredictivaSerializer(read_only=True)

    # Contrato del frontend (RealizarBaja.vue): precarga la regional del activo
    # desde su ubicación actual ('regional' es el ID de la Regional).
    ubicacion_actual_detalle = serializers.SerializerMethodField()

    vida_util_total_meses = serializers.ReadOnlyField()
    meses_restantes = serializers.ReadOnlyField()
    edad_ajustada_meses = serializers.ReadOnlyField()

    def get_ubicacion_actual_detalle(self, obj):
        if not obj.ubicacion_actual:
            return None
        ubicacion = obj.ubicacion_actual
        return {
            "id": ubicacion.id,
            "nombre_sala": ubicacion.nombre_sala,
            "regional": ubicacion.regional_id,
            "regional_nombre": ubicacion.regional.nombre,
        }

    class Meta:
        model = Activo
        fields = "__all__"
        read_only_fields = [
            "imagen_qr",
            "vida_util_estimada",
            "horas_uso_actual",
            "contador_fallas",
            "contador_correctivos",
            "contador_preventivos",
            "contador_servicios",
            "contador_mejoras",
            "prediccion",
        ]

    def validate_codigo_tamep(self, value):
        qs = Activo.objects.filter(codigo_tamep=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Este Código TAMEP ya existe.")
        return value


# --- 5. GESTIÓN DE MOVIMIENTOS ---


class DesignacionSerializer(serializers.ModelSerializer):
    nombre_activo = serializers.ReadOnlyField(source="activo.nombre_especifico")
    codigo_tamep = serializers.ReadOnlyField(source="activo.codigo_tamep")
    nombre_usuario = serializers.ReadOnlyField(source="usuario.get_full_name")
    nombre_ubicacion = serializers.ReadOnlyField(source="ubicacion.nombre_sala")
    nombre_regional = serializers.ReadOnlyField(source="regional.nombre")

    class Meta:
        model = Designacion
        fields = "__all__"

    def validate_activo(self, value):
        """
        Validación Robusta: No basta con que exista, debe estar DISPONIBLE.
        """
        if self.instance is None:
            if value.situacion_activo != "Disponible":
                raise serializers.ValidationError(
                    f"El activo {value.codigo_tamep} no está disponible. Estado actual: {value.situacion_activo}"
                )
        return value

    def validate(self, data):
        fecha_inicio = data.get("fecha_inicio", timezone.now().date())
        fecha_fin = data.get("fecha_fin_estimada")

        if fecha_fin and fecha_fin < fecha_inicio:
            raise serializers.ValidationError(
                {
                    "fecha_fin_estimada": "La fecha de devolución no puede ser anterior a la entrega."
                }
            )

        if data.get("tipo") == "Temporal" and not fecha_fin:
            raise serializers.ValidationError(
                {"fecha_fin_estimada": "Obligatoria para préstamos temporales."}
            )

        return data


# --- 6. GESTIÓN DE TRANSFERENCIAS ---
class TransferenciaSerializer(serializers.ModelSerializer):
    nombre_emisor = serializers.ReadOnlyField(source="emisor.get_full_name")
    nombre_receptor = serializers.ReadOnlyField(source="receptor.get_full_name")
    nombre_activo = serializers.ReadOnlyField(source="activo.nombre_especifico")
    codigo_tamep = serializers.ReadOnlyField(source="activo.codigo_tamep")
    origen_nombre = serializers.ReadOnlyField(source="ubicacion_origen.nombre_sala")
    destino_nombre = serializers.ReadOnlyField(source="ubicacion_destino.nombre_sala")

    class Meta:
        model = Transferencia
        fields = "__all__"
        read_only_fields = ["fecha"]

    def validate(self, data):
        activo = data.get("activo")
        emisor = data.get("emisor")
        receptor = data.get("receptor")
        if emisor == receptor:
            raise serializers.ValidationError(
                {"receptor": "El receptor no puede ser la misma persona que el emisor."}
            )
        custodia_actual = Designacion.objects.filter(
            activo=activo, usuario=emisor, esta_activa=True
        ).exists()

        if not custodia_actual:
            raise serializers.ValidationError(
                {
                    "emisor": f"El funcionario {emisor.get_full_name()} no es el custodio legal actual de este activo."
                }
            )

        return data


class BajaActivoSerializer(serializers.ModelSerializer):
    nombre_activo = serializers.ReadOnlyField(source="activo.nombre_especifico")
    codigo_tamep = serializers.ReadOnlyField(source="activo.codigo_tamep")
    nombre_solicitante = serializers.ReadOnlyField(source="solicitante.get_full_name")

    class Meta:
        model = BajaActivo
        fields = "__all__"
        read_only_fields = ["fecha"]

    def validate_activo(self, value):
        """
        Validación Crítica: Un activo no puede morir dos veces.
        """
        if value.situacion_activo == "Baja":
            raise serializers.ValidationError(
                "Este activo ya ha sido desincorporado del sistema."
            )
        return value


# --- 7. MANTENIMIENTO Y SOPORTE ---


class SolicitudServicioSerializer(serializers.ModelSerializer):
    activo_nombre = serializers.ReadOnlyField(source="activo.nombre_especifico")
    activo_codigo = serializers.ReadOnlyField(source="activo.codigo_tamep")
    solicitante_nombre = serializers.ReadOnlyField(source="solicitante.get_full_name")
    estado_texto = serializers.SerializerMethodField()

    class Meta:
        model = SolicitudServicio
        fields = "__all__"
        read_only_fields = ["fecha_solicitud", "solicitante", "num_ticket"]

    def get_estado_texto(self, obj):
        if not obj.intervenciones.exists():
            return "Pendiente"
        if obj.intervenciones.filter(fecha_fin__isnull=True).exists():
            return "En Proceso"
        return "Cerrado"


class IntervencionSerializer(serializers.ModelSerializer):
    tecnico_nombre = serializers.ReadOnlyField(source="tecnico.get_full_name")
    activo_nombre = serializers.ReadOnlyField(source="activo.nombre_especifico")
    activo_codigo = serializers.ReadOnlyField(source="activo.codigo_tamep")

    class Meta:
        model = Intervencion
        fields = "__all__"
        read_only_fields = ["tecnico"]

    def validate(self, data):
        if (
            data.get("fecha_fin")
            and data.get("fecha_inicio")
            and data["fecha_fin"] < data["fecha_inicio"]
        ):
            raise serializers.ValidationError(
                "La fecha de fin no puede ser anterior a la de inicio."
            )
        return data


class ActivoReporteSerializer(serializers.ModelSerializer):
    tipo_nombre = serializers.CharField(source="tipo_activo.nombre", read_only=True)
    grupo_nombre = serializers.CharField(
        source="tipo_activo.grupo_contable.nombre", read_only=True
    )
    ubicacion_nombre = serializers.CharField(
        source="ubicacion_actual.nombre_sala", read_only=True
    )
    regional_nombre = serializers.CharField(
        source="ubicacion_actual.regional.nombre", read_only=True
    )
    probabilidad_falla = serializers.FloatField(
        source="prediccion.probabilidad_falla", read_only=True
    )
    estado_ia = serializers.CharField(
        source="prediccion.obtener_nivel_riesgo", read_only=True
    )
    # El frontend también lee la métrica ANIDADA (ViewDetails.vue:
    # activo.prediccion?.indice_salud_fuzzy; ModuloPredictivo.vue modal:
    # mtbf, mttr, recomendacion_ia, horas_soporte_acumuladas).
    prediccion = MetricaPredictivaSerializer(read_only=True)
    # Reportes.vue y Monitoreo.vue: `a.custodio_actual || 'Sin asignar'`.
    # Se resuelve sobre las designaciones ya prefetcheadas en el queryset
    # (sin N+1): la custodia vigente es la designación con esta_activa=True.
    custodio_actual = serializers.SerializerMethodField()
    historial_custodios = serializers.SerializerMethodField()

    class Meta:
        model = Activo
        fields = [
            "id",
            "codigo_tamep",
            "codigo_tab",
            "nombre_especifico",
            "tipo_nombre",
            "grupo_nombre",
            "ubicacion_nombre",
            "regional_nombre",
            "situacion_activo",
            "estado_actual",
            "probabilidad_falla",
            "estado_ia",
            "prediccion",
            "imagen_activo",
            "imagen_sn",
            "imagen_lateral",
            "imagen_qr",
            "descripcion",
            "especificaciones",
            "serie",
            "costo",
            "fecha_adquisicion",
            "perfil_uso",
            "horas_uso_actual",
            "contador_preventivos",
            "custodio_actual",
            "historial_custodios",
        ]

    def get_custodio_actual(self, obj):
        for designacion in obj.designaciones.all():
            if designacion.esta_activa and designacion.usuario:
                return (
                    designacion.usuario.get_full_name() or designacion.usuario.username
                )
        return None

    def get_historial_custodios(self, obj):
        from .models import Transferencia, Designacion, BajaActivo

        historial_completo = []

        # 1. CAPTURAR DESIGNACIONES (Asignaciones iniciales y Préstamos)
        asignaciones = Designacion.objects.filter(activo=obj)
        for d in asignaciones:
            historial_completo.append(
                {
                    "id": f"des-{d.id}",
                    "fecha_raw": d.fecha_inicio,  # Para ordenar
                    "fecha": d.fecha_inicio.strftime("%d/%m/%Y"),
                    "tipo": f"ASIGNACIÓN ({d.tipo})",
                    "emisor": "ALMACÉN CENTRAL",
                    "receptor": d.usuario.get_full_name() if d.usuario else "S/A",
                    "acta": d.num_acta or "S/N",
                    "detalle": d.observaciones or "Asignación de cargo",
                    "color": "success",
                }
            )

        # 2. CAPTURAR TRANSFERENCIAS (Movimientos entre personal)
        transferencias = Transferencia.objects.filter(activo=obj)
        for t in transferencias:
            historial_completo.append(
                {
                    "id": f"tra-{t.id}",
                    "fecha_raw": t.fecha,
                    "fecha": t.fecha.strftime("%d/%m/%Y"),
                    "tipo": t.get_tipo_display(),
                    "emisor": t.emisor.get_full_name() if t.emisor else "SIAEM",
                    "receptor": t.receptor.get_full_name() if t.receptor else "S/A",
                    "acta": t.num_acta,
                    "detalle": t.motivo,
                    "color": "primary",
                }
            )

        # 3. CAPTURAR BAJA (Si existe)
        if hasattr(obj, "baja_registro"):
            b = obj.baja_registro
            historial_completo.append(
                {
                    "id": f"baj-{b.id}",
                    "fecha_raw": b.fecha,
                    "fecha": b.fecha.strftime("%d/%m/%Y"),
                    "tipo": "BAJA TÉCNICA",
                    "emisor": b.solicitante.get_full_name()
                    if b.solicitante
                    else "ADMIN",
                    "receptor": "DESINCORPORADO",
                    "acta": b.num_baja,
                    "detalle": b.motivo,
                    "color": "danger",
                }
            )

        # ORDENAR TODO POR FECHA (Más reciente primero)
        historial_completo.sort(key=lambda x: x["fecha_raw"], reverse=True)

        # Quitamos la fecha_raw antes de enviar el JSON
        for item in historial_completo:
            item.pop("fecha_raw")

        return historial_completo


class NotificacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notificacion
        fields = ["id", "tipo", "titulo", "mensaje", "url", "leida", "fecha_creacion"]
        read_only_fields = ["id", "tipo", "titulo", "mensaje", "url", "fecha_creacion"]


class AuditoriaSerializer(serializers.ModelSerializer):
    usuario = serializers.CharField(
        source="user.username", read_only=True, default="Sistema"
    )
    nombre_usuario = serializers.CharField(
        source="user.get_full_name", read_only=True, default=""
    )
    accion = serializers.SerializerMethodField()
    objeto = serializers.CharField(source="object_repr", read_only=True)
    tabla = serializers.CharField(source="content_type.model", read_only=True)

    class Meta:
        model = LogEntry
        fields = [
            "id",
            "action_time",
            "usuario",
            "nombre_usuario",
            "action_flag",
            "accion",
            "objeto",
            "tabla",
            "change_message",
        ]

    def get_accion(self, obj):
        flags = {1: "Creación", 2: "Edición", 3: "Eliminación"}
        return flags.get(obj.action_flag, "Desconocido")
