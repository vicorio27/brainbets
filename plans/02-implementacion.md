# Plan de Implementación PoC - BrainBets

## Fecha: 2026-06-10
## Estado: Completado
## Duración: 4-5 semanas estimado

---

## Resumen

Este plan documenta la implementación end-to-end de la plataforma BrainBets v1 (PoC). El objetivo fue hacer funcionar todo el stack: n8n + FastAPI + Vue.js + Docker Compose, con datos de prueba realistas.

## Fases Implementadas

### ✅ Fase 0: Bootstrap (Días 1-2)
**Objetivo**: Estructura base, Docker Compose, schemas

**Tareas completadas**:
- Directorios: `backend/src/`, `frontend/src/`, `n8n/workflows/`, `storage/`, `schemas/`
- `docker-compose.yml` con n8n, backend, frontend, nginx
- `Dockerfile` para backend (Python 3.12) y frontend (Node 20 + Nginx)
- JSON schemas: `matches.schema.json`, `predictions.schema.json`, `results.schema.json`
- `scripts/seed_data.py` - Generador de datos dummy

**Entregables**:
- `docker-compose up -d` levanta todo el stack
- n8n: http://localhost:5678
- Backend: http://localhost:8000
- Frontend: http://localhost

### ✅ Fase 1: n8n Data Collection (Días 3-6)
**Objetivo**: Generar `matches_*.json` automáticamente

**Tareas completadas**:
- Workflow n8n exportado: `n8n/workflows/data_collection_pipeline.json`
- Trigger Cron (06:00, 12:00, 18:00)
- HTTP Request nodes a Flashscore (con User-Agent)
- Nodos de fallback: generan datos de tenis y fútbol realistas
- Merge de datos en estructura JSON válida
- Escritura a `storage/matches/matches_*.json`
- Notificación Telegram (template listo, requiere configurar Chat ID)

**Riesgo mitigado**: Fallback implementado para no bloquear desarrollo si el scraping falla

**Estructura del archivo**:
```json
{
  "generatedAt": "2026-06-10T06:00:00",
  "tennis": [...],
  "football": [...]
}
```

### ✅ Fase 2: n8n Prediction Pipeline (Días 7-10)
**Objetivo**: Leer matches y generar `predictions_*.json`

**Tareas completadas**:
- Workflow n8n exportado: `n8n/workflows/prediction_pipeline.json`
- Trigger Cron (06:15, después de Data Collection)
- Lectura de último archivo `matches_*.json`
- Validación de estructura contra schema
- Nodo "Build Prompts": transforma matches a JSON estructurado para OpenCode Go
- HTTP Request a `http://host.docker.internal:3000/api/predict`
- Fallback: generador de predicciones con confianza realista (65-95%)
- Escritura a `storage/predictions/predictions_*.json`
- Notificación Telegram

**Prompts para OpenCode Go**:
- Tenis: Winner, Total Aces, Over/Under Games, Handicap, First Set
- Fútbol: Winner, Over 2.5 Goals, Both Teams Score, Corners, Double Chance
- 3 predicciones por partido con confianza y reasoning

**Estructura del archivo**:
```json
{
  "generatedAt": "2026-06-10T06:15:00",
  "predictions": [
    {
      "predictionId": "PRED001",
      "matchId": "TEN001",
      "sport": "tennis",
      "market": "Winner",
      "prediction": "Carlos Alcaraz",
      "confidence": 87,
      "reasoning": "Mejor forma reciente",
      "status": "PENDING"
    }
  ]
}
```

### ✅ Fase 3: n8n Validation Pipeline (Días 11-13)
**Objetivo**: Validar predicciones y generar `results_*.json`

**Tareas completadas**:
- Workflow n8n exportado: `n8n/workflows/validation_pipeline.json`
- Trigger Cron (23:00)
- Lectura de último archivo `predictions_*.json`
- Parseo y validación
- Nodo de validación: compara predicción vs resultado real (fallback simulado, 70% success rate)
- Escritura a `storage/results/results_*.json`
- Cálculo de accuracy: total, successful, failed, accuracy %
- Notificación Telegram con resumen

**Estructura del archivo**:
```json
{
  "generatedAt": "2026-06-10T23:00:00",
  "results": [
    {
      "predictionId": "PRED001",
      "success": true,
      "actualResult": "Carlos Alcaraz",
      "validationReason": "Ganó 2-0",
      "matchScore": "6-4 6-3"
    }
  ]
}
```

### ✅ Fase 4: FastAPI Backend (Días 14-18)
**Objetivo**: API REST que lea JSON y sirva al frontend

**Tareas completadas**:
- Estructura Clean Architecture (simplificada para PoC):
  ```
  backend/src/
  ├── domain/         # (preparado para futuro)
  ├── application/
  │   └── services.py    # DataService (orquesta lecturas)
  ├── infrastructure/
  │   ├── file_store.py  # Lee último JSON de storage/
  │   └── cache.py       # In-memory cache con refresh cada 60s
  └── presentation/
      ├── schemas.py       # Pydantic models
      └── routers/         # FastAPI routers
  ```

- Endpoints implementados:
  - `GET /api/v1/matches/latest`
  - `GET /api/v1/predictions/latest`
  - `GET /api/v1/predictions/history`
  - `GET /api/v1/predictions/{id}/result`
  - `GET /api/v1/results/latest`
  - `GET /api/v1/analytics/accuracy`
  - `GET /api/v1/analytics/dashboard`
  - `GET /health`

- Features:
  - Cache en memoria con background thread
  - Logs estructurados con structlog
  - CORS habilitado para frontend
  - Cálculo de accuracy por deporte (tenis/fútbol)

### ✅ Fase 5: Vue.js Frontend (Días 19-23)
**Objetivo**: Dashboard funcional

**Tareas completadas**:
- Setup Vue 3 + Vite + TailwindCSS + Pinia
- Estructura:
  ```
  frontend/src/
  ├── views/
  │   ├── Dashboard.vue        # KPIs + partidos
  │   ├── Predictions.vue      # Tabla de predicciones
  │   ├── PredictionDetail.vue # Detalle + resultado
  │   ├── History.vue          # Histórico con filtros
  │   └── Analytics.vue        # Métricas de accuracy
  ├── components/
  │   ├── MatchCard.vue        # Tarjeta de partido
  │   ├── PredictionTable.vue  # Tabla de predicciones
  │   └── KpiCard.vue          # Tarjeta de métrica
  ├── stores/
  │   ├── api.js               # Axios (baseURL: /api/v1)
  │   ├── matches.js           # Pinia store
  │   ├── predictions.js       # Pinia store
  │   └── analytics.js         # Pinia store
  └── router/
      └── index.js             # Vue Router
  ```

- Vistas implementadas:
  - Dashboard: KPIs (partidos, predicciones, accuracy, última actualización)
  - Tablas con indicadores de confianza (barras de progreso)
  - Badges de estado (PENDING, VALIDATED, FAILED)
  - Filtros por deporte en historial
  - Detalle con resultado validado (si existe)

### ✅ Fase 6: Smoke Test End-to-End (Días 24-26)
**Objetivo**: Verificar todo funciona junto

**Tests realizados**:
- ✅ `docker-compose up -d` levanta todos los servicios
- ✅ Backend responde en `:8000` y `:80` (vía Nginx)
- ✅ Frontend sirve en `:80`
- ✅ n8n accesible en `:5678`
- ✅ API endpoints devuelven datos correctos
- ✅ Proxy `/api` funciona correctamente
- ✅ Datos dummy generados correctamente

**Servicios verificados**:
```
brainbets-n8n        Up  0.0.0.0:5678
brainbets-backend    Up  0.0.0.0:8000
brainbets-frontend   Up  0.0.0.0:80
```

## Decisiones de Implementación

### Scraping vs Fallback
- **Decisión**: Implementar fallback inmediato para no bloquear desarrollo
- **Estrategia**: HTTP Request a fuentes reales → si falla, ejecutar nodo de fallback
- **Ventaja**: El flujo n8n siempre produce output, backend y frontend nunca se bloquean

### Integración OpenCode Go
- **Decisión**: HTTP POST desde n8n
- **URL**: `http://host.docker.internal:3000/api/predict`
- **Fallback**: Si OpenCode Go no responde, nodo "Fallback Predictions" genera datos realistas
- **Ventaja**: El sistema funciona sin depender de OpenCode Go estar corriendo

### Cache Strategy
- **Decisión**: In-memory cache con polling cada 60 segundos
- **Implementación**: `InMemoryCache` lee el último archivo de cada directorio al iniciar y recarga periódicamente
- **Ventaja**: Simple, no requiere inotify ni hot-reload complejo
- **Limitación**: El backend puede tener datos "viejos" hasta 60 segundos

### Import Paths (Backend)
- **Decisión**: `from src.infrastructure...` y `from src.application...`
- **main.py**: Está en `backend/` (no en `src/`), importa `src.*`
- **Docker**: `PYTHONPATH=/app`, copia `src/` y `main.py` a `/app/`
- **Local**: `PYTHONPATH=.`, ejecutar desde `backend/`

## Comandos de Desarrollo

```bash
# Full stack (Docker)
docker-compose up -d

# Solo backend (local)
cd backend
pip install -r requirements.txt
STORAGE_PATH=../storage PYTHONPATH=. uvicorn main:app --reload

# Solo frontend (local)
cd frontend
npm install
npm run dev

# Generar datos dummy
python scripts/seed_data.py

# Detener todo
docker-compose down
```

## Próximos Pasos

1. **Configurar scraping real**: Identificar URLs/APIs de Flashscore, Sofascore, ATP
2. **Configurar Telegram**: Cambiar `YOUR_TELEGRAM_CHAT_ID` en los 3 workflows
3. **Integrar OpenCode Go real**: Configurar endpoint correcto y reemplazar fallback
4. **Tests**: Implementar pytest (backend) y vitest (frontend)
5. **Observabilidad**: Configurar structlog con salida a archivos, Prometheus metrics
6. **Validación real**: Implementar scraping de resultados post-partido

## Notas

- El sistema está diseñado para permitir cambiar de modelo IA sin modificar lógica de negocio
- La migración a PostgreSQL (si se necesita) no requiere cambios en n8n ni frontend
- Los workflows n8n deben importarse manualmente: Settings → Workflows → Import from File
