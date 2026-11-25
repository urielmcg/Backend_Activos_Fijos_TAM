import joblib
import os
import pandas as pd
from django.conf import settings

class IAEngine:
    _instance = None
    _model = None
    _scaler = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(IAEngine, cls).__new__(cls)
            path = os.path.join(settings.BASE_DIR, 'ia_models')
            model_path = os.path.join(path, 'random_forest_v1.joblib')
            scaler_path = os.path.join(path, 'scaler_v1.joblib')

            try:
                if os.path.exists(model_path) and os.path.exists(scaler_path):
                    cls._model = joblib.load(model_path)
                    cls._scaler = joblib.load(scaler_path)
                else:
                    print(f"Advertencia: Archivos no encontrados en {path}")
            except Exception as e:
                print(f"Error crítico al cargar modelos de IA: {e}")
                
        return cls._instance

    def predecir_falla(self, datos_dict):
        if not self._model or not self._scaler:
            return 0.0
        
        try:
            df = pd.DataFrame([datos_dict])
            datos_scaled = self._scaler.transform(df)
            probabilidades = self._model.predict_proba(datos_scaled)
            return probabilidades[0][1]
        except Exception as e:
            print(f"Error en la predicción: {e}")
            return 0.0