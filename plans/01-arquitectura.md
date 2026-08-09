# Plan de Arquitectura - BrainBets

## Fecha: 2026-06-10
## Estado: Implementado

---

## 1. Visión General

BrainBets es una plataforma de inteligencia de apuestas deportivas que automatiza el análisis de partidos de tenis y fútbol mediante scraping web, IA y dashboards interactivos.

## 2. Principios Arquitectónicos

### 2.1 Separación de Capas (Crítico)

| Capa | Responsabilidad | Prohibición |
|------|----------------|-------------|
| **n8n** | Scraping, normalización, generación de JSON | No ejecutar lógica Python ni llamar OpenCode Go desde código Python |
| **OpenCode Go** | Generar predicciones desde JSON estructurado | Nunca consumir HTML crudo o datos sin procesar |
| **FastAPI (BFF)** | Leer JSON, exponer REST API, servir frontend | No scraping, no predicciones, no escritura a disco |
| **Vue.js** | Dashboard UI, consumir API | No scraping, no lógica de predicciones |

### 2.2 Flujo de Datos

```
Web Scraping
    ↓
Extracción de Datos
    ↓
Normalización (n8n)
    ↓
JSON Estructurado
    ↓
OpenCode Go (IA)
    ↓
Predicciones JSON
    ↓
FastAPI (solo lectura)
    ↓
Vue.js Dashboard
```

## 3. Decisiones Clave

### 3.1 Almacenamiento File-Based (v1)
- **Decisión**: JSON files en disco, no PostgreSQL
- **Justificación**: Datos diarios y efímeros, no requieren ACID ni transacciones complejas
- **Estructura**:
  ```
  storage/
  ├── matches/matches_20260609_060000.json
  ├── predictions/predictions_20260609_061500.json
  ├── results/results_20260609_230000.json
  └── audit/scraping.log, predictions.log, validation.log
  ```

### 3.2 Backend Read-Only
- FastAPI solo lee el último archivo JSON de cada directorio
- No escribe, no modifica, no genera datos
- Cache en memoria con refresh cada 60 segundos

### 3.3 OpenCode Go Input Contract
- n8n debe normalizar TODO antes de enviar
- Solo JSON estructurado, nunca HTML
- Validaciones obligatorias: campos requeridos, tipos, nulls, duplicados
- Si falla validación: NO invocar OpenCode Go, log + Telegram

### 3.4 API HTTP vs MCP para OpenCode Go
- **Decisión**: API HTTP REST
- **Por qué**: n8n maneja HTTP nativamente con reintentos, timeout, headers
- **MCP**: Requiere servidor persistente, más complejo para flujos automatizados
- **Futuro**: El mismo JSON de entrada funciona para OpenAI/Claude/Gemini vía Adapter

## 4. Tecnologías

- **Automatización**: n8n (self-hosted en Docker)
- **AI**: OpenCode Go v1 (HTTP POST desde n8n)
- **Backend**: Python 3.12, FastAPI, Pydantic, structlog
- **Frontend**: Vue.js 3, Vite, TailwindCSS, Pinia, Axios
- **Infra**: Docker Compose, Nginx (reverse proxy)
- **Observabilidad**: structlog (logs JSON), Prometheus/Grafana (planificado)
- **Testing**: pytest, vitest (planificado, 80% coverage)

## 5. Endpoints REST (v1)

- `GET /api/v1/matches/latest` - Partidos del día
- `GET /api/v1/predictions/latest` - Predicciones del día
- `GET /api/v1/predictions/history` - Histórico
- `GET /api/v1/predictions/{id}/result` - Predicción + resultado
- `GET /api/v1/results/latest` - Resultados validados
- `GET /api/v1/analytics/accuracy` - Métricas de accuracy
- `GET /api/v1/analytics/dashboard` - Resumen dashboard
- `GET /health` - Health check

## 6. Workflows n8n

### 6.1 Data Collection Pipeline
- **Trigger**: Cron 06:00, 12:00, 18:00
- **Acción**: HTTP Request a fuentes deportivas → Fallback a datos dummy
- **Output**: `storage/matches/matches_YYYYMMDD_HHMMSS.json`
- **Notificación**: Telegram (cuenta de partidos)

### 6.2 Prediction Pipeline
- **Trigger**: Cron 06:15, 12:15, 18:15 (después de Data Collection)
- **Acción**: Leer matches → Validar → Construir prompts → HTTP POST a OpenCode Go → Fallback si falla
- **Output**: `storage/predictions/predictions_YYYYMMDD_HHMMSS.json`
- **Notificación**: Telegram (partidos analizados, predicciones totales)

### 6.3 Validation Pipeline
- **Trigger**: Cron 23:00
- **Acción**: Leer predictions → Scraping resultados reales → Comparar → Fallback simulado
- **Output**: `storage/results/results_YYYYMMDD_HHMMSS.json`
- **Notificación**: Telegram (predicciones revisadas, acertadas, fallidas, accuracy)

## 7. Normalización de Datos

### 7.1 Tennis Input (JSON)
```json
{
  "sport": "tennis",
  "player1": "Carlos Alcaraz",
  "player2": "Jannik Sinner",
  "ranking_player1": 2,
  "ranking_player2": 1,
  "surface": "Clay",
  "form_player1": "WWWWW",
  "form_player2": "WWWLW",
  "h2h": "5-4",
  "aces_avg_player1": 8.1,
  "aces_avg_player2": 7.2
}
```

### 7.2 Football Input (JSON)
```json
{
  "sport": "football",
  "home_team": "Barcelona",
  "away_team": "Liverpool",
  "league": "Champions League",
  "home_form": "WWDWW",
  "away_form": "WLWWW",
  "home_xg": 2.1,
  "away_xg": 1.8,
  "home_corners": 6.4,
  "away_corners": 5.2
}
```

## 8. Contratos de Datos (JSON Schemas)

- `schemas/matches.schema.json` - Estructura de matches.json
- `schemas/predictions.schema.json` - Estructura de predictions.json
- `schemas/results.schema.json` - Estructura de results.json

Todos los archivos deben incluir:
- `generatedAt`: ISO 8601 timestamp
- Arrays validados según schema

## 9. Evolución Futura

### Fase 1 (Actual) ✅
- File-based, n8n + OpenCode Go + FastAPI + Vue.js
- Scraping básico, fallback a datos dummy
- Dashboard simple con KPIs

### Fase 2 (Multi-modelo)
- Integrar OpenAI, Claude, Gemini
- Patrón Adapter para IA
- Ensemble de modelos

### Fase 3 (Bankroll)
- Sistema de bankroll
- Kelly Criterion
- Monte Carlo simulation

### Fase 4 (Mobile)
- Flutter app
- Telegram bot interactivo
- WhatsApp Business

## 10. Notas para Desarrolladores

- Usar `PYTHONPATH=.` al ejecutar backend localmente
- En Docker: `PYTHONPATH=/app`, entrypoint es `main.py` (no `src/main.py`)
- Frontend dev: `/api` proxy a `http://localhost:8000`
- Frontend prod: `/api` proxy a `http://backend:8000` (Docker)
- Storage: `storage/` montado en `/storage` para n8n y backend
- n8n workflows: importar manualmente desde UI (Settings → Workflows → Import)
- Seed data: `python scripts/seed_data.py` para datos de prueba
