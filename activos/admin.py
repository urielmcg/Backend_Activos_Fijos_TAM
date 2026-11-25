from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Gerencia, Cargo, PerfilUsuario, Regional, Ubicacion, 
    Activo, Designacion, Transferencia, SolicitudServicio, Intervencion, 
    MetricaPredictiva, GrupoContable, TipoActivo, HistorialEstadoActivo,
    BajaActivo # <--- IMPORTANTE: Incluimos el modelo de Bajas
)

# --- 1. CONFIGURACIÓN GENERAL ---
admin.site.register(Gerencia)
admin.site.register(Cargo)
admin.site.register(PerfilUsuario)
admin.site.register(Regional)
admin.site.register(Ubicacion)

# --- 2. CONFIGURACIÓN DE GRUPOS Y TIPOS ---
class TipoActivoInline(admin.TabularInline):
    model = TipoActivo
    extra = 1

@admin.register(GrupoContable)
class GrupoContableAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'vida_util_anos', 'coeficiente_depreciacion', 'tiene_mantenimiento_predictivo')
    list_editable = ('tiene_mantenimiento_predictivo',)
    inlines = [TipoActivoInline]

@admin.register(TipoActivo)
class TipoActivoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'grupo_contable')
    list_filter = ('grupo_contable',)
class MetricaPredictivaInline(admin.StackedInline):
    """
    Esta es una 'ventana' a todo el poder de tu MetricaPredictiva 
    dentro de la ficha del Activo. No se simplifica nada.
    """
    model = MetricaPredictiva
    can_delete = False
    readonly_fields = (
        'mtbf', 'mttr', 'rul', 'probabilidad_falla', 
        'indice_salud_fuzzy', 'horas_soporte_acumuladas', 'get_recomendacion_ia_poa'
    )
    
    fieldsets = (
        ('Métricas de Confiabilidad ($MTBF$ / $MTTR$)', {
            'classes': ('collapse',),
            'fields': (('mtbf', 'mttr'), 'horas_soporte_acumuladas', 'rul')
        }),
        ('Inteligencia de Datos (Random Forest & Fuzzy Logic)', {
            'classes': ('collapse',),
            'fields': (('probabilidad_falla', 'indice_salud_fuzzy'), 'get_recomendacion_ia_poa')
        }),
    )

    def get_recomendacion_ia_poa(self, obj):
        rec = obj.generar_recomendacion_poa()
        return format_html('<div style="background:#f0f7ff; border-left:5px solid #007bff; padding:15px;">{}</div>', rec)
# --- 3. CONFIGURACIÓN DE ACTIVOS (VISUALMENTE RICA) ---
@admin.register(Activo)
class ActivoAdmin(admin.ModelAdmin):
    list_display = (
        'codigo_tamep', 'nombre_especifico', 'get_tipo', 
        'colorear_estado_fisico', 'mostrar_riesgo_rapido', 
        'get_regional_actual', 'situacion_activo', 'get_edad_ia'
    )
    list_filter = (
        'tipo_activo__grupo_contable__tiene_mantenimiento_predictivo', 
        'situacion_activo', 'estado_actual', 'perfil_uso'
    )
    search_fields = ('codigo_tamep', 'nombre_especifico', 'serie')
    readonly_fields = ('visualizar_vida_util', 'imagen_qr', 'get_edad_ia')
    inlines = [MetricaPredictivaInline]

    fieldsets = (
        ('Información General', {
            'fields': ('codigo_tamep', 'codigo_tab', 'nombre_especifico', 'serie')
        }),
        ('Grupo Contable', {
            'description': 'Los campos de IA solo afectarán si el Grupo Contable tiene la IA habilitada.',
            'fields': (('grupo_contable_seleccionado', 'tipo_activo'), ('perfil_uso', 'get_edad_ia'))
        }),
        ('Estado y Ubicación', {
            'fields': ('estado_actual', 'situacion_activo', 'ubicacion_base', 'ubicacion_actual')
        }),
        ('Métricas de Uso (IA)', {
            'classes': ('collapse',), # Oculto por defecto para activos simples
            'fields': ('horas_uso_actual', 'contador_fallas', 'uso_inicial_estimado')
        }),
        ('Costos y Tiempos', {
            'fields': ('fecha_adquisicion', 'costo', 'visualizar_vida_util')
        }),
        ('Detalles Técnicos', {
            'classes': ('collapse',),
            'fields': ('descripcion', 'especificaciones', 'imagen_activo', 'imagen_lateral', 'imagen_sn', 'imagen_qr')
        }),
    )
   

    def get_edad_ia(self, obj):
        return f"{obj.edad_ajustada_meses} meses"
    get_edad_ia.short_description = 'Edad Ajustada (IA)'

    def visualizar_vida_util(self, obj):
        if obj.vida_util_estimada:
            anios = obj.vida_util_estimada // 12
            meses = obj.vida_util_estimada % 12
            txt = f"{anios} años"
            if meses > 0: txt += f" y {meses} meses"
            return txt
        return "0 años"
    visualizar_vida_util.short_description = "Vida Útil"

    def get_tipo(self, obj): return obj.tipo_activo.nombre if obj.tipo_activo else "-"
    get_tipo.short_description = 'Tipo'

    def get_regional_actual(self, obj): return obj.ubicacion_actual.regional.nombre if obj.ubicacion_actual else "-"
    get_regional_actual.short_description = 'Regional'

    def colorear_estado_fisico(self, obj):
        colores = {'Bueno': '#28a745', 'Regular': '#ffc107', 'Malo': '#dc3545'}
        color = colores.get(obj.estado_actual, '#6c757d')
        return format_html('<strong style="color: {};">{}</strong>', color, obj.estado_actual)
    colorear_estado_fisico.short_description = 'Estado Físico'

    def mostrar_riesgo_rapido(self, obj):
        # Esta función intenta leer la predicción si existe
        try:
            if hasattr(obj, 'prediccion'):
                prob = float(obj.prediccion.probabilidad_falla)
                color = "#28a745" if prob < 40 else ("#ffc107" if prob < 75 else "#dc3545")
                return format_html(
                    '<div style="width:80px; background:#eee; border-radius:3px; height:10px;">'
                    '<div style="width:{}px; background:{}; height:10px;"></div>'
                    '</div>',
                    min(prob, 80), color
                )
            return "-"
        except:
            return format_html('<small style="color:gray;">Sin Datos</small>')
    mostrar_riesgo_rapido.short_description = 'Riesgo IA'
    class Media:
        js = (
            'https://code.jquery.com/jquery-3.6.0.min.js', 
        )

# --- 4. DESIGNACIONES ---
# --- 4. GESTIÓN DE DESIGNACIONES Y PRÉSTAMOS ---

@admin.register(Designacion)
class DesignacionAdmin(admin.ModelAdmin):
    # Columnas principales con información de trazabilidad
    list_display = (
        'get_codigo_activo', 'get_nombre_activo', 'usuario', 
        'tipo', 'esta_activa', 'fecha_inicio', 'get_ubicacion'
    )
    
    # Filtros laterales para gestión de inventario
    list_filter = ('tipo', 'esta_activa', 'regional', 'fecha_inicio')
    
    # Búsqueda potente por código de activo o nombre de funcionario
    search_fields = ('activo__codigo_tamep', 'usuario__username', 'usuario__first_name', 'usuario__last_name')
    
    # Campos de solo lectura para integridad del sistema
    readonly_fields = ('fecha_inicio', 'fecha_fin_real')

    # Organización por Fieldsets para un flujo de trabajo lógico
    fieldsets = (
        ('Selección de Activo', {
            'description': 'Filtre por grupo y tipo para encontrar el activo disponible.',
            'fields': (('grupo_contable', 'tipo_activo_filtro'), 'activo')
        }),
        ('Responsable y Ubicación', {
            'description': 'Asignación del funcionario siguiendo la jerarquía de TAMEP.',
            'fields': (('regional', 'gerencia'), ('cargo', 'usuario'), 'ubicacion')
        }),
        ('Condiciones de la Designación', {
            'fields': (('tipo', 'esta_activa'), ('fecha_fin_estimada', 'fecha_fin_real'))
        }),
        ('Documentación y Respaldo', {
            'classes': ('collapse',),
            'fields': ('observaciones', 'documento_respaldo')
        }),
    )

    # --- Métodos de Ayuda para Visualización ---

    def get_codigo_activo(self, obj):
        return obj.activo.codigo_tamep
    get_codigo_activo.short_description = 'Código TAMEP'
    get_codigo_activo.admin_order_field = 'activo__codigo_tamep'

    def get_nombre_activo(self, obj):
        return obj.activo.nombre_especifico
    get_nombre_activo.short_description = 'Activo'

    def get_ubicacion(self, obj):
        return f"{obj.ubicacion.nombre_sala} ({obj.regional.nombre})"
    get_ubicacion.short_description = 'Ubicación de Destino'

    # Mejoramos la experiencia de usuario con CSS inline para el estado
    def save_model(self, request, obj, form, change):
        # Aquí podrías añadir lógica adicional antes de guardar, 
        # aunque la mayoría ya está en tu robusto método save() del modelo.
        super().save_model(request, obj, form, change)

# --- 5. TRANSFERENCIAS ---
@admin.register(Transferencia)
class TransferenciaAdmin(admin.ModelAdmin):
    list_display = ('num_acta', 'activo', 'emisor', 'receptor', 'tipo', 'fecha')
    search_fields = ('num_acta', 'activo__codigo_tamep')

# --- 6. BAJAS ---
@admin.register(BajaActivo)
class BajaActivoAdmin(admin.ModelAdmin):
    list_display = ('activo', 'num_baja', 'motivo', 'fecha', 'solicitante')
    # 'resolucion_admin' fue eliminado en la migración 0022: buscarlo rompía el admin.
    search_fields = ('activo__codigo_tamep', 'num_baja', 'motivo')
    readonly_fields = ('fecha',)

# --- 7. SERVICIOS E INTERVENCIONES ---
@admin.register(SolicitudServicio)
class SolicitudServicioAdmin(admin.ModelAdmin):
    list_display = ('id', 'activo', 'solicitante', 'severidad', 'fecha_solicitud')
    readonly_fields = ('fecha_solicitud',)
# --- 8. INTERVENCIONES ---
@admin.register(Intervencion)
class IntervencionAdmin(admin.ModelAdmin):
    list_display = ('activo', 'tipo_mantenimiento', 'tecnico', 'fecha_fin', 'estado_post_intervencion')
    list_filter = ('tipo_mantenimiento', 'estado_post_intervencion')
# --- 9. HISTORIAL ESTADO ACTIVO ---
@admin.register(HistorialEstadoActivo)
class HistorialEstadoActivoAdmin(admin.ModelAdmin):
    list_display = ('activo', 'estado', 'fecha', 'observacion')
    readonly_fields = ('activo', 'fecha', 'observacion')

# --- 10. METRICAS IA (CON GRÁFICOS) ---
@admin.register(MetricaPredictiva)
class MetricaPredictivaAdmin(admin.ModelAdmin):
    list_display = ('activo', 'mostrar_barra_riesgo', 'mostrar_salud_fuzzy', 'mtbf', 'mttr', 'ultima_actualizacion')
    list_filter = ('patron_falla_detectado',)
    readonly_fields = ('activo', 'mtbf', 'mttr', 'rul', 'probabilidad_falla', 'indice_salud_fuzzy', 'horas_soporte_acumuladas', 'get_recomendacion_ia_poa')

    fieldsets = (
        ('Métricas de Ingeniería', {
            'fields': (('mtbf', 'mttr'), 'horas_soporte_acumuladas', 'rul')
        }),
        ('Análisis Inteligente', {
            'fields': (('probabilidad_falla', 'indice_salud_fuzzy'), 'patron_falla_detectado')
        }),
        ('Resultado Prescriptivo', {
            'fields': ('get_recomendacion_ia_poa',)
        }),
    )

    def mostrar_barra_riesgo(self, obj):
        prob_val = float(obj.probabilidad_falla or 0.0)
        prob_str = "{:.1f}".format(prob_val)
        
        if prob_val < 40: color = "#28a745"
        elif prob_val < 75: color = "#ffc107"
        else: color = "#dc3545"
        
        return format_html(
            '<div style="width:100px; background:#eee; border-radius:4px; overflow:hidden; border:1px solid #ccc;">'
            '<div style="width:{}px; background:{}; height:15px;"></div>'
            '</div><small><b>{}%</b> riesgo</small>',
            min(prob_val, 100), color, prob_str
        )
    mostrar_barra_riesgo.short_description = 'Probabilidad RF'

    def mostrar_salud_fuzzy(self, obj):
        salud_val = float(obj.indice_salud_fuzzy or 0.0)
        salud_str = "{:.2f}".format(salud_val)
        
        if salud_val >= 70: color = "#28a745"
        elif salud_val >= 40: color = "#ffc107"
        else: color = "#dc3545"

        return format_html(
            '<span style="font-weight:bold; color:{}; font-size:1.1em;">{} pts</span>', 
            color, salud_str
        )
    mostrar_salud_fuzzy.short_description = 'Salud Fuzzy'

    def get_recomendacion_ia_poa(self, obj):
        rec = obj.generar_recomendacion_poa()
        return format_html('<div style="background:#f8f9fa; border-left:5px solid #007bff; padding:10px;">{}</div>', rec)
    get_recomendacion_ia_poa.short_description = 'Sugerencia POA'