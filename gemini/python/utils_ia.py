from datetime import timedelta
from .models import Intervencion, MetricasIA

def calcular_mtbf_activo(activo_id):
    # Obtenemos intervenciones correctivas ordenadas por fecha
    mantenimientos = Intervencion.objects.filter(
        solicitud__activo_id=activo_id, 
        tipo_mant='CORR'
    ).order_by('fecha_inicio')

    if mantenimientos.count() < 2:
        return 0 # No hay suficientes datos para una media

    intervalos = []
    for i in range(len(mantenimientos) - 1):
        diferencia = mantenimientos[i+1].fecha_inicio - mantenimientos[i].fecha_fin
        intervalos.append(diferencia.total_seconds() / 3600) # En horas

    mtbf = sum(intervalos) / len(intervalos)
    
    # Guardamos en la tabla de IA
    obj, created = MetricasIA.objects.get_or_create(activo_id=activo_id)
    obj.mtbf = mtbf
    obj.save()
    return mtbf