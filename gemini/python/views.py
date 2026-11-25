from django.shortcuts import render, redirect
from .forms import ActivoForm, DesignacionForm
from django.shortcuts import render, get_object_ some_list_or_object
from .models import Activo, Intervencion
from django.db.models.functions import ExtractMonth, ExtractYear
from django.db.models import Count, Sum

# Vista para el Registro Técnico
def registrar_activo(request):
    if request.method == 'POST':
        form = ActivoForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('lista_activos')
    else:
        form = ActivoForm()
    return render(request, 'registro.html', {'form': form})

# Vista para Designar Responsable
def designar_activo(request, activo_id):
    activo = Activo.objects.get(id=activo_id)
    if request.method == 'POST':
        form = DesignacionForm(request.POST)
        if form.is_valid():
            designacion = form.save(commit=False)
            designacion.activo = activo
            designacion.save()
            # Cambiamos estado del activo
            activo.disponible = False
            activo.save()
            return redirect('detalle_activo', activo.id)
    else:
        form = DesignacionForm()
    return render(request, 'designar.html', {'form': form, 'activo': activo})
def detalle_historial_equipo(request, activo_id):
    activo = get_object_or_404(Activo, id=activo_id)
    # Obtenemos las intervenciones con sus fallas relacionadas
    historial = Intervencion.objects.filter(solicitud__activo=activo).select_related('solicitud').prefetch_related('fallas_set')
    
    return render(request, 'historial_equipo.html', {
        'activo': activo,
        'historial': historial
    })

def reporte_mantenimientos_mensuales(request):
    # Agrupamos intervenciones por mes y año
    reporte_mensual = Intervencion.objects.annotate(
        mes=ExtractMonth('fecha_inicio'),
        anio=ExtractYear('fecha_inicio')
    ).values('mes', 'anio').annotate(
        total_servicios=Count('id'),
        costo_total=Sum('costo')
    ).order_by('-anio', '-mes')

    return render(request, 'reporte_mensual.html', {'reporte': reporte_mensual})