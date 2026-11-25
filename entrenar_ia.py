import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import confusion_matrix, classification_report
import joblib
import os

# 1. Generación de Datos Sintéticos (Basados en la realidad de TAMEP)
np.random.seed(42)
n_samples = 1000

data = {
    'edad_ajustada': np.random.randint(1, 120, n_samples),
    'mtbf': np.random.randint(100, 2000, n_samples),
    'mttr': np.random.uniform(1, 24, n_samples),
    'fallas': np.random.randint(0, 10, n_samples),
    'uso': np.random.choice([0, 1, 2], n_samples)  # 0:Oficina, 1:Intensivo, 2:Crítico
}

df = pd.DataFrame(data)
# Lógica de falla: falla si es viejo, tiene bajo MTBF y uso crítico
df['fallo'] = ((df['edad_ajustada'] / 120) + (1 - df['mtbf'] / 2000) + (df['uso'] / 2) > 1.5).astype(int)

# 2. Preparación
X = df.drop('fallo', axis=1)
y = df['fallo']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 3. Escalado (StandardScaler)
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# 4. Entrenamiento
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train_scaled, y_train)

# 5. Evaluación para tu Tesis
y_pred = model.predict(X_test_scaled)
print("--- MATRIZ DE CONFUSIÓN ---")
print(confusion_matrix(y_test, y_pred))
print("\n--- REPORTE DE CLASIFICACIÓN ---")
print(classification_report(y_test, y_pred))

# 6. Guardado de archivos
if not os.path.exists('ia_models'): os.makedirs('ia_models')
joblib.dump(model, 'ia_models/random_forest_v1.joblib')
joblib.dump(scaler, 'ia_models/scaler_v1.joblib')
print("\nArchivos guardados en ia_models/")