# Tarea para DeepSeek: sección "En vivo" (partidos de tenis que se están jugando)

> Documento de implementación autocontenido. Léelo entero antes de escribir código.
> Lee también `AGENTS.md` (raíz del repo): tiene las reglas del proyecto y los "gotchas" que ya costaron caro.
> Todo texto que vea el usuario va **en español**. Los nombres en el código y los mensajes de commit, en inglés.

---

## 1. Qué hay que construir

Una página nueva **`/en-vivo`** que muestra los partidos **ATP de cuadro principal individual** que se están jugando **ahora**. Se actualiza sola cada 30 segundos. Para cada partido se ve:

1. **El marcador al momento**: sets, games por set, el punto del game actual (15-30, 40-A…) y quién saca.
2. **Cómo van las apuestas del usuario** en ese partido (las registradas en "Mis apuestas"): ganada ya, perdida ya o pendiente, y **de qué depende**.
3. **Lo que se esperaba antes del partido frente a cómo va**: probabilidad de la casa sin margen y del modelo de saque y resto antes del inicio.
4. **Datos de contexto medidos**, por ejemplo: si el no favorito gana el 1er set, al mejor de 3 se llevó el partido el 67.1% de las veces (detalle en §6).
5. **Estadísticas del partido en curso** (aces, dobles faltas, % de primer saque, quiebres), en un detalle plegable.

Es una sección de **solo lectura**: no escribe nada en la base de datos.

### Lo que NO se puede, y la sección debe decirlo una sola vez

- **No hay cuotas en vivo.** `get_live_odds` de api-tennis responde con error en el plan actual (verificado el 2026-11-06). La sección **no** recomienda apuestas en vivo ni calcula edge en vivo. Muestra el marcador y datos medidos. Ningún texto debe sugerir "ahora hay valor en X".
- **Solo ATP.** El feed en vivo trae también ITF, Challenger y WTA: se filtran (ver §4.1).

### Principios (no negociables)

- **Solo estadística, sin sermones.** El usuario tiene su sistema de apuestas y no se discute. Se dan números, con su muestra (`n`), y él decide.
- **Nunca "no se puede".** Si un dato falta (partido que no está en nuestra base, sin cuota previa), se muestra lo que sí hay y se dice qué falta en una línea.
- **Un dato histórico va siempre con su muestra y su límite.** Si viene de un estudio de 2010–2020 con cuotas de Pinnacle, se dice.

---

## 2. Reglas del repo que debes respetar

(Resumen de `AGENTS.md`; si hay contradicción, manda `AGENTS.md`.)

| Regla | Detalle |
|---|---|
| Imports absolutos | `from src.application...`, `from src.domain...` |
| Endpoints con `def`, no `async def` | SQLAlchemy es síncrono y la llamada a la API externa bloquea; un `async def` lento congela el backend entero (gotcha #47). |
| Lógica pura con tests | Parseo del feed, estado de apuestas e "insights" van en un servicio **puro** (sin DB ni red), testeado en `backend/tests/application/`. La parte con red/DB solo arma los datos. |
| Fechas | Hora Bogotá con `src/timezone.py` (`to_bogota`, `today_bogota`). Nunca formatear `match_date` sin `to_bogota()`. |
| Secretos | La clave de api-tennis está en la variable de entorno `TENNIS_API_KEY` del backend (ya configurada en `docker-compose.yml`). **Nunca** la escribas en código, logs, respuestas de la API ni commits. Si logueas una URL, redacta `APIkey=***`. |
| Payload del motor | **No** agregues campos a `TennisMatch` (`presentation/schemas.py`). Este feature tiene su propio esquema de respuesta. |
| Fútbol | Congelado. Esta sección es solo tenis. |
| Documentar | Entrada en `AGENTS.md` → "Recent updates (fecha)" en español: qué se hizo, números, límites. |
| Commits | Mensaje en inglés. No commitear `storage/models/*`. Revisar el diff por secretos antes de commitear (`git diff --cached \| grep -iE "apikey=|token|secret"`). |

### Cómo se corre y se prueba

```bash
# Reconstruir y desplegar (el backend corre desde la imagen, no desde un bind mount)
docker compose build backend frontend -q
docker compose up -d --no-deps backend frontend

# Tests (Git Bash en Windows; en Linux/macOS quitar MSYS_NO_PATHCONV y usar $(pwd))
MSYS_NO_PATHCONV=1 docker run --rm --network none \
  -v "$(pwd -W)/backend/tests:/app/tests:ro" \
  -e DATABASE_URL=postgresql://x:x@localhost/x -e INTERNAL_API_KEY=x \
  brainbets-backend python -m pytest tests/application -q
```

Hoy pasan 220 tests. Al terminar deben pasar todos más los tuyos.

---

## 3. Piezas que YA existen y debes reutilizar

| Archivo | Qué te da |
|---|---|
| `backend/src/application/user_bets_service.py` | `settle_live_leg(kind, selector, live_home, live_away)`: decide una selección **a mitad de partido** solo cuando ningún set posterior puede cambiarla (al menos un set, ganar sin ceder set, número de sets, 1er set). `settle_leg(...)` para partidos terminados, `games_in_set(selector, set_rows)`, `KINDS` y `valid_selector`. **No reimplementes estas reglas**: llámalas. Los modelos ORM son `UserBet` / `UserBetLeg` (`kind`, `selector`, `odds`, `status`, `match_id`). |
| `backend/src/application/services.py` → `DataService` | `get_matches_by_date(...)` arma cada partido de tenis (`TennisMatch`) con `oddsMarkets`, `gamesModel`, `likelyPicks`, `underdogCase`, `h2hDetail`, `streakPlayer1/2`. `_extract_event_id(external_id)` convierte `TENNIS-12178070` → `12178070`. |
| `backend/src/application/likely_picks_service.py` | `_pair(...)` / `board_outcomes(setBetting)`: probabilidad sin margen desde las cuotas guardadas (`odds_markets.matchWinner`, `set1Winner`, `setBetting`). Úsalo para "lo que daba la casa antes del inicio". |
| `backend/src/application/clv_service.py` | `_fetch_odds_by_key`: ejemplo de cómo el backend llama a api-tennis con `requests`, `TENNIS_API_KEY`, timeout y logging sin filtrar la clave. Copia ese patrón. |
| `frontend/src/stores/api.js` | Axios con caché de GET de 2 minutos. **Para esta sección hay que saltarla**: pasar `{ noCache: true }` en la config del `get` (el adaptador ya lo soporta). Si no, el polling de 30 s devolvería la misma respuesta durante 2 min. |
| `frontend/src/components/MatchCard.vue` | Estilo de tarjeta, badge "🔴 EN VIVO", colores. Reutiliza el estilo; no hace falta reutilizar el componente. |
| `frontend/src/App.vue` + `frontend/src/router/index.js` | Navbar (escritorio y móvil) y rutas. |

### Datos de partido en nuestra base

- Un partido de tenis tiene `matches.external_id = "TENNIS-<event_key>"`. El `event_key` es el **mismo** que devuelve `get_livescore`. Así se cruza; **nunca** por nombre de jugador.
- `matches.extra_data['odds_markets']` = cuotas previas al partido (`matchWinner: {p1, p2}`, `set1Winner: {p1, p2}`, `setBetting: {"2:0": ..}`, `oneSet`). `player1` en nuestra base = `event_first_player` en la API.
- **Gotcha conocido**: la actualización horaria de tenis escribe el marcador pero deja el partido en `SCHEDULED` hasta que termina. **No uses `matches.status` para decidir si está en vivo**: lo que está en vivo lo dice el feed (`event_live == "1"`).

---

## 4. Backend

### 4.1 Fuente: `get_livescore` de api-tennis

```
GET https://api.api-tennis.com/tennis/?method=get_livescore&APIkey=<TENNIS_API_KEY>&event_type_key=265
```

- Probar primero con `event_type_key=265` (ATP singles). Si devuelve vacío cuando sí hay ATP en juego, quitar el parámetro. **En ambos casos** filtrar después en Python: `event_type_type == "Atp Singles"` y `event_qualification != "True"`.
- Respuesta: `{"success": 1, "result": [evento, ...]}`. Ante error, la API devuelve HTTP 200 con `{"error": "1", "result": [{"cod": 1006, "msg": "..."}]}` (pasó el 2-nov: "Please make the payment for your account!"). Trátalo como fallo y regístralo con `logger.warning` (sin la clave).

Forma real de un evento (capturado el 2026-11-06, era ITF):

```json
{
  "event_key": 12177776,
  "event_live": "1",
  "event_status": "Set 1",
  "event_game_result": "0 - 0",
  "event_serve": "Second Player",
  "event_final_result": "0 - 0",
  "event_winner": null,
  "event_first_player": "A. Blinkova",
  "event_second_player": "Y. Kabbaj",
  "first_player_key": 1779,
  "second_player_key": 2001,
  "tournament_name": "...",
  "tournament_round": "...",
  "event_type_type": "Challenger Women Singles",
  "event_qualification": "False",
  "scores": [{"score_first": "2", "score_second": "0", "score_set": "1"}],
  "pointbypoint": [{"set_number": "Set 1", "number_game": "3", "player_served": "Second Player",
                    "serve_winner": null, "serve_lost": null, "score": null, "points": [...]}],
  "statistics": [{"player_key": 1779, "stat_period": "match", "stat_type": "Service",
                  "stat_name": "Aces", "stat_value": "0", "stat_won": null, "stat_total": null}]
}
```

Cómo leerlo:

- `event_final_result` = **sets ganados** hasta ahora (`"1 - 0"`).
- `scores` = games de cada set, **incluido el set en curso** (el último elemento puede estar incompleto). Un set está terminado si alguno llegó a 6 con 2 de diferencia, o a 7 (7-5, 7-6). Un set de 7-6 tuvo tiebreak.
- `event_game_result` = **puntos del game actual** (`"15 - 30"`, `"40 - A"`; en tiebreak son números `"5 - 4"`).
- `event_serve` = `"First Player"` / `"Second Player"` / null.
- `event_status` = `"Set 1"`, `"Set 2"`, … mientras se juega; `"Finished"`, `"Retired"` al terminar.
- `statistics`: filtrar `stat_period == "match"`. Nombres que interesan (comparar **en minúsculas**, cambian de mayúsculas según la época): `aces`, `double faults`, `1st serve percentage` (o derivarlo), `break points converted` (usa `stat_won`/`stat_total`), `service games won`, `total points won`. `player_key` se mapea a p1/p2 con `first_player_key`.
- `pointbypoint`: solo para el detalle. Puede venir vacío.

### 4.2 Servicio puro: `backend/src/application/live_service.py`

Sin DB ni red. Funciones (nombres sugeridos, firmas obligatorias en espíritu):

```python
ATP_TYPE = "Atp Singles"

def is_atp_main_draw(ev: dict) -> bool: ...

def parse_live_event(ev: dict) -> dict:
    """Evento crudo → forma normalizada:
    {
      "eventKey": "12177776",
      "matchId": "TENNIS-12177776",
      "player1": "A. Blinkova", "player2": "Y. Kabbaj",
      "tournament": "...", "round": "...",
      "status": "Set 2",
      "sets": {"p1": 1, "p2": 0},            # de event_final_result
      "games": [{"set": 1, "p1": 6, "p2": 4, "done": True, "tiebreak": False},
                {"set": 2, "p1": 2, "p2": 1, "done": False, "tiebreak": False}],
      "point": {"p1": "15", "p2": "30"},      # de event_game_result; None si no hay
      "serving": "p1" | "p2" | None,
      "finished": False,                      # True si Finished/Retired
      "stats": {"p1": {...}, "p2": {...}}     # solo stat_period == match
    }
    Nunca lanza: un campo raro → None en ese campo."""

def set_done(p1: int, p2: int) -> bool: ...   # 6-x con 2 de diferencia, 7-5, 7-6

def leg_live_view(kind: str, selector: dict, live: dict) -> dict:
    """Estado de una selección registrada con el marcador vivo:
    {"status": "WON" | "LOST" | "PENDING", "why": "texto corto en español"}
    - Primero intenta settle_live_leg(kind, selector, live["sets"]["p1"], live["sets"]["p2"]).
    - gamesSet del 1er set (o de un set numerado) ya terminado: decídelo con games_in_set
      sobre las filas de sets terminados (los sets en curso NO cuentan).
    - gamesSet / gamesMatch "más de X" ya superado con games jugados: WON aunque el set siga.
      "menos de X" ya superado: LOST. (Los games solo suben.)
    - tiebreak "si": WON en cuanto un set terminado sea 7-6 (o el set en curso llegue a 6-6).
    - Lo demás: PENDING con el porqué ("necesita ganar el partido", "decide el 3er set", ...)."""

def bet_live_view(legs: list[dict], live_by_match: dict) -> dict:
    """Combinada: perdida si una selección está LOST; ganada si todas WON/VOID;
    si no, pendiente con cuántas faltan. Selecciones de partidos que no están en vivo
    conservan su estado guardado."""

def insights(live: dict, pre: dict | None) -> list[dict]:
    """Datos medidos que aplican AHORA. Cada uno:
    {"key": "...", "text": "...", "evidence": "fuente + n + límite"}.
    Ver §6 para la lista y los números exactos. Máximo 3."""
```

Reglas importantes de `leg_live_view`:

- **No inventes reglas nuevas** para `partido`, `unSet`, `sinCeder`, `sets`, `set1`: eso ya lo decide `settle_live_leg`. Tu código solo agrega los tipos de games y el texto "why".
- Un selector usa `side: "p1" | "p2"`; `p1` = `player1` en nuestra base = `event_first_player`.
- Esto es **solo vista**: no cambia `user_bet_legs.status`. La liquidación guardada sigue siendo la horaria (`settle_pending`). Si la vista dice WON y la base dice PENDING, se muestra "ya ganada (se registra al validar)".

### 4.3 Cliente con caché: `backend/src/application/live_feed.py`

```python
CACHE_SECONDS = 30

def fetch_livescore() -> tuple[list[dict], str, bool]:
    """(eventos crudos, fetchedAt ISO, stale).
    - Caché en memoria del proceso por CACHE_SECONDS, protegida con threading.Lock
      para que N pestañas abiertas no hagan N llamadas.
    - Si la API falla (red, HTTP != 200, error 1006), devuelve el último resultado bueno
      con stale=True. Si nunca hubo uno, ([], ahora, True).
    - timeout=15. Sin TENNIS_API_KEY: ([], ahora, True) y un warning."""
```

No uses la tabla `external_api_cache` ni el proxy interno: el proxy guarda la última respuesta por URL sin vencimiento corto y aquí el dato vence en segundos.

### 4.4 Router: `backend/src/presentation/routers/live.py`

Registrar en `backend/main.py` con `prefix="/api/v1"`, igual que `my_bets`.

#### `GET /api/v1/live/tennis`

```json
{
  "fetchedAt": "2026-11-06T14:03:10-05:00",
  "stale": false,
  "note": "Sin cuotas en vivo: el proveedor no las ofrece en este plan.",
  "matches": [
    {
      "matchId": "TENNIS-12178070",
      "inDb": true,
      "player1": "A. Zverev", "player2": "A. de Minaur",
      "tournament": "ATP Paris", "round": "...",
      "status": "Set 2", "finished": false,
      "sets": {"p1": 1, "p2": 0},
      "games": [{"set": 1, "p1": 6, "p2": 4, "done": true, "tiebreak": false},
                {"set": 2, "p1": 2, "p2": 1, "done": false, "tiebreak": false}],
      "point": {"p1": "15", "p2": "30"},
      "serving": "p2",
      "bestOf": 3,
      "pre": {
        "favorite": "p1",
        "market": {"matchP1": 0.68, "set1P1": 0.64},
        "model": {"matchP1": 0.61, "set1P1": 0.58},
        "odds": {"matchWinner": {"p1": 1.42, "p2": 2.95}}
      },
      "myBets": [
        {"betId": "…", "amount": 1000000, "odds": 1.47,
         "legs": [{"label": "Zverev gana el 1er set", "kind": "set1",
                   "live": {"status": "WON", "why": "Ganó el 1er set 6-4"},
                   "saved": "PENDING"}],
         "live": {"status": "WON", "why": "Todas las selecciones ya salieron"}}
      ],
      "insights": [
        {"key": "underdog_set1", "text": "…", "evidence": "…"}
      ]
    }
  ]
}
```

- `inDb: false` cuando el `event_key` no está en `matches` (partido que nuestro collect no vio). Se muestra igual, con `pre: null`, `myBets: []` y una línea "Sin datos previos: el partido no se recolectó".
- `bestOf`: 5 si el torneo es Grand Slam, si no 3. Reutiliza `best_of_sets(...)` de `n8n/prediction_engine/tennis.py` copiando **solo** su lista de nombres a una constante del backend, o reutiliza el `gamesModel.bestOf` del partido cuando está en la base.
- `pre.market`: probabilidad **sin margen** desde `odds_markets` guardado (usa `_pair`). `pre.model`: de `gamesModel.markets` (`matchP1`, `set1P1`) si existe. Cualquiera puede ser `null`.
- `myBets`: apuestas con `status = PENDING` que tengan al menos una selección en un partido en vivo, más las que se liquidaron hoy en un partido que sigue en el feed. Una consulta por request (`joinedload` de `legs` y `legs.match`), no N+1.
- Partidos en vivo de nuestra base: **una** consulta `Match.external_id.in_(ids)`; no llames a `get_matches_by_date` completo (es pesado, arma noticias, H2H, etc.). Lee directo `extra_data['odds_markets']`, `extra_data['odds_lines']` y, si hace falta `gamesModel`, solo para esos partidos.
- Orden: primero partidos donde el usuario tiene apuestas, luego por torneo y hora.
- Tiempo objetivo: < 1 s con caché caliente.

#### `GET /api/v1/live/tennis/{matchId}`

Lo mismo para un partido, más `stats` completas y `pointByPoint` del set en curso (últimos 3 games). 404 con `{"detail": "El partido no está en juego"}` si no está en el feed.

---

## 5. Frontend

### 5.1 Archivos

- `frontend/src/stores/live.js` (Pinia): `fetchLive()` con `api.get('/live/tennis', { noCache: true })`, estado `matches`, `fetchedAt`, `stale`, `error`, `loading`.
- `frontend/src/views/Live.vue` en la ruta `/en-vivo`.
- Navbar en `App.vue`: enlace "🔴 En vivo" (escritorio y menú móvil), con un contador de partidos en juego si es > 0 (puede leerlo del store cuando la vista ya cargó; no hagas polling global desde la navbar).

### 5.2 Comportamiento

- Polling cada **30 s** con `setInterval` que se limpia en `onUnmounted`. Pausar cuando la pestaña no está visible (`document.visibilityState`) y refrescar al volver.
- Botón "Actualizar" que fuerza un fetch.
- Línea arriba: "Actualizado hace N s". Si `stale`, aviso ámbar: "No se pudo actualizar; mostrando el último marcador (de hace N s)".
- Sin partidos: "No hay partidos ATP en juego ahora." y debajo los próximos 3 partidos de hoy desde `/matches/by-date` (hora Bogotá).
- La nota "Sin cuotas en vivo…" se muestra **una vez** en gris pequeño, no en cada tarjeta.

### 5.3 Tarjeta de partido

```
ATP Paris · R16                                         🔴 Set 2
● A. Zverev        6   2   15        ← ● = saca
  A. de Minaur     4   1   30
Antes del partido: casa 68% Zverev · modelo 61%
───────────────────────────────────────────────
Tus apuestas
  ✅ Zverev gana el 1er set (1.47 · $1.000.000) — ya ganada
  ⏳ Más de 9.5 games en el último set — decide el set 3
───────────────────────────────────────────────
📊 De Minaur ganó el 1er set siendo no favorito: al mejor de 3, … (tooltip con la evidencia)
[Ver estadísticas ▾]
```

- Columnas de games por set alineadas (tabla), set en curso resaltado, punto actual en otra columna.
- Estados: ✅ ganada (verde), ❌ perdida (rojo), ⏳ pendiente (gris) con el `why`.
- Partido terminado que sigue en el feed: badge "Final" y el resultado; desaparece cuando el feed lo quite.
- Accesible: contraste AA, `aria-label` en el botón, `aria-live="polite"` en el marcador **solo** en la vista de detalle (en la lista sería ruido para lectores de pantalla).
- Móvil (390 px): sin scroll horizontal de la página.

---

## 6. Insights (datos medidos que se pueden mostrar)

Solo estos, con estos números. **No inventes otros** sin un estudio que los respalde. Cada uno con `evidence` en el tooltip.

| key | Cuándo aplica | Texto (ejemplo) | evidence |
|---|---|---|---|
| `underdog_set1` | Al mejor de 3, terminó el set 1 y lo ganó el no favorito (`pre.favorite` según `pre.market.matchP1`) | "X (no favorito) ganó el 1er set. Al mejor de 3, el no favorito que gana el 1er set se lleva el partido el 67.1% de las veces; con sets independientes se esperaría 62.6%." | "Estudio con 26.935 partidos ATP 2010–2020 y cuota de cierre de Pinnacle (AGENTS.md, 2026-10-15). No dice si la cuota en vivo paga eso: no tenemos cuotas en vivo." |
| `underdog_set1_bo5` | Igual pero al mejor de 5 | "Al mejor de 5 el no favorito gana el 1er set menos de lo esperado (30.1% vs 34.3%) y el partido también (21.7% vs 24.4% de la cuota)." | Mismo estudio. |
| `underdog_set1_tb` | Set 1 en 6-6 y el no favorito está en el tiebreak | "El 1er set del no favorito va a tiebreak el 19.7% de las veces y lo gana el 43.6%." | Mismo estudio. |
| `favorite_down` | El favorito perdió el set 1 | Usar `underdog_set1` desde el lado del favorito: "El favorito perdió el 1er set; históricamente gana el partido el 32.9% de esas veces." (= 100 − 67.1) | Mismo estudio. |
| `pre_vs_now` | Siempre que haya `pre.market` | "Antes del partido la casa le daba 68% a Zverev." | "Probabilidad sin margen de la cuota recolectada antes del inicio." |

Máximo 3 por partido. Si no aplica ninguno, no se muestra nada (no rellenar).

---

## 7. Tests obligatorios (`backend/tests/application/test_live_service.py`)

1. `parse_live_event` con el evento de ejemplo de §4.1: sets 0-0, un set en curso 2-0 no terminado, `serving == "p2"`, sin excepción.
2. `parse_live_event` con campos faltantes o basura (`scores: None`, `event_game_result: ""`): no lanza y deja `None`.
3. `set_done`: 6-4 sí, 6-5 no, 7-5 sí, 7-6 sí (tiebreak), 5-3 no.
4. `is_atp_main_draw`: "Atp Singles" sí; "Itf Men Singles", "Challenger Men Singles", "Atp Doubles" no; qualy no.
5. `leg_live_view` `set1` con un set terminado a favor: WON (vía `settle_live_leg`).
6. `leg_live_view` `unSet` con el jugador sin sets: PENDING con un `why` no vacío.
7. `leg_live_view` `gamesSet` set 1 "más de 9.5" con el set 1 terminado 7-6: WON; terminado 6-2: LOST.
8. `leg_live_view` `gamesSet` set 1 "más de 9.5" con el set en curso 5-5 (10 games): WON aunque no terminó.
9. `leg_live_view` `gamesSet` "ultimo": PENDING mientras el partido no termine.
10. `leg_live_view` `tiebreak` "si" con un set terminado 7-6: WON; "no" con el mismo marcador: LOST.
11. `bet_live_view` combinada con una selección LOST → LOST; todas WON → WON; una PENDING → PENDING con "falta 1".
12. `insights`: no favorito gana el set 1 al mejor de 3 → incluye `underdog_set1` con 67.1; sin `pre` → no incluye nada que dependa del favorito.
13. `fetch_livescore` (con `requests.get` simulado por `monkeypatch`): respuesta de error 1006 → devuelve el último bueno con `stale=True`; dos llamadas dentro de 30 s → una sola petición.

---

## 8. Criterios de aceptación

- [ ] `/en-vivo` lista los partidos ATP en juego, se refresca solo cada 30 s y no hace más de una llamada a api-tennis cada 30 s aunque haya varias pestañas abiertas.
- [ ] Marcador correcto contra la web del torneo en al menos 2 partidos reales (sets, games, punto, saque).
- [ ] Una apuesta registrada en un partido en vivo aparece en su tarjeta con el estado correcto y el porqué.
- [ ] Si la API falla, la página no se rompe: aviso ámbar y último marcador.
- [ ] Ningún log, respuesta ni commit contiene la clave de la API.
- [ ] Sin partidos en juego, la página lo dice y muestra los próximos.
- [ ] Todos los tests pasan (220 + los nuevos).
- [ ] Entrada en `AGENTS.md` → "Recent updates" con fecha, qué se hizo, el filtro ATP, la falta de cuotas en vivo y la caché de 30 s.
- [ ] Sin scroll horizontal a 390 px; sin violaciones axe nuevas (`cd frontend && npm run audit` con la ruta `/en-vivo` agregada a `audit/run-audit.mjs`).

---

## 9. Fuera de alcance (no lo hagas)

- Cuotas en vivo, edge en vivo, recomendaciones de apuesta en vivo.
- Escribir en la base (liquidar apuestas, cambiar `matches.status`, guardar snapshots). La liquidación horaria existente no se toca.
- Cambiar workflows de n8n.
- Fútbol, WTA, Challenger, ITF, dobles.
- WebSockets o Server-Sent Events: polling de 30 s alcanza.
- Notificaciones (Telegram, push).

## 10. Límites conocidos (decirlos en la UI o en AGENTS.md, no esconderlos)

- El feed puede ir unos segundos o un game por detrás de la TV.
- Un partido que nuestro collect no vio (`inDb: false`) no tiene datos previos ni apuestas.
- Los insights de §6 vienen de un estudio 2010–2020 previo al partido; no dicen nada sobre si una cuota en vivo paga bien.
- `matches.status` sigue quedando `SCHEDULED` durante el partido (gotcha conocido); esta sección no lo corrige.
