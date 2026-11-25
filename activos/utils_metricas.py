from django.db import transaction
from django.utils import timezone

def actualizar_mtbf(activo):
    """
    MTBF: Tiempo medio entre fallas.
    Mide la CONFIABILIDAD. Cuanto más alto, mejor.
    """
    from .models import Intervencion, MetricaPredictiva
    
    # Solo tomamos Correctivos porque representan una falla real
    intervenciones = Intervencion.objects.filter(
        activo=activo,
        tipo_mantenimiento='Correctivo'
    ).order_by('fecha_inicio')

    if intervenciones.count() >= 1:
        # --- MEJORA PRO: Incluir tiempo desde la adquisición ---
        # Si no incluimos el tiempo desde que se compró hasta la primera falla,
        # perdemos datos valiosos de confiabilidad inicial.
        puntos_tiempo = []
        if activo.fecha_adquisicion:
            puntos_tiempo.append(activo.fecha_adquisicion)
        
        # Agregamos las fechas de las fallas
        fallas = list(intervenciones)
        
        intervalos = []
        # Calculamos uptime: desde el fin de una reparación hasta el inicio de la siguiente
        inicio_operacion = activo.fecha_adquisicion
        
        for falla in fallas:
            if inicio_operacion:
                # Convertimos inicio_operacion a datetime si es solo date para comparar
                import datetime
                if isinstance(inicio_operacion, datetime.date) and not isinstance(inicio_operacion, datetime.datetime):
                    # Asumimos que la operación empezó a las 00:00 de ese día
                    dt_inicio = timezone.make_aware(datetime.datetime.combine(inicio_operacion, datetime.time.min))
                else:
                    dt_inicio = inicio_operacion

                # Tiempo funcionando (Uptime) = Inicio de falla - Fin de reparación anterior
                diff = falla.fecha_inicio - dt_inicio
                horas_funcionando = diff.total_seconds() / 3600
                if horas_funcionando > 0:
                    intervalos.append(horas_funcionando)
            
            # El equipo vuelve a estar disponible cuando termina la intervención
            inicio_operacion = falla.fecha_fin

        if intervalos:
            mtbf = sum(intervalos) / len(intervalos)
            metrica, _ = MetricaPredictiva.objects.get_or_create(activo=activo)
            metrica.mtbf = round(mtbf, 2)
            metrica.save()

def actualizar_mttr(activo):
    """
    MTTR: Tiempo medio de reparación.
    Mide la MANTENIBILIDAD. Cuanto más bajo, mejor.
    """
    from .models import Intervencion, MetricaPredictiva
    
    # IMPORTANTE: El MTTR técnico real solo se calcula sobre CORRECTIVOS.
    # Los Preventivos son programados y no representan "tiempo de reparación de falla".
    intervenciones = Intervencion.objects.filter(
        activo=activo,
        tipo_mantenimiento='Correctivo'
    )

    if intervenciones.exists():
        tiempos = [
            (i.fecha_fin - i.fecha_inicio).total_seconds() / 3600
            for i in intervenciones
        ]

        mttr = sum(tiempos) / len(tiempos)
        metrica, _ = MetricaPredictiva.objects.get_or_create(activo=activo)
        metrica.mttr = round(mttr, 2)
        metrica.save()