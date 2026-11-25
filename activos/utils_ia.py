from datetime import date
from .ia_engine import IAEngine

def calcular_salud_logic(activo):
    """
    Lógica Difusa: Evalúa el estado actual del equipo.
    Salud = (Base - Edad - Fallas + Prevención)
    """
    salud = 100.0 
    
    # 1. Impacto de la Edad
    vida_total = activo.vida_util_total_meses
    if vida_total > 0:
        uso_porcentaje = (activo.edad_ajustada_meses / vida_total)
        salud -= min(60, uso_porcentaje * 50) 

    # 2. Impacto de Fallas y Mantenimiento
    salud -= (activo.contador_correctivos * 8)
    salud += (activo.contador_preventivos * 4)

    # 3. Perfil de Uso
    if activo.perfil_uso == 'Critico': salud -= 10
    elif activo.perfil_uso == 'Intensivo': salud -= 5

    return max(0, min(100, salud))

def activo_tiene_ia(activo):
    """
    Indica si el activo participa en el mantenimiento predictivo.
    Consistente con la 'puerta' que aplica Activo.save() (que borra las
    métricas de los grupos sin IA).
    """
    return bool(
        activo.tipo_activo
        and activo.tipo_activo.grupo_contable
        and activo.tipo_activo.grupo_contable.tiene_mantenimiento_predictivo
    )

def ejecutar_prediccion_y_analisis(activo):
    """
    Orquestador de IA: Calcula predicción, salud y genera recomendaciones.
    """
    from .models import MetricaPredictiva

    # LA PUERTA: sin IA habilitada en el grupo contable no creamos ni
    # tocamos MetricaPredictiva (Activo.save() la borraría igual).
    if not activo_tiene_ia(activo):
        return

    metricas, _ = MetricaPredictiva.objects.get_or_create(activo=activo)
    
    # --- 1. PREDICCIÓN RANDOM FOREST ---
    features = {
        'edad_ajustada': activo.edad_ajustada_meses,
        'mtbf': metricas.mtbf,
        'mttr': metricas.mttr,
        'fallas': activo.contador_fallas,
        'uso': 2 if activo.perfil_uso == 'Critico' else (1 if activo.perfil_uso == 'Intensivo' else 0)
    }
    
    engine = IAEngine()
    probabilidad = engine.predecir_falla(features)
    metricas.probabilidad_falla = probabilidad * 100 
    
    # --- 2. LÓGICA DIFUSA (ACTUALIZADO) ---
    metricas.indice_salud_fuzzy = calcular_salud_logic(activo)
    
    # --- 3. RECOMENDACIONES ---
    recomendaciones = []
    if metricas.probabilidad_falla > 70:
        recomendaciones.append(f"ALERTA IA: Alta probabilidad de falla ({metricas.probabilidad_falla:.1f}%).")
    
    if metricas.mttr > 5 and 0 < metricas.mtbf < 500:
        recomendaciones.append("SATURACIÓN: Evaluar reemplazo por alto tiempo de reparación.")

    if activo.fecha_adquisicion:
        hoy = date.today()
        # Cálculo exacto de años transcurridos
        años = hoy.year - activo.fecha_adquisicion.year - ((hoy.month, hoy.day) < (activo.fecha_adquisicion.month, activo.fecha_adquisicion.day))
        
        # 1. Verificamos primero la vida útil normativa (del Grupo Contable)
        if activo.tipo_activo and activo.tipo_activo.grupo_contable:
            vida_normativa = activo.tipo_activo.grupo_contable.vida_util_anos
            if años >= vida_normativa:
                recomendaciones.append(f"OBSOLESCENCIA NORMATIVA: El equipo ha cumplido su ciclo de vida contable ({vida_normativa} años).")
        
        # 2. Verificamos la obsolescencia técnica (límite de 6 años)
        # Se lanza solo si no se lanzó la anterior o para reforzar el dictamen técnico
        elif años >= 6:
            recomendaciones.append(f"OBSOLESCENCIA TÉCNICA: {años} años de uso. Supera el tiempo de vida recomendado para hardware.")

    # --- 4. GUARDADO FINAL ---
    metricas.recomendacion_ia = " | ".join(recomendaciones) if recomendaciones else "Estado estable."
    metricas.save()