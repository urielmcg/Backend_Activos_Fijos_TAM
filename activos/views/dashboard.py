from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Avg, Sum, Q, F
from django.utils import timezone
from datetime import timedelta
from ..models import Activo, Intervencion, Regional, MetricaPredictiva, SolicitudServicio
from ..permissions import obtener_rol
from rest_framework_simplejwt.authentication import JWTAuthentication
class DashboardStatsAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_regional_filter(self, request):
        """Retorna filtro de regional si el usuario es admin_regional."""
        rol = obtener_rol(request.user)
        if rol == 'admin_regional' and hasattr(request.user, 'perfil') and request.user.perfil.regional:
            return {'ubicacion_actual__regional': request.user.perfil.regional}
        return {}

    def get(self, request):
        hoy = timezone.now()
        regional_filter = self.get_regional_filter(request)
        activos_base = Activo.objects.filter(**regional_filter) if regional_filter else Activo.objects
        metricas_base = MetricaPredictiva.objects.filter(**{f'activo__{k}': v for k, v in regional_filter.items()}) if regional_filter else MetricaPredictiva.objects

        kpis_ia = metricas_base.aggregate(
            avg_salud=Avg('indice_salud_fuzzy'),
            avg_mtbf=Avg('mtbf'),
            avg_mttr=Avg('mttr'),
            criticos=Count('id', filter=Q(probabilidad_falla__gt=75))
        )

        # Rejuvenecimiento (Basado en mejoras técnicas)
        intervenciones_base = Intervencion.objects.filter(**{f'activo__{k}': v for k, v in regional_filter.items()}) if regional_filter else Intervencion.objects
        mejoras = intervenciones_base.filter(tipo_mantenimiento='Mejora').aggregate(
            total=Count('id'),
            meses=Sum(F('activo__tipo_activo__grupo_contable__vida_util_anos'))
        )
        meses_recuperados = (mejoras['total'] or 0) * 6 

        # --- 2. TENDENCIA DE MANTENIMIENTO (6 MESES) ---
        labels, data_preventivo, data_correctivo = [], [], []
        for i in range(5, -1, -1):
            fecha_inicio_mes = (hoy.replace(day=1) - timedelta(days=i*30)).replace(day=1)
            labels.append(fecha_inicio_mes.strftime('%b'))
            
            intervenciones_mes = intervenciones_base.filter(
                fecha_inicio__year=fecha_inicio_mes.year,
                fecha_inicio__month=fecha_inicio_mes.month
            )
            data_preventivo.append(intervenciones_mes.filter(tipo_mantenimiento='Preventivo').count())
            data_correctivo.append(intervenciones_mes.filter(tipo_mantenimiento='Correctivo').count())

        # --- 3. TOP 5 RIESGO INMINENTE (Random Forest) ---
        top_riesgo = metricas_base.filter(
            activo__situacion_activo='Asignado'
        ).select_related('activo').order_by('-probabilidad_falla')[:5]

        # --- 4. PRÓXIMA ACCIÓN ESTRATÉGICA ---
        solicitudes_base = SolicitudServicio.objects.filter(**{f'activo__{k}': v for k, v in regional_filter.items()}) if regional_filter else SolicitudServicio.objects
        proxima = solicitudes_base.filter(
            intervenciones__isnull=True
        ).select_related('activo', 'activo__prediccion').order_by(
            '-activo__prediccion__probabilidad_falla', '-severidad'
        ).first()

        return Response({
            "cards": {
                "total_activos": activos_base.exclude(situacion_activo='Baja').count(),
                "criticos_ia": kpis_ia['criticos'] or 0,
                "salud_global": round(float(kpis_ia['avg_salud'] or 0), 2),
                "meses_recuperados": meses_recuperados,
                "total_mejoras": mejoras['total'] or 0,
                "mtbf_avg": round(float(kpis_ia['avg_mtbf'] or 0), 1), # Nuevo KPI
                "mttr_avg": round(float(kpis_ia['avg_mttr'] or 0), 1), # Nuevo KPI
                "proximo_mantenimiento": {
                    "activo": proxima.activo.nombre_especifico if proxima else "Ninguno",
                    "codigo": proxima.activo.codigo_tamep if proxima else "N/A",
                    # Un activo puede no tener fila en MetricaPredictiva (OneToOne
                    # inverso): acceder directo lanza RelatedObjectDoesNotExist y
                    # reventaba el Dashboard con 500.
                    "probabilidad": (
                        proxima.activo.prediccion.probabilidad_falla
                        if proxima and hasattr(proxima.activo, "prediccion")
                        else 0
                    ),
                } if proxima else None
            },
            "charts": {
                "mantenimiento": {
                    "labels": labels,
                    "preventivos": data_preventivo,
                    "correctivos": data_correctivo
                },
                "perfiles": list(activos_base.values('perfil_uso').annotate(total=Count('id')))
            },
            "top_criticos": [{
                "nombre": m.activo.nombre_especifico,
                "codigo": m.activo.codigo_tamep,
                "probabilidad": round(m.probabilidad_falla, 1)
            } for m in top_riesgo],
            "regionales": self.get_regionales_stats()
        })

    def get_regionales_stats(self):
        res = []
        for reg in Regional.objects.all():
            activos = Activo.objects.filter(ubicacion_actual__regional=reg)
            if activos.exists():
                salud = MetricaPredictiva.objects.filter(activo__in=activos).aggregate(Avg('indice_salud_fuzzy'))
                res.append({
                    "nombre": reg.nombre,
                    "cantidad": activos.count(),
                    "salud": round(float(salud['indice_salud_fuzzy__avg'] or 0), 2)
                })
        return res