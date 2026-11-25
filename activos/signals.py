from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import (
    Activo,
    HistorialEstadoActivo,
    Intervencion,
    Notificacion,
    PerfilUsuario,
    SolicitudServicio,
)
from .utils_ia import activo_tiene_ia, ejecutar_prediccion_y_analisis
from .utils_metricas import actualizar_mtbf, actualizar_mttr


# --- 1. USUARIOS Y PERFILES ---


@receiver(post_save, sender=User)
def crear_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        PerfilUsuario.objects.create(user=instance)


@receiver(post_save, sender=User)
def guardar_perfil_usuario(sender, instance, **kwargs):
    if hasattr(instance, "perfil"):
        instance.perfil.save()


@receiver(post_save, sender=User)
def notificar_nuevo_registro(sender, instance, created, **kwargs):
    if created:
        # Evitar notificar por creates de creates de perfil o creates internos sin username válido
        # Solo notificar si es un registro vía API (usuario nuevo con email)
        try:
            admins = PerfilUsuario.objects.filter(
                rol__in=["admin_informatico", "admin_principal"]
            ).select_related("user")
            for perfil in admins:
                Notificacion.objects.create(
                    destinatario=perfil.user,
                    tipo="registro",
                    titulo=f"Nueva solicitud de acceso: {instance.username}",
                    mensaje=f"El usuario {instance.get_full_name() or instance.username} ({instance.email}) se registró y espera activación.",
                    url="/Personal",
                )
            print(
                f"NOTIFICACION REGISTRO: {instance.username} -> {admins.count()} admins notificados"
            )
        except Exception as e:
            print(f"Error creando notificacion registro: {e}")


# --- 2. ACTIVOS (HISTORIAL E IA) ---


@receiver(pre_save, sender=Activo)
def guardar_estado_anterior(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Activo.objects.get(pk=instance.pk)
            instance._estado_anterior = old.estado_actual
            instance._ubicacion_anterior = old.ubicacion_actual
            instance._situacion_anterior = old.situacion_activo
        except Activo.DoesNotExist:
            instance._estado_anterior = None
            instance._ubicacion_anterior = None
            instance._situacion_anterior = None


@receiver(post_save, sender=Activo)
def registrar_historial_estado(sender, instance, created, **kwargs):

    if created:
        HistorialEstadoActivo.objects.create(
            activo=instance,
            estado=instance.estado_actual,
            observacion=f"Registro inicial del activo en {instance.ubicacion_actual or instance.ubicacion_base}",
        )
        return

    estado_anterior = getattr(instance, "_estado_anterior", None)
    ubicacion_anterior = getattr(instance, "_ubicacion_anterior", None)
    situacion_anterior = getattr(instance, "_situacion_anterior", None)

    cambio_estado = estado_anterior != instance.estado_actual
    cambio_ubicacion = ubicacion_anterior != instance.ubicacion_actual
    cambio_situacion = situacion_anterior != instance.situacion_activo

    if cambio_estado or cambio_ubicacion or cambio_situacion:
        observaciones = []

        if cambio_estado:
            observaciones.append(
                f"Estado físico: {estado_anterior} → {instance.estado_actual}"
            )

        if cambio_ubicacion:
            observaciones.append(
                f"Ubicación: {ubicacion_anterior} → {instance.ubicacion_actual}"
            )

        if cambio_situacion:
            observaciones.append(
                f"Situación: {situacion_anterior} → {instance.situacion_activo}"
            )

        HistorialEstadoActivo.objects.create(
            activo=instance,
            estado=instance.estado_actual,
            observacion=" | ".join(observaciones),
        )


@receiver(post_save, sender=Activo)
def inicializar_ia_nuevo_activo(sender, instance, created, **kwargs):
    """
    Si es un activo nuevo, inicializamos sus métricas
    para que no aparezcan vacías en el Admin.

    EL PORTERO: ejecutar_prediccion_y_analisis() solo crea la tabla de IA si el
    grupo contable tiene habilitado el mantenimiento predictivo.
    """
    if created:
        ejecutar_prediccion_y_analisis(instance)


# --- 3. INTERVENCIONES Y SOPORTE ---


@receiver(post_save, sender=Intervencion)
def actualizar_ia_por_intervencion(sender, instance, created, **kwargs):
    """
    Recalcula las métricas de ingeniería (MTBF/MTTR) y dispara el Random Forest
    cuando se cierra una intervención.

    Los contadores del Activo NO se tocan aquí: los incrementa y persiste
    Intervencion.save() para que exista una sola fuente de verdad.
    """
    activo = instance.activo

    if not activo_tiene_ia(activo):
        return
    if not instance.fecha_fin:
        return

    # 1. Métricas de ingeniería
    actualizar_mtbf(activo)
    actualizar_mttr(activo)
    if hasattr(activo, "prediccion"):
        activo.prediccion.actualizar_horas_soporte()

    # 2. Motor de IA y análisis prescriptivo (al final, con los datos ya frescos)
    ejecutar_prediccion_y_analisis(activo)


@receiver(post_save, sender=Intervencion)
def notificar_mantenimiento_atendido(sender, instance, created, **kwargs):
    if created:
        try:
            # Notificar al solicitante de la solicitud asociada
            solicitud = instance.solicitud
            destinatario = solicitud.solicitante
            Notificacion.objects.create(
                destinatario=destinatario,
                tipo="mantenimiento",
                titulo=f"Solicitud {solicitud.num_ticket} atendida",
                mensaje=f"Tu solicitud para {instance.activo.codigo_tamep} fue atendida por {instance.tecnico.get_full_name() or instance.tecnico.username}: {instance.detalles_reparacion[:120]}",
                url="/solicitud-mantenimiento",
            )
            print(
                f"NOTIFICACION MANTENIMIENTO: {solicitud.num_ticket} -> {destinatario.username}"
            )
        except Exception as e:
            print(f"Error creando notificacion mantenimiento: {e}")


@receiver(post_save, sender=SolicitudServicio)
def alertar_soporte_tecnico(sender, instance, created, **kwargs):
    if created:
        # Aquí puedes integrar el envío de correos o Push Notifications
        print(
            f"ALERTA: Nueva solicitud {instance.id} para el equipo {instance.activo.codigo_tamep}"
        )
        if instance.severidad == "3":
            # Consultar la última predicción para dar más contexto al técnico
            try:
                prediccion = instance.activo.prediccion
                print(
                    f"¡CRÍTICO! El equipo tiene {prediccion.probabilidad_falla}% de falla según IA."
                )  # Alta - No puede trabajar
            except Exception:
                pass
        # NOTIFICACIÓN: avisar a admin_informatico
        try:
            admins = PerfilUsuario.objects.filter(
                rol="admin_informatico"
            ).select_related("user")
            for perfil in admins:
                Notificacion.objects.create(
                    destinatario=perfil.user,
                    tipo="solicitud",
                    titulo=f"Nueva solicitud {instance.num_ticket}",
                    mensaje=f"{instance.solicitante.get_full_name() or instance.solicitante.username} solicitó mantenimiento para {instance.activo.codigo_tamep}: {instance.descripcion_problema[:120]}",
                    url="/Solicitud-mantenimiento",
                )
        except Exception as e:
            print(f"Error creando notificacion solicitud: {e}")
