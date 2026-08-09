# BrainBets - Sports Betting Intelligence Platform

Sistema de análisis y predicción deportiva para tenis y fútbol basado en Machine Learning, automatización mediante n8n y visualización en tiempo real.

---

# Objetivo

BrainBets es una plataforma diseñada para:

* Recolectar información deportiva automáticamente.
* Normalizar y almacenar eventos deportivos.
* Generar predicciones mediante modelos de Machine Learning especializados.
* Validar resultados automáticamente.
* Exponer información mediante APIs y dashboard web.
* Permitir interacción mediante Telegram.
* Mantener una arquitectura desacoplada y orientada a workflows.

La plataforma está diseñada bajo el principio:

> n8n orquesta la recolección y los modelos. PostgreSQL es la fuente de verdad. FastAPI solamente expone información. El frontend visualiza resultados. Los modelos generan predicciones.

---

# Estado Actual y Novedades

## Accuracy actual (2026-06-28)

```text
Total:     60.89%
Fútbol:    65.79%
Tenis:     33.33%
```

El fútbol mantiene accuracy aceptable gracias al modelo Poisson + Elo. El tenis ahora cuenta con un modelo XGBoost real entrenado sobre datos históricos 2010-2024; su impacto en accuracy se medirá en los próximos ciclos de validación.

## Últimas funcionalidades implementadas

- **Optimizaciones de pipeline de tenis (2026-07-01)**: Se aumentó la recolección de eventos de tenis de 5 a 50 (`data_collection_db`); se corrigió el cálculo de snapshots en vivo en `update_scores_tennis`; se agregó inferencia batch del modelo ML (`POST /api/v1/internal/predict/tennis-ml/batch`); el `Prediction Engine` de tenis consume el bloque `features` de `FeatureService`; se normalizan nombres de jugadores para H2H; el endpoint `/matches/tennis/enrich` devuelve stats completos; se mejoró el parser de odds de tenis; el cache de detalle de eventos subió a 300s; y el modelo ML incorpora features de fatiga con compatibilidad hacia modelos antiguos.
- **Nuevos datos históricos 2025**: Se ingirió la temporada ATP 2025 desde tennis-data.co.uk (2,644 partidos) y La Liga 2024-25 desde openfootball/Wayback Machine (380 partidos). Los modelos Elo, Poisson y XGBoost de tenis se reentrenaron con esta data ampliada.
- **Modelo ML real para tenis (XGBoost)**: Nuevo servicio `backend/src/application/tennis_ml_service.py` que entrena un clasificador XGBoost con features de Elo, Elo por superficie, ranking y forma. Expone `POST /api/v1/internal/predict/tennis-ml` para inferencia y se integra en el ensemble de `n8n/prediction_engine/tennis.py`. Entrenamiento: ~15k filas en ~10s, 99.86% test accuracy.
- **Fix parser de odds de fútbol**: El nodo `Merge Football Odds` maneja correctamente la respuesta real de RapidAPI (`response.odds.odds.matchfactMarkets` / `oddsTabMarkets`) y empareja eventos de entrada con respuestas de odds por índice.
- **H2H por evento para fútbol**: El workflow `data_collection_db` consulta `football-get-head-to-head?eventid={id}` de RapidAPI para cada evento nuevo y enriquece el partido con H2H real. Las respuestas se emparejan por índice porque el nodo HTTP no preserva los campos del item de entrada. El backend aplica H2H solo a partidos **nuevos** para no gastar llamadas de API en eventos ya recolectados.
- **H2H para tenis desde histórico DB**: Se agregó `backend/src/application/tennis_stats_service.py` que calcula el head-to-head entre jugadores a partir de partidos terminados en PostgreSQL. El endpoint `POST /api/v1/internal/matches/tennis/enrich` expone los registros H2H como cadena "wins-losses". El workflow `data_collection_db` agrupa eventos de tenis, consulta el endpoint y mergea `h2h` en cada partido antes de guardarlo. El motor de tenis (`n8n/prediction_engine/tennis.py`) utiliza este H2H real como feature en el modelo XGBoost-like.
- **Odds para fútbol**: El workflow de recolección consulta el endpoint `/football-event-odds?eventid={id}&countrycode=BR` de RapidAPI y almacena las cuotas 1X2 (`homeOdds`, `drawOdds`, `awayOdds`). El motor de fútbol usa estas cuotas normalizadas en el ensemble, con pesos dinámicos según disponibilidad de datos reales.
- **Odds para tenis**: El workflow de recolección consulta el endpoint de odds de RapidAPI (`/api/tennis/event/{id}/odds`) y almacena las cuotas en `match_competitors.pre_match_odds`. El motor de tenis usa estas cuotas normalizadas en el ensemble, con pesos dinámicos según disponibilidad de Elo real/superficie.
- **Filtrado de PENDING obsoletas**: El endpoint `/api/v1/predictions/history` oculta predicciones PENDING cuyo partido es anterior al día de ayer, evitando que predicciones abandonadas de semanas/meses aparezcan en el frontend.
- **Fix en FeatureService**: Se corrigió un bug de indentación que provocaba que `POST /api/v1/internal/features/build` cargara todos los partidos de la base de datos cuando se llamaba solo con rango de fechas, colgando el pipeline de predicciones.
- **Fix de flujos n8n**: Se reactivaron todos los workflows tras importación. Se arregló `/matches/by-date` para aceptar parámetros vacíos. Se corrigió `update_scores` para encadenar `Update Football → Update Tennis → Prepare Response`. Se cambió el paso de JSON al `Prediction Engine` a base64 + archivo temporal (`/tmp/predict_input.json`) para evitar errores por comillas simples en nombres.
- **Proxy/cache interno**: Todos los workflows de scores en vivo (fútbol y tenis) usan `POST /api/v1/internal/proxy`, con cache en PostgreSQL y backoff ante `429`.
- **Validación por ventana de fecha**: Solo se validan predicciones PENDING de hoy y ayer. Predicciones más antiguas se reportan como `skipped`.

## Roadmap de mejora de accuracy

- **Opción A - Odds para fútbol** ✅: Integrar cuotas de casas de apuestas al ensemble de fútbol (paralelo al trabajo de tenis).
- **Opción B - Modelos reales para tenis** ✅: Entrenar XGBoost/CatBoost con los datos históricos 2010+ ya cargados, en lugar de usar heurísticas.
- **Opción C - Mejor recolección de fútbol** 🔄: Traer xG, forma, posición en tabla, partidos programados y stats reales en lugar de placeholders.

---

# Arquitectura General

```text
┌─────────────────────┐
│     Telegram Bot    │
│      (Python)       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   workflow_executor │
│   (n8n proxy only)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│        n8n          │
│ Workflow Orchestrator│
│  + Prediction Engine│
│   (Python scripts)  │
└──────────┬──────────┘
           │
           ▼
     storage/*.json
           │
           ▼
┌─────────────────────┐
│   migration_worker  │
│    (CDC a PostgreSQL)│
└──────────┬──────────┘
           │
           ▼
      PostgreSQL
           │
           ▼
      FastAPI (BFF)
           │
           ▼
       Vue Dashboard
```

---

# Principios Arquitectónicos

## 1. n8n es el cerebro del sistema

Toda la orquestación ocurre en n8n.

Responsabilidades:

* Scraping
* Recolección de datos
* Normalización
* Ejecución de modelos
* Validación
* Notificaciones
* Integración con Telegram

n8n es la única capa autorizada para coordinar procesos.

---

## 2. FastAPI es Read-Only (público)

FastAPI no:

* Ejecuta predicciones
* Ejecuta scraping
* Modifica archivos
* Entrena modelos

FastAPI únicamente:

* Lee desde PostgreSQL
* Expone APIs REST
* Agrega métricas
* Alimenta el dashboard

FastAPI sí expone endpoints internos (`/api/v1/internal/*`) protegidos con API key para que n8n y el `migration_worker` puedan escribir en PostgreSQL.

---

## 3. Prediction Engine dentro de n8n

La lógica predictiva está implementada como scripts Python montados dentro del contenedor n8n y orquestados por workflows de n8n.

Responsabilidades:

* Inferencia por deporte (fútbol y tenis)
* Scoring con modelos Elo, Poisson, XGBoost-like, CatBoost-like
* Ensemble de modelos
* Generación de predicciones que se persisten en PostgreSQL

OpenAI recibe el output del ensemble y enriquece el `naturalLanguageReasoning` de cada predicción con un análisis de experto en apuestas en español. El motor puede evolucionar independientemente siempre que mantenga el mismo contrato JSON.

## 4. PostgreSQL es la fuente de verdad

Toda la información histórica y en vivo se almacena en PostgreSQL:

* Deportes, ligas, competidores (equipos/jugadores)
* Partidos (programados, en vivo, finalizados)
* Predicciones y sus resultados de validación
* Estadísticas rolling, historial Elo, feature store
* Jobs de ingesta de datos históricos

El `migration_worker` actúa como CDC: detecta archivos JSON nuevos en `storage/`, los migra a PostgreSQL y los elimina después de un tiempo configurable para no llenar el disco.

---

## 4. Frontend desacoplado

Vue.js nunca accede directamente a:

* APIs deportivas
* OpenAI
* Modelos ML

Todo acceso ocurre mediante FastAPI.

---

# Arquitectura de Datos

```text
Data Sources (RapidAPI, CSV históricos)
     │
     ▼
┌─────────────────────────────┐
│   n8n Collection Pipeline   │
└─────────────┬───────────────┘
              │
              ▼
       storage/matches/*.json
              │
              ▼
┌─────────────────────────────┐
│     migration_worker        │
│   (CDC filesystem → DB)     │
└─────────────┬───────────────┘
              │
              ▼
         PostgreSQL
              │
     ┌────────┴────────┐
     ▼                 ▼
Prediction Engine   Validation Pipeline
(n8n + Python)      (n8n + RapidAPI)
     │                 │
     ▼                 ▼
storage/predictions  storage/results
     │                 │
     └────────┬────────┘
              │
              ▼
       PostgreSQL
              │
              ▼
         FastAPI
              │
              ▼
          Dashboard
```

---

# Stack Tecnológico

## Automatización

* n8n
* Webhooks
* Cron Jobs

## Backend

* Python 3.12
* FastAPI
* Pydantic
* SQLAlchemy 2.0
* Alembic
* PostgreSQL

## Frontend

* Vue 3
* Vite
* TailwindCSS
* Pinia

## Machine Learning

* Scikit-Learn
* XGBoost
* CatBoost
* Elo Rating
* Poisson Models

## Infraestructura

* Docker
* Docker Compose
* Nginx
* PostgreSQL 16

---

# Estructura del Proyecto

```text
brainbets/

├── docker-compose.yml

├── backend/
│   ├── alembic/               # Migraciones de PostgreSQL
│   │   ├── versions/
│   │   ├── env.py
│   │   └── init.sql
│   ├── alembic.ini
│   ├── src/
│   │   ├── domain/            # SQLAlchemy ORM models
│   │   ├── infrastructure/    # Database, repositories, migration_worker
│   │   ├── application/       # DataService
│   │   └── presentation/      # FastAPI routers + schemas
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile

├── frontend/
│   ├── src/
│   ├── nginx.conf
│   └── Dockerfile

├── services/
│   ├── file_writer/           # Deprecated (mantenido por compatibilidad)
│   ├── workflow_executor/
│   ├── telegram_bot/
│   └── migration_worker/      # CDC a PostgreSQL (dentro de backend/)
│
├── n8n/
│   ├── Dockerfile
│   ├── prediction_engine/     # Python scripts executed inside n8n
│   │   ├── football.py
│   │   ├── tennis.py
│   │   ├── common.py
│   │   └── predict.py
│   └── workflows/
│       ├── data_collection_db.json
│       ├── prediction_pipeline_db.json
│       ├── validation_db.json
│       └── telegram_bot.json
│
├── schemas/
│
├── storage/                   # Archivos temporales antes de CDC
│   ├── matches/
│   ├── predictions/
│   ├── results/
│   └── audit/
│
├── scripts/                   # Utilidades de administración (no usadas por flujos activos)
│
└── docs/
```

---

# Setup / Instalación

## Requisitos

* Docker Desktop o Docker Engine + Docker Compose
* Git
* ~4 GB de RAM disponibles

## Iniciar la plataforma

```bash
# Clonar o ubicarse en el proyecto
cd brainbets

# Levantar todos los servicios
docker-compose up -d --build

# Verificar que todos los contenedores estén saludables
docker-compose ps
```

## Activar workflows de n8n (después del primer arranque)

Los workflows se importan automáticamente desde `n8n/workflows/`, pero n8n requiere activarlos manualmente para registrar los webhooks:

```bash
# Activar todos los workflows via CLI
docker exec brainbets-n8n n8n update:workflow --all --active=true

# Reiniciar n8n para que los webhooks queden registrados
docker restart brainbets-n8n
```

O alternativamente, abrir http://localhost:5678 e activar cada workflow con el toggle superior derecho.

## Verificar salud

```bash
# Backend
curl http://localhost:8000/health

# Workflow executor
curl http://localhost:5001/health

# n8n
open http://localhost:5678
```

## Ejecutar pipeline completo

```bash
# Via workflow executor
curl -X POST http://localhost:5001/execute/pipeline

# Via Telegram Bot
# Enviar /pipeline a @coriousreybey_bot
```

## Migraciones de base de datos

Las migraciones de Alembic se ejecutan automáticamente al iniciar el backend.

Para ejecutarlas manualmente:

```bash
docker exec brainbets-backend alembic upgrade head
```

Para crear una nueva migración después de cambiar modelos:

```bash
cd backend
alembic revision --autogenerate -m "descripcion de cambios"
```

## Variables de entorno importantes

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `DATABASE_URL` | URL de PostgreSQL | `postgresql://brainbets:brainbets123@postgres:5432/brainbets` |
| `INTERNAL_API_KEY` | API key para endpoints internos | (sin default; definir en `.env`) |
| `WORKER_DELETE_AFTER_MIGRATE` | Borrar archivos después de migrar | `true` |
| `WORKER_MIN_FILE_AGE_SECONDS` | Edad mínima para borrar archivos | `300` |
| `WORKER_POLL_INTERVAL` | Intervalo de polling del CDC | `10` |

---

# Football Prediction Engine

## Objetivo

Generar predicciones para:

* Match Winner
* Double Chance
* Over/Under
* BTTS
* Asian Handicap
* Correct Score

---

## Modelo Elo

Variables:

```text
home_elo
away_elo
elo_difference
home_advantage
```

Salida:

```text
home_win_probability
away_win_probability
draw_probability
```

---

## Modelo Poisson

Variables:

```text
goals_scored
goals_conceded
expected_goals
expected_goals_against
```

Salida:

```text
expected_goals_home
expected_goals_away
score_distribution
```

Mercados:

* Correct Score
* Over/Under
* BTTS

---

## Modelo XGBoost

Features:

```text
elo_difference
xG
xGA
shots
corners
form
injuries
rest_days
market_odds
```

Predicciones:

```text
winner
btts
over_under
asian_handicap
```

---

## Ensemble Final Fútbol

```text
40% XGBoost
35% Poisson
25% Elo
```

Implementado en `n8n/prediction_engine/football.py` y ejecutado dentro del workflow `prediction_pipeline_db` de n8n.

---

# Tennis Prediction Engine

## Objetivo

Generar predicciones para:

* Ganador
* Ganador primer set
* Número de sets
* Total de juegos
* Handicap de juegos
* Correct Score
* Tie Break

---

## Elo General

Variables:

```text
player_elo
ranking
recent_form
```

---

## Surface Elo

Variables:

```text
clay_elo
hard_elo
grass_elo
```

---

## XGBoost

Variables:

```text
ranking
elo
surface_elo
h2h
recent_form
aces
double_faults
break_points_saved
return_points_won
fatigue
```

---

## CatBoost

Variables categóricas:

```text
surface
country
tournament
indoor_outdoor
```

---

## Ensemble Final Tenis

```text
35% Surface Elo
25% Elo
25% XGBoost
15% CatBoost
```

Implementado en `n8n/prediction_engine/tennis.py` y ejecutado dentro del workflow `prediction_pipeline_db` de n8n.

---

# Workflows n8n

## 1. Data Collection

Responsabilidades:

* Obtener partidos
* Obtener estadísticas
* Obtener rankings
* Obtener cuotas
* Normalizar datos

Output:

```text
storage/matches/*.json
```

---

## 2. Prediction Pipeline

Responsabilidades:

* Leer matches
* Ejecutar Prediction Engine (scripts Python dentro de n8n)
* Generar predicciones con ensemble de modelos
* Enviar resultados a OpenAI para enriquecer el reasoning
* Persistir resultados

Output:

```text
storage/predictions/*.json
```

Modelos por deporte:

* **Fútbol**: 40% XGBoost-like, 35% Poisson, 25% Elo
* **Tenis**: 35% Surface Elo, 25% Elo, 25% XGBoost-like, 15% CatBoost-like

---

## 3. Validation Pipeline

Responsabilidades:

* Obtener resultados finales
* Comparar contra predicciones
* Calcular accuracy
* Generar métricas

Output:

```text
storage/results/*.json
```

---

# Telegram Bot

## Regla Arquitectónica Obligatoria

El bot NO puede consumir directamente:

* APIs deportivas
* Prediction Engine
* FastAPI
* OpenAI

Toda interacción debe realizarse mediante n8n.

---

## Flujo Obligatorio

```text
Telegram User
      │
      ▼
Telegram Bot
      │
      ▼
workflow_executor (n8n proxy)
      │
      ▼
n8n Webhook
      │
      ▼
Workflow
      │
      ▼
Respuesta Telegram
```

---

## Comandos Iniciales

```text
/picks
/football
/tennis
/match
/player
/stats
/help
```

---

# OpenAI

OpenAI NO genera predicciones.

OpenAI únicamente puede utilizarse para:

* Explicar predicciones
* Generar análisis narrativos
* Crear resúmenes
* Responder preguntas del usuario
* Generar insights

La probabilidad final siempre debe provenir del Prediction Engine.

---

# APIs REST

## Matches

```http
GET /api/v1/matches/latest
```

```http
GET /api/v1/matches/history
```

---

## Predictions

```http
GET /api/v1/predictions/latest
```

```http
GET /api/v1/predictions/history
```

---

## Results

```http
GET /api/v1/results/latest
```

---

## Analytics

```http
GET /api/v1/analytics/accuracy
```

```http
GET /api/v1/analytics/dashboard
```

---

# Roadmap

## Fase 1 (Completada)

* Recolección de datos en vivo (RapidAPI)
* Dashboard con Vue.js
* Predicciones básicas (Elo, Poisson, XGBoost-like, CatBoost-like)
* Telegram Bot
* Migración a PostgreSQL con CDC desde archivos

## Fase 2 (En progreso)

* Entrenamiento automático con datos históricos (2010+)
* Feature store y modelos reentrenables
* Métricas avanzadas y backtesting
* Alertas inteligentes

## Fase 3 (Planeada)

* MCP Server
* Multi-deporte (NBA, MLB, eSports)
* Reinforcement Learning
* Predicciones en vivo con actualización continua
* Bankroll management y Kelly Criterion

---

# Objetivo Futuro

Exponer el Prediction Engine mediante un MCP Server para que cualquier agente de IA pueda consultar directamente:

```text
predict_football()
predict_tennis()
get_best_picks()
get_player_analysis()
```

sin depender del frontend o del dashboard.
