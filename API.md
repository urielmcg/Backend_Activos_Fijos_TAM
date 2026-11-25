# 📡 API REST — Sistema de Activos Fijos TAMEP (SIAEM)

> Documentación técnica completa de la API REST construida con **Django REST Framework**.  
> Base URL de producción: `https://siaem.tamep.bo/api/`  
> Base URL local: `http://localhost:8000/api/`

---

## 📑 Índice

1. [Arquitectura General](#1-arquitectura-general)
2. [Autenticación (JWT)](#2-autenticación-jwt)
3. [Modelos de Datos](#3-modelos-de-datos)
4. [Endpoints de la API](#4-endpoints-de-la-api)
   - [Login y Perfil de Usuario](#41-login-y-perfil-de-usuario)
   - [Activos](#42-activos)
   - [Designaciones](#43-designaciones-asignaciones)
   - [Transferencias](#44-transferencias)
   - [Baja de Activos](#45-baja-de-activos)
   - [Solicitudes de Servicio](#46-solicitudes-de-servicio)
   - [Intervenciones](#47-intervenciones)
   - [Dashboard](#48-dashboard)
   - [Reportes y Gestión](#49-reportes-y-gestión-de-activos)
   - [Catálogos (Parámetros)](#410-catálogos-parámetros)
   - [Notificaciones y Auditoría](#411-notificaciones-y-auditoría)
5. [Motor de IA Predictiva](#5-motor-de-ia-predictiva)
6. [Signals y Hooks Automáticos](#6-signals-y-hooks-automáticos)
7. [Configuración del Proyecto](#7-configuración-del-proyecto)

---

## 1. Arquitectura General

```
core/                  ← Proyecto Django principal
├── settings.py        ← Configuración global (DB MySQL, JWT, CORS)
├── urls.py            ← Enrutamiento central con DefaultRouter
├── wsgi.py / asgi.py  ← Entry points del servidor

activos/               ← App principal del sistema
├── models.py          ← 12 modelos de datos (~843 líneas)
├── serializers.py     ← 10+ serializers DRF (~344 líneas)
├── views/             ← ViewSets organizados por módulo
│   ├── activos.py     ← CRUD de activos + acciones extra
│   ├── designaciones.py ← Asignación de activos a personal
│   ├── transferencias.py ← Transferencias entre funcionarios
│   ├── baja.py        ← Desincorporación de activos
│   ├── soporte.py     ← Solicitudes de servicio e intervenciones
│   ├── reportes.py    ← Vistas de solo lectura para reportes
│   ├── dashboard.py   ← KPIs y estadísticas del dashboard
│   ├── auth.py        ← Login personalizado con JWT
│   ├── usuarios.py    ← Perfil de usuario (GET/PATCH)
│   └── parametros.py  ← Catálogos para selectores del formulario
├── ia_engine.py       ← Singleton del Random Forest (joblib)
├── utils_ia.py        ← Lógica difusa + análisis prescriptivo
├── utils_metricas.py  ← Cálculos de MTBF y MTTR
└── signals.py         ← Hooks post_save / pre_save
```

**Stack tecnológico:**

| Componente          | Tecnología                                       |
|---------------------|--------------------------------------------------|
| Framework           | Django 5.2 + Django REST Framework                |
| Base de datos       | MySQL (motor `django.db.backends.mysql`)          |
| Autenticación       | `djangorestframework-simplejwt` (Bearer JWT)      |
| Filtros             | `django-filter` (DjangoFilterBackend)             |
| Campos encadenados  | `django-smart-selects` (ChainedForeignKey)        |
| CORS                | `django-cors-headers`                             |
| IA / ML             | `scikit-learn` (Random Forest) + `joblib`         |
| QR                  | `qrcode` + `Pillow`                              |

---

## 2. Autenticación (JWT)

La API utiliza **JSON Web Tokens** con `djangorestframework-simplejwt`.

### Flujo de autenticación

```
1. POST /api/login/  →  Recibe { access, refresh, user }
2. Cada petición  →  Header: "Authorization: Bearer <access_token>"
3. Token expirado →  POST /api/token/refresh/ con { refresh }
```

### Configuración JWT

```python
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=180),   # 3 horas
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),        # 1 día
    "AUTH_HEADER_TYPES": ("Bearer",),
}
```

### `POST /api/login/`

**Request:**
```json
{
  "username": "usuario@tamep.bo",
  "password": "contraseña"
}
```

**Response exitosa (200):**
```json
{
  "access": "eyJ0eXAi...",
  "refresh": "eyJ0eXAi...",
  "success": true,
  "message": "Bienvenido a TAMEP",
  "user": {
    "id": 1,
    "username": "usuario@tamep.bo",
    "first_name": "Juan",
    "last_name": "Pérez",
    "nombre_completo": "Juan Pérez",
    "cargo_nombre": "Técnico de Informática",
    "es_admin": false
  }
}
```

**Response error (401):**
```json
{ "success": false, "error": "Credenciales incorrectas." }
```

### `POST /api/token/refresh/`

**Request:** `{ "refresh": "<refresh_token>" }`  
**Response:** `{ "access": "<nuevo_access_token>" }`

---

## 3. Modelos de Datos

### Diagrama de relaciones

```
Regional (1) ──┬──→ (N) Ubicacion
               ├──→ (N) Gerencia ──→ (N) Cargo
               └──→ (N) Designacion / Transferencia

GrupoContable (1) ──→ (N) TipoActivo ──→ (N) Activo

User (1) ──→ (1) PerfilUsuario
         ├──→ (N) Designacion
         ├──→ (N) Transferencia (emisor/receptor)
         └──→ (N) SolicitudServicio / Intervencion

Activo (1) ──┬──→ (N) Designacion
             ├──→ (N) Transferencia
             ├──→ (1) BajaActivo
             ├──→ (1) MetricaPredictiva
             ├──→ (N) SolicitudServicio
             ├──→ (N) Intervencion
             └──→ (N) HistorialEstadoActivo
```

### Modelos principales

| Modelo                | Descripción                                                   |
|-----------------------|---------------------------------------------------------------|
| `Regional`            | Sedes regionales (La Paz, Cochabamba, etc.)                   |
| `Ubicacion`           | Salas/oficinas con altitud, temperatura y humedad             |
| `Gerencia`            | Departamentos dentro de una Regional                          |
| `Cargo`               | Puestos laborales dentro de una Gerencia                      |
| `GrupoContable`       | Categorías contables con vida útil y coeficiente depreciación |
| `TipoActivo`          | Subcategoría del grupo contable (ej: Laptop, Impresora)       |
| `PerfilUsuario`       | Extensión del User de Django (CI, extensión, teléfono, cargo) |
| `Activo`              | **Núcleo del sistema** — equipo con código TAMEP, serial, QR  |
| `Designacion`         | Asignación de un activo a un usuario (permanente o temporal)  |
| `Transferencia`       | Movimiento de activo entre funcionarios o devolución          |
| `BajaActivo`          | Desincorporación definitiva de un activo                      |
| `SolicitudServicio`   | Ticket de soporte/mantenimiento                               |
| `Intervencion`        | Registro técnico de trabajo realizado sobre un activo         |
| `MetricaPredictiva`   | MTBF, MTTR, probabilidad de falla, índice salud Fuzzy         |
| `HistorialEstadoActivo` | Log automático de cambios de estado, ubicación, situación   |

### modelo `Activo` — Campos clave

| Campo                  | Tipo           | Descripción                                    |
|------------------------|----------------|------------------------------------------------|
| `codigo_tamep`         | CharField(50)  | Código único institucional                     |
| `codigo_tab`           | CharField(50)  | Código histórico/legado                        |
| `nombre_especifico`    | CharField(255) | Ej: "Dell Latitude 5420"                       |
| `serie`                | CharField(100) | Número de serie (único)                        |
| `fecha_adquisicion`    | DateField      | Fecha de compra                                |
| `costo`                | Decimal(12,2)  | Valor de adquisición en Bs.                    |
| `estado_actual`        | CharField      | `Bueno`, `Regular`, `Malo`                     |
| `situacion_activo`     | CharField      | `Disponible`, `Asignado`, `Mantenimiento`, `Baja` |
| `perfil_uso`           | CharField      | `N/A`, `Oficina`, `Intensivo`, `Critico`       |
| `horas_uso_actual`     | Float          | Horas acumuladas de uso                        |
| `contador_fallas`      | Integer        | Total de fallas registradas                    |
| `contador_correctivos` | Integer        | Mantenimientos correctivos realizados          |
| `contador_preventivos` | Integer        | Mantenimientos preventivos realizados          |
| `contador_mejoras`     | Integer        | Mejoras/upgrades aplicados                     |
| `imagen_qr`            | ImageField     | QR generado automáticamente al guardar         |

**Propiedades calculadas:**
- `vida_util_total_meses` → Vida útil del grupo contable × 12
- `meses_restantes` → Meses de vida útil restante desde fecha de adquisición
- `edad_ajustada_meses` → Edad real menos 6 meses por cada mejora (para el modelo de IA)

---

## 4. Endpoints de la API

> Todos los endpoints requieren autenticación JWT (`Authorization: Bearer <token>`) excepto donde se indique lo contrario.

### Paginación y throttling

| Concepto | Valor |
|----------|-------|
| Clase de paginación | `PaginacionEstandar` (PageNumberPagination) |
| Tamaño por defecto | `?page=` y `?page_size=50` |
| Tope de página | `?page_size=N` con máximo **100** (evita volcados de tablas completas) |
| Formato de respuesta | `{ count, next, previous, results }` |

Los endpoints que alimentan **dropdowns** o que el frontend consume como **array plano** no se paginan (`pagination_class = None`): catálogos (`/api/regionales/`, `/api/grupos-contables/`, `/api/tipos-activos/`, `/api/gerencias/`, `/api/cargos/`, `/api/users/`), `/api/activos/parametros_iniciales/`, los auxiliares de `/api/transferencias/` y `/api/gestion-activos/`.

**Throttling** (solo en los endpoints de autenticación, vía `ScopedRateThrottle`):

| Scope | Límite | Endpoints |
|-------|--------|-----------|
| `login` | 20/min | `POST /api/login/` |
| `register` | 10/hora | `POST /api/register/` |
| `refresh` | 30/min | `POST /api/token/refresh/` |

Al superar el límite la API responde **429** con mensaje en español.

### 4.1. Login y Perfil de Usuario

| Método | Endpoint              | Descripción                       | Auth   |
|--------|-----------------------|-----------------------------------|--------|
| POST   | `/api/login/`         | Autenticación (obtener JWT)       | ❌ No  |
| POST   | `/api/token/refresh/` | Renovar access token              | ❌ No  |
| GET    | `/api/me/`            | Obtener perfil del usuario actual | ✅ Sí  |
| PATCH  | `/api/me/`            | Actualizar perfil (nombre, CI, teléfono, contraseña) | ✅ Sí |

**GET `/api/me/`** responde:
```json
{
  "id": 1,
  "username": "jperez",
  "first_name": "Juan",
  "last_name": "Pérez",
  "email": "jperez@tamep.bo",
  "ci": "12345678",
  "extension": "LP",
  "telefono": "71234567",
  "cargo_nombre": "Técnico",
  "regional_nombre": "La Paz",
  "gerencia_nombre": "TI"
}
```

**PATCH `/api/me/`** acepta:
```json
{
  "first_name": "Juan Pablo",
  "email": "nuevo@tamep.bo",
  "telefono": "72000000",
  "password": "nuevaContraseña123"
}
```

---

### 4.2. Activos

**Base:** `/api/activos/`

| Método | Endpoint                                      | Descripción                                      |
|--------|-----------------------------------------------|--------------------------------------------------|
| GET    | `/api/activos/`                               | Listar todos los activos (paginado, filtrable)   |
| POST   | `/api/activos/`                               | Crear nuevo activo                               |
| GET    | `/api/activos/{id}/`                          | Detalle de un activo                             |
| PUT    | `/api/activos/{id}/`                          | Actualizar activo completo                       |
| PATCH  | `/api/activos/{id}/`                          | Actualizar parcialmente                          |
| DELETE | `/api/activos/{id}/`                          | Eliminar activo                                  |
| GET    | `/api/activos/{id}/historial/`                | Historial de cambios de estado del activo        |
| GET    | `/api/activos/parametros_iniciales/`           | Grupos contables + ubicaciones (para formularios)|
| GET    | `/api/activos/personal_list/`                 | Lista de personal con jerarquía                  |
| GET    | `/api/activos/tipos_por_grupo/{grupo_id}/`    | Tipos de activo filtrados por grupo contable     |
| GET    | `/api/activos/grupos_contables/`              | Lista de grupos contables                        |
| GET    | `/api/activos/ubicaciones_list/`              | Lista de ubicaciones con regional                |
| GET    | `/api/activos/resumen_ia/`                    | Resumen de IA: críticos, salud degradada, etc.   |

**Filtros disponibles** (query params):
- `?situacion_activo=Asignado`
- `?estado_actual=Bueno`
- `?ubicacion_actual=3`
- `?codigo_tamep=TAM-001`
- `?search=Dell` (busca en código_tamep, serie, nombre, código_tab)

**Respuesta de un activo (GET):**
```json
{
  "id": 1,
  "codigo_tamep": "TAM-LP-001",
  "codigo_tab": "HIST-001",
  "nombre_especifico": "Dell Latitude 5420",
  "descripcion": "Laptop para oficina",
  "serie": "ABC123XYZ",
  "fecha_adquisicion": "2023-01-15",
  "costo": "8500.00",
  "estado_actual": "Bueno",
  "situacion_activo": "Asignado",
  "perfil_uso": "Oficina",
  "horas_uso_actual": 2500.0,
  "tipo_nombre": "Laptop",
  "grupo_nombre": "Equipo de Computación",
  "ubicacion_nombre": "Sala 101",
  "regional_nombre": "La Paz",
  "vida_util_total_meses": 60,
  "meses_restantes": 22,
  "edad_ajustada_meses": 38,
  "imagen_qr": "/media/qrs/qr-TAM-LP-001.png",
  "imagen_activo": "/media/activos_fotos/dell_lat.jpg",
  "prediccion": {
    "mtbf": 1200.5,
    "mttr": 3.2,
    "probabilidad_falla": 15.3,
    "indice_salud_fuzzy": 78.50,
    "recomendacion_ia": "Estado estable.",
    "horas_soporte_acumuladas": 12.5
  }
}
```

---

### 4.3. Designaciones (Asignaciones)

**Base:** `/api/designaciones/`

| Método | Endpoint                                      | Descripción                                     |
|--------|-----------------------------------------------|-------------------------------------------------|
| GET    | `/api/designaciones/`                         | Listar todas las designaciones                  |
| POST   | `/api/designaciones/`                         | Crear nueva designación (asignar activo)        |
| GET    | `/api/designaciones/{id}/`                    | Detalle de designación                          |
| POST   | `/api/designaciones/{id}/devolver/`           | Devolver activo (cierra custodia)               |
| GET    | `/api/designaciones/estructura_completa/`     | Personal completo con jerarquía organizacional  |

**Filtros:** `?activo__codigo_tamep=TAM-001`, `?usuario__username=jperez`, `?tipo=Permanente`, `?esta_activa=true`

**POST (crear asignación):**
```json
{
  "activo": 5,
  "usuario": 2,
  "regional": 1,
  "gerencia": 3,
  "cargo": 7,
  "ubicacion": 12,
  "tipo": "Permanente",
  "esta_activa": true,
  "observaciones": "Asignación para nuevo funcionario"
}
```

**Lógica de negocio al crear:**
1. El activo debe estar en situación `Disponible`.
2. Se ejecuta `perform_create` →  cambia `activo.situacion_activo` a `Asignado`.
3. La transacción es atómica (todo o nada).

**POST `/{id}/devolver/`:**
- Cierra la designación (`esta_activa = False`, `fecha_fin_real = ahora`).
- Cambia el activo a `Disponible`.

---

### 4.4. Transferencias

**Base:** `/api/transferencias/`

| Método | Endpoint                                               | Descripción                                     |
|--------|--------------------------------------------------------|-------------------------------------------------|
| GET    | `/api/transferencias/`                                 | Listar transferencias                           |
| POST   | `/api/transferencias/`                                 | Crear nueva transferencia                       |
| GET    | `/api/transferencias/{id}/`                            | Detalle                                         |
| GET    | `/api/transferencias/buscar-activo/?codigo=TAM-001`    | Buscar activo por código + info del custodio    |
| GET    | `/api/transferencias/estructura_personal/`             | Personal con jerarquía para selectores          |
| GET    | `/api/transferencias/listar_ubicaciones/`              | Lista de ubicaciones                            |
| GET    | `/api/transferencias/regionales/`                      | Lista de regionales                             |
| GET    | `/api/transferencias/gerencias/?regional={id}`         | Gerencias filtradas por regional                |
| GET    | `/api/transferencias/cargos/?gerencia={id}`            | Cargos filtrados por gerencia                   |
| GET    | `/api/transferencias/usuarios/?cargo={id}`             | Usuarios filtrados por cargo                    |

**Búsqueda de activo para transferencia:**

`GET /api/transferencias/buscar-activo/?codigo=TAM-LP-001`
```json
{
  "activo_id": 5,
  "descripcion": "Dell Latitude 5420 | S/N: ABC123XYZ",
  "codigo_tamep": "TAM-LP-001",
  "ubicacion_actual_id": 12,
  "ubicacion_actual_nombre": "Sala 101",
  "emisor": {
    "id": 2,
    "nombre": "Juan Pérez",
    "regional": "La Paz",
    "gerencia": "TI",
    "cargo": "Técnico"
  }
}
```

**POST (crear transferencia):**
```json
{
  "activo": 5,
  "emisor": 2,
  "receptor": 8,
  "tipo": "TR",
  "reg_receptor": 2,
  "ger_receptor": 5,
  "car_receptor": 10,
  "ubicacion_destino": 15,
  "num_acta": "TRANS-2026-0015",
  "motivo": "Reasignación por cambio de funciones"
}
```

**Lógica automática al crear:**
1. Valida que el emisor sea el custodio actual.
2. Cierra la designación actual del emisor (`esta_activa = False`).
3. Si es tipo `TR`: crea nueva designación para el receptor.
4. Si es tipo `DE` (Devolución): libera el activo como `Disponible`.
5. Actualiza la ubicación del activo.

---

### 4.5. Baja de Activos

**Base:** `/api/operacion-baja/`

| Método | Endpoint                                          | Descripción                            |
|--------|---------------------------------------------------|----------------------------------------|
| GET    | `/api/operacion-baja/`                            | Listar bajas registradas               |
| POST   | `/api/operacion-baja/`                            | Registrar baja de activo               |
| GET    | `/api/operacion-baja/{id}/`                       | Detalle de baja                        |
| GET    | `/api/operacion-baja/datos_formulario/`           | Datos para el formulario (regionales, encargados) |
| POST   | `/api/operacion-baja/{activo_id}/procesar_baja/`  | Baja guiada desde la UI (`RealizarBaja.vue`) |
| GET    | `/api/operacion-baja/{id}/imprimir_acta_baja/`    | Acta de baja en **PDF**                |

> ⚠️ **Ojo con el `pk` de cada acción:** en `procesar_baja` el `{id}` de la URL es el **ID del activo**; en `imprimir_acta_baja` es el **ID del registro de baja** (detalle `True`).

**POST `/{activo_id}/procesar_baja/` (baja guiada):**

Payload en `multipart/form-data` con los nombres que usa el frontend:

```json
{
  "regional_id": "1",
  "usuario_id": "3",
  "motivo": "Obsolescencia total del equipo",
  "documento": "<archivo_pdf (opcional)>"
}
```

| Campo | Obligatorio | Notas |
|-------|-------------|-------|
| `regional_id` | ✅ | Regional administrativa que procesa la baja |
| `usuario_id` | ✅ | Responsable que **autoriza** la baja; debe estar activo y, si tiene perfil con regional, coincidir con `regional_id` |
| `motivo` | ✅ | Justificación libre |
| `documento` | ❌ | PDF de respaldo (informe técnico o denuncia); si se envía, debe terminar en `.pdf` |

**Respuesta (201):**
```json
{
  "detail": "Activo dado de baja y desvinculado correctamente.",
  "baja": { "id": 1, "num_baja": "BJA-2026-0001", "activo": 5, "solicitante": 3, "...": "..." },
  "activo": {
    "id": 5,
    "codigo_tamep": "TAM-LP-001",
    "situacion_activo": "Baja",
    "estado_actual": "Malo"
  }
}
```

**Validaciones:** `400` si falta algún campo o el responsable no corresponde a la regional; `409` si el activo ya tiene baja registrada.

**Lógica automática (atómica, vía `BajaActivo.save()`):**
1. Genera el correlativo `num_baja` (`BJA-{año}-{correlativo}`).
2. Cierra las designaciones activas del activo (`esta_activa = False`, `fecha_fin_real = ahora`, `observaciones = "CIERRE POR BAJA - REF: {num_baja}"`).
3. Cambia `situacion_activo = 'Baja'` y `estado_actual = 'Malo'`.
4. Quita la ubicación actual (`ubicacion_actual = None`).
5. Deja el rastro en el `HistorialEstadoActivo` y en la **auditoría** (`LogEntry`).

**POST (crear baja directa, vía CRUD):**
```json
{
  "activo": 5,
  "solicitante": 1,
  "num_baja": "BAJA-2026-001",
  "motivo": "Obsolescencia Tecnológica",
  "descripcion_tecnica": "Equipo con 8 años de antigüedad, componentes sin soporte.",
  "documento_respaldo": "<archivo_pdf>"
}
```

**GET `/{id}/imprimir_acta_baja/`:** devuelve el **acta en PDF** (carta, márgenes de 2 cm) con el mismo criterio visual que el acta de transferencia: identificación del bien, datos de la baja, custodia al momento de la baja (designación cerrada) y firmas. Respuesta `FileResponse` con `content_type: application/pdf` y `Content-Disposition: inline; filename=Acta_Baja_<num_baja>.pdf`.

---

### 4.6. Solicitudes de Servicio

**Base:** `/api/solicitudes/`

| Método | Endpoint                | Descripción                                        |
|--------|-------------------------|----------------------------------------------------|
| GET    | `/api/solicitudes/`     | Listar solicitudes (admin ve todas, usuario solo las suyas) |
| POST   | `/api/solicitudes/`     | Crear ticket de soporte/mantenimiento              |
| GET    | `/api/solicitudes/{id}/`| Detalle de solicitud                               |

**Seguridad:** Los usuarios normales solo ven solicitudes propias. Admin/Staff ve todas.

**POST (crear solicitud):**
```json
{
  "activo": 5,
  "tipo_solicitud": "MANTENIMIENTO",
  "severidad": "2",
  "descripcion_problema": "El equipo se apaga inesperadamente.",
  "requerimiento": "Revisión de fuente de poder y sistema de enfriamiento."
}
```

> El campo `solicitante` se asigna automáticamente al usuario autenticado.  
> El `num_ticket` se genera automáticamente con formato `TKT-{año}-{correlativo}`.

**Estado derivado:** Se calcula automáticamente según las intervenciones:
- Sin intervenciones → `"Pendiente"`
- Con intervención sin fecha_fin → `"En Proceso"`
- Todas con fecha_fin → `"Cerrado"`

---

### 4.7. Intervenciones

**Base:** `/api/intervenciones/`

| Método | Endpoint                                          | Descripción                                     |
|--------|---------------------------------------------------|-------------------------------------------------|
| GET    | `/api/intervenciones/`                            | Listar intervenciones                           |
| POST   | `/api/intervenciones/`                            | Registrar intervención técnica                  |
| GET    | `/api/intervenciones/{id}/`                       | Detalle                                         |
| GET    | `/api/intervenciones/historial/{activo_id}/`      | Hoja de vida técnica del activo                 |

**POST (registrar intervención):**
```json
{
  "solicitud": 3,
  "activo": 5,
  "tipo_mantenimiento": "Correctivo",
  "categoria_falla": "Hardware",
  "modalidad": "Sitio",
  "diagnostico_previo": "Fuente de poder defectuosa",
  "detalles_reparacion": "Reemplazo de fuente de poder 500W",
  "recomendacion_tecnica": "Instalar UPS dedicado",
  "verificado_por": "Ing. Carlos López",
  "conclusion": "Equipo funcional, monitorear rendimiento",
  "fecha_inicio": "2026-03-01T08:00:00Z",
  "fecha_fin": "2026-03-01T12:30:00Z",
  "lectura_uso_equipo": 2650.0,
  "costo_materiales": 350.00,
  "severidad_falla": 3,
  "estado_post_intervencion": "Bueno"
}
```

> `tecnico` se asigna automáticamente al usuario autenticado.

**Lógica automática al guardar:**
1. Incrementa contadores del activo (`contador_correctivos`, `contador_preventivos`, etc.).
2. Actualiza `horas_uso_actual` del activo.
3. Si el grupo contable tiene IA predictiva habilitada:
   - Recalcula **MTBF** (solo para correctivos).
   - Recalcula **MTTR**.
   - Ejecuta análisis prescriptivo (recalcula `probabilidad_falla`, `indice_salud_fuzzy`, `recomendacion_ia`).
   - Actualiza `horas_soporte_acumuladas`.

---

### 4.8. Dashboard

| Método | Endpoint                    | Descripción                             |
|--------|-----------------------------|-----------------------------------------|
| GET    | `/api/dashboard/stats/`    | Estadísticas completas para el dashboard|

**Respuesta:**
```json
{
  "cards": {
    "total_activos": 150,
    "criticos_ia": 3,
    "salud_global": 72.5,
    "meses_recuperados": 18,
    "total_mejoras": 3,
    "mtbf_avg": 1500.3,
    "mttr_avg": 4.2,
    "proximo_mantenimiento": {
      "activo": "HP ProBook 450",
      "codigo": "TAM-CB-022",
      "probabilidad": 85.3
    }
  },
  "charts": {
    "mantenimiento": {
      "labels": ["Oct", "Nov", "Dic", "Ene", "Feb", "Mar"],
      "preventivos": [2, 4, 1, 3, 5, 2],
      "correctivos": [1, 0, 3, 2, 1, 4]
    },
    "perfiles": [
      { "perfil_uso": "Oficina", "total": 80 },
      { "perfil_uso": "Intensivo", "total": 45 }
    ]
  },
  "top_criticos": [
    { "nombre": "Lenovo ThinkPad", "codigo": "TAM-LP-005", "probabilidad": 92.1 }
  ],
  "regionales": [
    { "nombre": "La Paz", "cantidad": 85, "salud": 68.3 },
    { "nombre": "Cochabamba", "cantidad": 42, "salud": 81.7 }
  ]
}
```

---

### 4.9. Reportes y Gestión de Activos

**Base:** `/api/gestion-activos/` (Solo lectura — `ReadOnlyModelViewSet`)

| Método | Endpoint                                  | Descripción                                   |
|--------|-------------------------------------------|-----------------------------------------------|
| GET    | `/api/gestion-activos/`                   | Activos con info extendida + historial custodios |
| GET    | `/api/gestion-activos/{id}/`              | Detalle extendido de un activo                |

**Filtros avanzados:**
- `?grupo_contable_seleccionado=1`
- `?tipo_activo=3`
- `?ubicacion_actual__regional=2`
- `?situacion_activo=Asignado`
- `?estado_actual=Bueno`
- `?perfil_uso=Oficina`
- `?search=Dell`

**Ordenamiento** (`?ordering=` acepta varios campos separados por coma; el `-` invierte el orden):

| Campo aceptado | Campo real en el ORM |
|----------------|----------------------|
| `fecha_adquisicion` | `Activo.fecha_adquisicion` |
| `costo` | `Activo.costo` |
| `horas_uso_actual` | `Activo.horas_uso_actual` |
| `probabilidad_falla` | `MetricaPredictiva.probabilidad_falla` (relación `prediccion`) |
| `indice_salud_fuzzy` | `MetricaPredictiva.indice_salud_fuzzy` (relación `prediccion`) |
| `prediccion__probabilidad_falla` | igual que `probabilidad_falla`, pero escrito como ruta ORM |
| `prediccion__indice_salud_fuzzy` | igual que `indice_salud_fuzzy`, pero escrito como ruta ORM |

Los dos primeros son **nombres amigables** para el frontend (`ModuloPredictivo.vue` envía `?ordering=-probabilidad_falla`); el backend los traduce a la ruta de la relación `prediccion` antes del `order_by()`. Los activos sin métrica de IA quedan con el valor vacío y no rompen el orden.

**Campos añadidos al serializer** (además de los de `historial_custodios`):

| Campo | Descripción |
|-------|-------------|
| `prediccion` | Objeto anidado con `MetricaPredictiva` (`mtbf`, `mttr`, `probabilidad_falla`, `indice_salud_fuzzy`, `recomendacion_ia`, `horas_soporte_acumuladas`, `ultima_actualizacion`) |
| `probabilidad_falla` | Misma probabilidad aplanada a nivel del activo (número, `null` si no hay métrica) |
| `estado_ia` | Nivel de riesgo derivado de la probabilidad (`obtener_nivel_riesgo`) |
| `custodio_actual` | Nombre completo del custodio de la designación activa; `null` si no hay asignación |
| `contador_preventivos` | Mantenimientos preventivos acumulados |

`custodio_actual` se resuelve sobre las designaciones ya prefetcheadas en el queryset (sin N+1): es la designación con `esta_activa = True`.

**Respuesta incluye `historial_custodios` y `prediccion`:**
```json
{
  "id": 5,
  "codigo_tamep": "TAM-LP-001",
  "tipo_nombre": "Laptop",
  "custodio_actual": "Juan Pérez",
  "contador_preventivos": 4,
  "probabilidad_falla": 15.3,
  "estado_ia": "Bajo",
  "prediccion": {
    "mtbf": 1200.5,
    "mttr": 3.2,
    "probabilidad_falla": 15.3,
    "indice_salud_fuzzy": 78.50,
    "recomendacion_ia": "Estado estable.",
    "horas_soporte_acumuladas": 12.5,
    "ultima_actualizacion": "2026-03-01T12:30:00Z"
  },
  "historial_custodios": [
    {
      "id": "tra-5",
      "fecha": "15/02/2026",
      "tipo": "Transferencia entre Funcionarios",
      "emisor": "Juan Pérez",
      "receptor": "María López",
      "acta": "TRANS-2026-0003",
      "detalle": "Cambio de funciones",
      "color": "primary"
    },
    {
      "id": "des-1",
      "fecha": "01/01/2024",
      "tipo": "ASIGNACIÓN (Permanente)",
      "emisor": "ALMACÉN CENTRAL",
      "receptor": "Juan Pérez",
      "acta": "S/N",
      "detalle": "Asignación de cargo",
      "color": "success"
    }
  ]
}
```

### Catálogos auxiliares (Solo lectura)

| Endpoint                                   | Descripción               |
|--------------------------------------------|---------------------------|
| GET `/api/regionales/`                     | Lista de regionales       |
| GET `/api/grupos-contables/`               | Lista de grupos contables |
| GET `/api/tipos-activos/`                  | Lista de tipos de activo  |
| GET `/api/tipos-activos/?grupo_contable=1` | Tipos por grupo contable  |

---

### 4.10. Catálogos (Parámetros)

Endpoint auxiliar para poblar formularios:

| Endpoint                            | Respuesta                                    |
|-------------------------------------|----------------------------------------------|
| `GET /api/activos/parametros_iniciales/` | `{ grupos: [...], ubicaciones: [...] }`  |
| `GET /api/activos/tipos_por_grupo/{id}/` | `[{ id, nombre }]`                      |

---

### 4.11. Notificaciones y Auditoría

**Notificaciones** — Base: `/api/notificaciones/` (solo ve las propias; no acepta `POST`/`DELETE` directos)

| Método | Endpoint                                 | Descripción                                  |
|--------|------------------------------------------|----------------------------------------------|
| GET    | `/api/notificaciones/`                   | Listar notificaciones del usuario actual     |
| GET    | `/api/notificaciones/no_leidas/`         | Contador: `{ "count": 3 }`                   |
| PATCH  | `/api/notificaciones/{id}/marcar_leida/` | Marcar una notificación como leída           |
| PATCH  | `/api/notificaciones/{id}/`              | Actualización parcial (ej: `leida: true`)    |
| POST   | `/api/notificaciones/marcar_todas_leidas/` | Marcar todas como leídas                   |

Las notificaciones se generan automáticamente (registro de activos, solicitudes de servicio, mantenimientos atendidos).

**Auditoría** — Base: `/api/auditoria/` (admin o superior; últimas 500 entradas, más recientes primero)

| Método | Endpoint                  | Descripción                                |
|--------|---------------------------|--------------------------------------------|
| GET    | `/api/auditoria/`         | Bitácora de acciones (`LogEntry` de Django)|
| GET    | `/api/auditoria/{id}/`    | Detalle de una entrada                     |

**Formato de cada entrada:**
```json
{
  "id": 12,
  "action_time": "2026-03-01T12:30:00Z",
  "usuario": "jperez",
  "nombre_usuario": "Juan Pérez",
  "action_flag": 2,
  "accion": "MODIFICACIÓN",
  "objeto": "TAM-LP-001 — Dell Latitude 5420",
  "tabla": "activo",
  "mensaje": "PATCH /api/activos/5/ — estado_actual=Bueno; horas_uso_actual=2650.0"
}
```

**Qué se audita desde la API:** crear, modificar y eliminar en `activos`, `designaciones`, `transferencias`, `operacion-baja` (incluye la acción `procesar_baja`), `solicitudes`, `intervenciones` y `users`. El registro lo hace `AuditoriaApiMixin` (`activos/views/auditoria.py`), que envuelve `perform_create` / `perform_update` / `perform_destroy`:

- **Formato del mensaje:** `MÉTODO /ruta — campo=valor; ...`
- Los **campos sensibles** (contraseñas, tokens, CI) se registran como `clave=[oculto]`.
- Se listan hasta **15 campos** y cada valor se trunca a **80 caracteres**.
- Para usuarios no autenticados no se registra nada (`LogEntry.user` es `NOT NULL`).

---

## 5. Motor de IA Predictiva

El sistema integra un **motor de Inteligencia Artificial** para mantenimiento predictivo. Solo se activa para activos cuyo `GrupoContable` tiene `tiene_mantenimiento_predictivo = True`.

### 5.1. Random Forest (Predicción de Falla)

Archivo: `ia_engine.py` — Implementado como **Singleton**.

**Modelo:** Un Random Forest Classifier entrenado con `scikit-learn`, serializado con `joblib`.

**Features de entrada:**

| Feature           | Fuente                             |
|-------------------|------------------------------------|
| `edad_ajustada`   | `activo.edad_ajustada_meses`       |
| `mtbf`            | `metricas.mtbf`                    |
| `mttr`            | `metricas.mttr`                    |
| `fallas`          | `activo.contador_fallas`           |
| `uso`             | 0=N/A, 1=Intensivo, 2=Crítico     |

**Salida:** `probabilidad_falla` (0-100%) → almacenada en `MetricaPredictiva`.

### 5.2. Lógica Difusa (Índice de Salud)

Archivo: `utils_ia.py` → función `calcular_salud_logic()`

**Fórmula:**
```
Salud = 100 - (Impacto Edad) - (Correctivos × 8) + (Preventivos × 4) - (Perfil Uso)
```

Donde:
- **Impacto Edad** = `min(60, (edad_ajustada / vida_util_total) × 50)`
- **Perfil Uso:** Crítico = -10, Intensivo = -5
- Resultado limitado a rango `[0, 100]`

### 5.3. Métricas de Confiabilidad

Archivo: `utils_metricas.py`

| Métrica | Fórmula                                                         | Significado                       |
|---------|-----------------------------------------------------------------|-----------------------------------|
| **MTBF** | `Σ(uptime entre fallas) / N°fallas`                           | Tiempo promedio entre fallas (horas) — Confiabilidad |
| **MTTR** | `Σ(tiempo reparación correctivos) / N°correctivos`             | Tiempo promedio de reparación (horas) — Mantenibilidad |

### 5.4. Análisis Prescriptivo

Se genera automáticamente al ejecutar `generar_analisis_prescriptivo()`:

- **Probabilidad > 70%:** `"ALERTA IA: Alta probabilidad de falla"`
- **MTTR alto + MTBF bajo:** `"SATURACIÓN: Evaluar reemplazo"`
- **Años ≥ vida útil normativa:** `"OBSOLESCENCIA NORMATIVA"`
- **Años ≥ 6 (técnica):** `"OBSOLESCENCIA TÉCNICA"`

---

## 6. Signals y Hooks Automáticos

El sistema utiliza señales de Django para automatizar procesos:

| Señal                        | Trigger                | Acción                                              |
|------------------------------|------------------------|-----------------------------------------------------|
| `post_save(User)`            | Crear usuario          | Crea `PerfilUsuario` automáticamente                |
| `post_save(Activo)` (create) | Nuevo activo           | Crea `MetricaPredictiva` si el grupo contable tiene IA |
| `pre_save(Activo)`           | Antes de guardar       | Captura estado/ubicación/situación anteriores        |
| `post_save(Activo)` (update) | Actualizar activo      | Registra en `HistorialEstadoActivo` los cambios      |
| `Activo.save()`              | Siempre                | Genera/regenera QR, asigna ubicación inicial         |
| `Intervencion.save()`        | Nueva intervención     | Actualiza contadores, recalcula IA                   |
| `Designacion.save()`         | Nueva designación      | Cambia estado del activo a `Asignado`/`Disponible`   |
| `Transferencia.save()`       | Nueva transferencia    | Cierra custodia anterior, crea nueva, mueve activo   |
| `BajaActivo.save()`          | Nueva baja             | Cierra custodias, marca activo como `Baja`           |

---

## 7. Configuración del Proyecto

### Base de datos
- **Motor:** MySQL 
- **Modo SQL:** `STRICT_TRANS_TABLES`

### CORS

Orígenes permitidos (`CORS_ALLOWED_ORIGINS` en `core/settings.py`):

```
https://siaem.tamep.bo
http://localhost:8080          https://localhost:3443
http://localhost:3000
http://192.168.3.232:8080
http://192.168.1.241:8080      http://192.168.1.241:3000
https://192.168.1.241:3443
http://11.0.3.225:8080         http://11.0.3.225:3000
https://11.0.3.225:3443
```

### Seguridad

El repositorio trae estas flags en **False** (correcto para desarrollo local y para este entorno de pruebas). En el servidor de producción hay que activarlas por variable de entorno o ajustando `core/settings.py`:

| Flag | En el repo | En producción |
|------|------------|---------------|
| `SECURE_SSL_REDIRECT` | `False` | `True` (redirige a HTTPS) |
| `SESSION_COOKIE_SECURE` | `False` | `True` |
| `CSRF_COOKIE_SECURE` | `False` | `True` |
| `DEBUG` | `False` por defecto; se enciende con `DJANGO_DEBUG=true` | `False` |

### Zona horaria
- `TIME_ZONE = 'America/La_Paz'`
- `LANGUAGE_CODE = 'es-es'`

### Endpoint QR público
`GET /activo/detalle/{codigo_tamep}/` — Renderiza una página HTML con los datos del activo al escanear el código QR (sin autenticación).

---

> **Nota:** Los endpoints del router de DRF siguen el estándar REST automático:
> - `GET /api/{recurso}/` → Listar
> - `POST /api/{recurso}/` → Crear
> - `GET /api/{recurso}/{id}/` → Detalle
> - `PUT /api/{recurso}/{id}/` → Actualizar completo
> - `PATCH /api/{recurso}/{id}/` → Actualizar parcial
> - `DELETE /api/{recurso}/{id}/` → Eliminar
