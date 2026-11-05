# Tarea para DeepSeek: "Asesor de apuestas" (analizar una apuesta con estadísticas)

> Documento de implementación autocontenido. Léelo entero antes de escribir código.
> Lee también `AGENTS.md` (raíz del repo): tiene las reglas del proyecto y los "gotchas" que ya costaron caro.
> Todo texto que vea el usuario va **en español**.

---

## 1. Qué hay que construir

Una sección nueva de la app donde el usuario **envía una apuesta** (una selección o una combinada, con la cuota que le ofrece su casa y el monto) y el sistema le responde, **con datos**:

1. **Si la apuesta es buena o no**: compara la cuota del usuario con la probabilidad real estimada (la de la casa sin su margen) y con cómo les fue en el pasado a apuestas iguales.
2. **Qué debería hacer para sacarle dinero**: acciones concretas (cuota mínima que debe exigir, mejor casa disponible, separar una combinada, bajar el monto, cambiar a una selección con mejor precio, etc.).
3. **Por qué**: cada número viene con una frase corta que lo explica. El objetivo es **educar al apostador para que pierda menos**, no venderle apuestas.

Es una herramienta de **solo lectura**: no registra nada. Registrar sigue siendo `POST /api/v1/my-bets`.

### Principios (no negociables)

- **Nunca responder "no se puede".** Si falta un dato, se da el mejor estimado disponible, se dice de dónde sale y cuál es su límite en una línea. Decisión del usuario (AGENTS.md, 2026-10-13): *"decime con datos cuál es la mejor apuesta y yo veré qué hago con esa información"*.
- **Solo estadística, sin sermones.** No se discute el tamaño de la apuesta ni se moraliza. Se da el número (stake de Kelly, probabilidad de perder) y el usuario decide. Un riesgo concreto y nuevo se menciona **una vez**.
- **La casa sin margen es la referencia.** En este proyecto se demostró varias veces que la cuota de cierre ATP ya incluye todo lo que nuestros modelos saben (ver AGENTS.md: "el modelo de puntos NO le gana a la cuota", 2026-10-13; "edge inflado", 2026-10-10). Por eso:
  - la probabilidad "real" de una selección = **probabilidad de la casa sin margen**;
  - el modelo propio (modelo de saque y resto, motor) se muestra solo como **segunda opinión** y **nunca** se usa para declarar valor;
  - un edge mayor a 20% se marca **sospechoso** (casi siempre es una cuota vieja o mal cargada).
- **Lo más probable no es lo más rentable.** Hay que decirlo cuando el usuario apueste favoritos a cuota baja.
- **Mostrar siempre la muestra (`n`) y el intervalo de confianza** de cualquier dato histórico. Con `n < 30` se dice "muestra chica".

---

## 2. Reglas del repo que debes respetar

(Resumen de `AGENTS.md`; si hay contradicción, manda `AGENTS.md`.)

| Regla | Detalle |
|---|---|
| Imports absolutos | `from src.application...`, `from src.domain...` |
| Endpoints con `def`, no `async def` | SQLAlchemy es síncrono; un `async def` lento congela el backend entero (gotcha #47). |
| Lógica pura con tests | Las funciones que calculan van en un servicio puro (sin DB) testeado en `backend/tests/application/`. La parte con DB solo arma los datos. |
| JSON en columnas | Nunca mutar un dict JSONB en sitio; reasignar un dict nuevo (gotcha #43). Este feature no escribe, pero no lo rompas en otro lado. |
| Fechas | Hora Bogotá: `src/timezone.py` (`to_bogota`, `today_bogota`). Nunca formatear `match_date` sin `to_bogota()`. |
| Secretos | Nunca en el código ni en los commits. Viven en `.env`. |
| Payload del motor | No agregar campos al esquema `TennisMatch` que solo sean de pantalla sin ponerlos en `DISPLAY_ONLY` del nodo `Build Batch` (gotcha del 2026-10-26, `spawn E2BIG`). Este feature **no necesita** tocar `TennisMatch`. |
| Alcance | Solo tenis ATP de cuadro principal. Fútbol está congelado (`FOOTBALL_ENABLED=false`): si llega un partido de fútbol, responder 422 con "Fútbol está pausado". |
| Documentar | Agregar una entrada en `AGENTS.md` → "Recent updates (fecha)" en español, con lo que se hizo, los números y los límites. |
| Commits | Mensaje en inglés, termina con la línea de coautoría que use el equipo. No commitear `storage/models/*`. Revisar el diff por secretos antes de commitear. |

### Cómo se corre y se prueba

```bash
# Reconstruir y desplegar
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

## 3. Piezas que YA existen y debes reutilizar (no reimplementar)

| Archivo | Qué te da |
|---|---|
| `backend/src/application/likely_picks_service.py` | `likely_picks(m, history, band_of, books)`: para un partido por jugar, las selecciones con su `kind`, `selector`, probabilidad sin margen, cuota de la casa, mejor cuota (`bestOdds`, `bestBook`, `bestNeedsCheck`), `source` (`casa` / `modelo`) y `group` (`main` / `games`). También `board_outcomes(setBetting)`, `_pair`, `_line_pair`, `_estimated_price`. **Es la fuente principal de la probabilidad justa por tipo de apuesta.** Ojo: filtra a probabilidad ≥ 50% (`MIN_PROB`) y recorta a 4 + 4; para el asesor necesitas la probabilidad de **cualquier** lado (ver §5.2). |
| `backend/src/application/best_bets_service.py` | `band_of(fair)` → tramo `"70-80"`; `band_history(db)` → `{mercado: {tramo: {n, winRate, expected, yield, yieldLow, yieldHigh}}}` (cómo les fue a los favoritos de ese tramo, cacheado 1 h); `band_summary(outcomes)`; `price_view(...)` y `level_for(edge, price_gap)` con `GOOD_EDGE = 0.02` y `STALE_GAP = 0.06`. |
| `backend/src/application/user_bets_service.py` | `KINDS`, `valid_selector(kind, selector)` (catálogo oficial de tipos de apuesta y su forma), `settle_leg` (cómo se gana cada tipo), `summarize(bets)` (historial del propio usuario: acierto real vs esperado, rendimiento). |
| `backend/src/application/games_model_service.py` | `point_markets(pa, pb, best_of)` y la vista `gamesModel` (`tiebreak`, `decider`, `expectedGames`, `markets.setScores`). Solo segunda opinión. |
| `backend/src/application/services.py` → `DataService` | `get_matches_by_date(...)` devuelve cada partido de tenis ya armado (`TennisMatch`: `oddsMarkets`, `gamesModel`, `likelyPicks`, `underdogCase`, `playerNews`, `h2hDetail`, `streakPlayer1/2`, estado, hora). **Usa esto para obtener el partido** en vez de reconstruirlo con consultas propias. La línea de `likely_picks` en `_match_to_tennis_schema` muestra cómo pasarle `oddsLines` (`matches.extra_data['odds_lines']`). |
| `backend/src/application/bankroll_service.py` | Lógica de Kelly fraccionado y el z-test de rendimiento (`_flat_yield_stats`). Reutiliza la fórmula; no dupliques constantes. |
| `backend/src/application/underdog_service.py` | `underdog_case` (argumentos a favor del no favorito, cada uno con la evidencia de que **no** le ganó a la cuota). |
| `frontend/src/stores/api.js` | Instancia de axios con caché de GET. Los POST no se cachean. |
| `frontend/src/stores/combo.js` + `components/ComboPanel.vue` | La combinada que arma el usuario desde "Lo más probable" (selecciones con `kind`, `selector`, `odds`). El asesor debe poder recibirla tal cual. |

### Tipos de apuesta soportados (`kind` + `selector`)

Son exactamente los de `user_bets_service.valid_selector`. No inventes otros sin agregarlos ahí y en `settle_leg`, con tests.

| `kind` | `selector` | Significado |
|---|---|---|
| `partido` | `{"side": "p1"\|"p2"}` | Gana el partido |
| `set1` | `{"side": ...}` | Gana el 1er set |
| `unSet` | `{"side": ...}` | Gana al menos un set (= hándicap +1.5 sets) |
| `sinCeder` | `{"side": ...}` | Gana sin ceder set (2-0 / 3-0) |
| `sets` | `{"sets": "corridos"\|"largo"}` | Se decide en sets corridos / va al set decisivo |
| `gamesSet` | `{"set": 1..5\|"ultimo", "line": X.5, "pick": "mas"\|"menos"}` | Games de un set |
| `gamesMatch` | `{"line": X.5, "pick": ...}` | Games del partido |
| `tiebreak` | `{"pick": "si"\|"no"}` | Al menos un tiebreak en el partido |

`p1` / `p2` = `player1` / `player2` del partido tal como lo devuelve la API.

---

## 4. Endpoints

Todos van en un router nuevo `backend/src/presentation/routers/advisor.py` (`get_router()`, registrado en `backend/main.py` con prefijo `/api/v1`, igual que `my_bets`). Son públicos y **de solo lectura**: no requieren `INTERNAL_API_KEY`.

### 4.1 `GET /api/v1/advisor/catalog`

Para que el frontend (u otro cliente) sepa qué puede enviar.

```json
{
  "kinds": [
    {"kind": "partido", "label": "Gana el partido", "selector": {"side": ["p1", "p2"]}},
    {"kind": "gamesSet", "label": "Games de un set",
     "selector": {"set": [1, 2, 3, 4, 5, "ultimo"], "line": "número terminado en .5", "pick": ["mas", "menos"]}}
  ],
  "limits": {"maxLegs": 10, "minOdds": 1.01}
}
```

### 4.2 `GET /api/v1/advisor/matches?q=&date=`

Busca partidos de tenis **por jugar** para elegir a cuál pertenece la apuesta. `q` = parte del nombre de cualquiera de los jugadores (sin acentos, sin mayúsculas); `date` opcional (Bogotá, por defecto hoy y mañana). Devuelve `[{matchId, player1, player2, tournament, eventDate, eventTime, status}]`, máximo 20. Reutiliza `DataService.get_matches_by_date`.

### 4.3 `POST /api/v1/advisor/analyze` (el principal)

**Entrada** (mismo formato que `POST /api/v1/my-bets`, para que una combinada armada en la calculadora se pueda analizar sin transformarla):

```json
{
  "amount": 1000000,
  "bankroll": 10000000,
  "legs": [
    {"matchId": "TENNIS-12176565", "kind": "set1", "selector": {"side": "p1"}, "odds": 1.62, "book": "bet365"},
    {"matchId": "TENNIS-12176937", "kind": "gamesSet", "selector": {"set": 1, "line": 9.5, "pick": "mas"}, "odds": 1.70}
  ]
}
```

- `amount` obligatorio, > 0.
- `bankroll` opcional: si viene, el stake sugerido sale también en pesos.
- `odds` obligatorio, > 1: **es la cuota que el usuario tiene en su casa**, no la nuestra.
- `book` opcional, solo informativo.
- De 1 a 10 selecciones. Dos selecciones del mismo partido **sí se aceptan** (a diferencia de `my-bets`), pero llevan la advertencia de correlación (§5.5).
- Partido no encontrado, `kind`/`selector` inválido o partido de fútbol → **422** con `detail` en español, igual que `BetError` en `my_bets.py`.
- Partido ya empezado o terminado: **no** es error. Se analiza igual (sirve para aprender de apuestas pasadas) con `matchState: "empezado" | "terminado"` y, si terminó, el resultado de la selección (`settle_leg`).

**Salida** (forma exacta; los nombres importan para el frontend):

```json
{
  "verdict": {
    "level": "cara",
    "title": "Pagas más de lo que vale",
    "summary": "La casa le da 58% a esta combinada; tu cuota 2.75 implica 36%... (una o dos frases)"
  },
  "bet": {
    "type": "combinada",
    "odds": 2.754,
    "fairProbability": 0.3480,
    "impliedProbability": 0.3631,
    "breakEvenOdds": 2.874,
    "edge": -0.0416,
    "expectedProfit": -41600,
    "lossProbability": 0.652,
    "kelly": {"fraction": 0.0, "quarter": 0.0, "stake": 0},
    "streak": {"tenInARow": 0.00003}
  },
  "legs": [
    {
      "label": "Ruud C. gana el 1er set",
      "matchId": "TENNIS-12176565",
      "kind": "set1",
      "selector": {"side": "p1"},
      "odds": 1.62,
      "fairProbability": 0.5871,
      "probabilitySource": "casa",
      "referenceOdds": 1.62,
      "referenceBook": "bet365",
      "bestOdds": 1.70,
      "bestBook": "Pncl",
      "bestNeedsCheck": false,
      "margin": 0.061,
      "breakEvenOdds": 1.703,
      "edge": -0.0489,
      "edgeAtBest": -0.0019,
      "suspicious": false,
      "history": {"band": "50-60", "n": 412, "winRate": 0.56, "expected": 0.55, "yield": -0.021,
                  "yieldLow": -0.07, "yieldHigh": 0.03, "priced": true},
      "secondOpinion": {"source": "modelo de saque y resto", "probability": 0.55, "trust": 1.0,
                        "note": "No le ha ganado a la cuota en 2.272 partidos: solo referencia."},
      "context": ["Ruud viene de 3 victorias en el torneo (la racha ya está en el precio)."],
      "matchState": "por_jugar",
      "result": null
    }
  ],
  "actions": [
    {"key": "pedir_cuota", "priority": 1,
     "text": "No la tomes por debajo de 1.71: a 1.62 pierdes 4,9 centavos por cada peso a la larga."},
    {"key": "mejor_casa", "priority": 2, "text": "Pinnacle la paga a 1.70: con esa cuota casi no pierdes (−0,2%)."},
    {"key": "separar_combinada", "priority": 3,
     "text": "En combinada el margen de la casa se multiplica (2 selecciones: ~12%). Sueltas pierdes la mitad."}
  ],
  "lessons": [
    {"key": "margen", "title": "La casa cobra un margen",
     "text": "Si en un partido 50-50 te pagan 1.87 por cada lado, la casa se queda con ~7%..."}
  ],
  "meta": {"generatedAt": "...", "historyWindow": "nov-2025 → hoy", "warnings": []}
}
```

---

## 5. Cálculos (servicio puro `backend/src/application/advisor_service.py`)

Separa en dos capas:

- `advisor_service.py`: **funciones puras** (reciben dicts, devuelven dicts). Aquí van todas las fórmulas y reglas.
- `advisor_data.py` (o una función `load_context(db, legs)` dentro del router): usa la DB para traer el partido (`DataService`), `band_history`, `odds_lines`, y llama al servicio puro.

### 5.1 Probabilidades básicas por selección

```
impliedProbability = 1 / odds                      # lo que "dice" la cuota del usuario
fairProbability    = probabilidad de la casa sin margen (ver 5.2)
breakEvenOdds      = 1 / fairProbability           # cuota mínima para no perder a la larga
edge               = fairProbability * odds - 1    # ganancia esperada por peso apostado
edgeAtBest         = fairProbability * bestOdds - 1
margin             = (1/p1 + 1/p2) - 1             # margen de la casa en ese mercado (de los dos lados de la referencia)
```

`edge` en pesos: `expectedProfit = amount * edge`.

### 5.2 De dónde sale `fairProbability` (en este orden)

1. **Casa, mercado directo** (`probabilitySource: "casa"`): quitar el margen con los dos lados del mismo mercado y la misma casa.
   - `partido` → `oddsMarkets.matchWinner`; `set1` → `oddsMarkets.set1Winner`; `unSet` → `oddsMarkets.oneSet` (sí/no).
   - `sinCeder`, `sets` → tablero de marcador exacto `oddsMarkets.setBetting` con `board_outcomes`.
   - `gamesSet` (solo `set: 1`) → `odds_lines.set1TotalGames.lines[line]`; `gamesMatch` → `odds_lines.totalGames.lines[line]` (`_line_pair`).
   - **Importante**: `likely_picks` descarta lo que está por debajo de 50% y recorta la lista. Para el asesor, escribe una función pura `fair_probability(kind, selector, odds_markets, odds_lines)` reutilizando `_pair`, `_line_pair` y `board_outcomes` (no copies su lógica: impórtalas). Debe devolver la probabilidad de **cualquier** lado (también un no favorito de 25%).
2. **Casa, otra línea del mismo mercado** (`"casa_interpolada"`): si el usuario apuesta una línea de games que la casa no publica (por ejemplo, 9.5 cuando solo hay 8.5 y 10.5), interpolar linealmente entre las dos líneas vecinas y avisarlo en `warnings`. Si solo hay una línea de un lado, no extrapolar: pasar al punto 3.
3. **Modelo** (`"modelo"`): `gamesModel` (modelo de saque y resto): `markets.matchP1`, `markets.set1P1`, `markets.setScores`, `tiebreak`. Para `gamesSet` con `set` distinto de 1 o `"ultimo"`, no hay fuente: ver punto 4. Con `trust < 0.2` no se usa.
4. **Sin fuente** (`"sin_datos"`): `fairProbability = null`, `edge = null`, veredicto `sin_datos`. Aun así se devuelven `impliedProbability`, `breakEvenOdds` del lado del usuario, el historial que exista y las lecciones. Nunca un 500, nunca "no se puede".

Cuando la fuente es `modelo`, el veredicto **nunca** puede ser `valor`: como máximo `justa`, con la frase "el modelo no ha demostrado ganarle a la cuota".

### 5.3 Historial ("cómo les fue a apuestas como esta")

- `band_history(db)` cubre `Match Winner`, `Set 1 Winner`, `One Set`, `Straight Sets`, `Total Sets` (ver `HISTORY_KEY` en `likely_picks_service`), solo **favoritos** (tramos de 50% en adelante, `BANDS`).
- `history.priced = true` solo para los mercados de `PRICED_HISTORY` (`partido`, `set1`, `sinCeder`): ahí el rendimiento se midió a cuota real. En los demás, mostrar solo `n`, `winRate` y `expected` (quitar `yield*`), como ya hace `likely_picks`.
- Para el no favorito (< 50%) y para games no hay historial todavía: `history = null` y una línea en `warnings`. **Opcional (fase 2)**: extender `band_history` a tramos por debajo de 50% y a las líneas de games, con la misma consulta y la misma regla de precio previo al partido (lee la docstring de `band_history`).
- Si `n < 30`: agregar "muestra chica" al texto.

### 5.4 Combinada

```
odds_combo  = producto de las cuotas del usuario
fair_combo  = producto de fairProbability      # asume independencia: solo vale entre partidos distintos
edge_combo  = fair_combo * odds_combo - 1
margin_combo ≈ producto(1 + margin_i) - 1       # mostrar cómo se multiplica el margen
```

Si alguna selección tiene `fairProbability = null`, la combinada también queda `null` (`sin_datos`), pero se muestran las demás selecciones.

### 5.5 Correlación (dos selecciones del mismo partido)

No multiplicar. `fair_combo = null`, veredicto `sin_datos` para la combinada, y la acción `misma_partida`: "Estas dos selecciones dependen una de la otra (si Zverev gana el 1er set es más probable que gane el partido); multiplicar sus probabilidades da un número falso. La casa suele ofrecer este cruce como 'apuesta creada' con su propia cuota."

### 5.6 Tamaño de la apuesta (Kelly)

```
b = odds - 1
kelly = max(0, (b * p - (1 - p)) / b)     # p = fairProbability de la apuesta (o de la combinada)
quarter = kelly / 4                        # lo que usa el proyecto (¼ Kelly)
stake = quarter * bankroll                 # si llegó bankroll
```

Si `edge <= 0`, Kelly es 0. Se muestra el número **sin opinar**: "Con edge ≤ 0, el criterio de Kelly sugiere 0%". No escribas frases sobre "apostar responsablemente" ni repitas el riesgo en cada respuesta (decisión del usuario: estadística, no sermón).

`lossProbability = 1 - fair` y `streak.tenInARow = fair ** 10` (lo que ya muestra `ComboPanel`).

### 5.7 Veredicto (`verdict.level`)

Función pura `verdict_for(edge, source, suspicious, n_history)`:

| level | condición | title |
|---|---|---|
| `sospechosa` | `edge > 0.20` | "Revisa la cuota: parece un error" |
| `valor` | `edge >= 0.02`, fuente `casa` y no sospechosa | "Tiene valor" |
| `justa` | `-0.02 < edge < 0.02` (o fuente `modelo` con `edge >= 0.02`) | "Precio justo: a la larga, cerca de cero" |
| `cara` | `edge <= -0.02` | "Pagas más de lo que vale" |
| `sin_datos` | `fairProbability` nula | "Sin referencia de la casa" |

Usa `GOOD_EDGE` y `STALE_GAP` de `best_bets_service` y `SUSPICIOUS_EDGE` de `bankroll_service` (importa las constantes, no copies los números). Si `bestNeedsCheck` es verdadero, agregar a `warnings`: "La mejor cuota supera en más de 6% a la referencia: puede estar vieja; confírmala".

`verdict.summary`: plantilla en español con los números reales, por ejemplo:

> "La casa (sin su margen) le da **58,7%**. Tu cuota 1.62 equivale a 61,7%: pagas 3 puntos de más. A la larga pierdes **$48.900 por cada $1.000.000** apostado. Para no perder necesitas **1.71 o más**."

### 5.8 Acciones ("qué hacer para sacarle dinero")

Función pura `actions_for(analysis) -> List[action]`, cada una con `key`, `priority` (1 = más importante) y `text`. Reglas, en este orden; incluye solo las que apliquen:

1. `pedir_cuota`: si `edge < 0` → "No la tomes por debajo de {breakEvenOdds:.2f}".
2. `mejor_casa`: si `bestOdds > odds` → "{bestBook} la paga a {bestOdds}: con esa cuota tu resultado esperado pasa de {edge} a {edgeAtBest}". Si `bestNeedsCheck`, agregar "confírmala, puede estar vieja".
3. `separar_combinada`: si es combinada y `edge_combo < min(edge_i)` → explicar cómo se multiplica el margen y comparar el resultado esperado de jugarlas sueltas con el de la combinada.
4. `quitar_seleccion`: en una combinada, la selección con peor `edge` si es < −3% → "Sin «{label}» la combinada pasa de {edge_combo} a {edge_sin_ella}".
5. `alternativa_mismo_partido`: entre las selecciones del mismo partido (usar `likely_picks` del partido, con probabilidad ≥ 50%), la de mejor `edge` a su cuota de referencia, si supera en ≥ 2 puntos a la del usuario → "En este partido «{label}» a {odds} tiene mejor precio ({edge})".
6. `monto_kelly`: si llegó `bankroll` → "¼ Kelly: {quarter:.1%} de tu caja (${stake})". Solo el número.
7. `lo_probable_no_es_rentable`: si `fair >= 0.75` y `edge < 0` → "Sale {fair:.0%} de las veces, pero a esta cuota pierdes a la larga: lo más probable no es lo más rentable".
8. `historial`: si hay `history` con `n >= 30` → "Apuestas como esta (tramo {band}%) salieron {winRate} de {n} (se esperaba {expected}); a la cuota de la casa rindieron {yield} por apuesta (rango {yieldLow} a {yieldHigh})".
9. `misma_partida` (§5.5).
10. `sin_referencia`: si la fuente es `modelo` o `sin_datos` → qué mercado buscar en la casa para tener referencia (por ejemplo, "busca la línea de games del 1er set para comparar").

Nunca más de 6 acciones; ordenar por `priority`.

### 5.9 Lecciones (`lessons`)

Diccionario estático `LESSONS` en `advisor_service.py` (texto corto, 2–3 frases, con un ejemplo numérico). Incluir solo las relevantes a la apuesta analizada:

| key | cuándo | idea |
|---|---|---|
| `margen` | siempre | Qué es el margen y cómo se calcula con los dos lados. |
| `cuota_justa` | siempre | Cuota justa = 1 / probabilidad; break-even. |
| `combinadas` | combinada | El margen se multiplica; 3 selecciones al 7% ≈ 22%. |
| `favoritos` | `fair >= 0.75` | Lo más probable no es lo más rentable; una pérdida borra varias ganancias (a 1.20 hacen falta 5 aciertos para recuperar 1 fallo). |
| `muestra` | hay historial | Por qué 10 aciertos seguidos no prueban nada (usar el `n` y el intervalo de confianza). |
| `clv` | siempre | Ganarle a la cuota de cierre es la mejor señal de que se apuesta bien (AGENTS.md, CLV). |
| `correlacion` | mismo partido | Por qué no se multiplican. |
| `kelly` | llegó `bankroll` | Qué es ¼ Kelly y por qué no apostar todo. |

---

## 6. Frontend

- Ruta nueva `/asesor`, vista `frontend/src/views/Advisor.vue`, enlace **"Asesor"** en la barra de navegación de escritorio y móvil (`App.vue`, mismo patrón que "Mis apuestas" / "Caja").
- Store `frontend/src/stores/advisor.js` (Pinia): `fetchCatalog`, `searchMatches(q)`, `analyze(payload)`. Los POST no pasan por la caché de `api.js`.
- Formulario:
  1. buscar partido (input con debounce de 400 ms → `/advisor/matches`);
  2. elegir tipo de apuesta (del catálogo) y el lado o la línea, con los nombres reales de los jugadores;
  3. cuota que le ofrece su casa, monto y caja (opcional);
  4. botón "+ otra selección" (combinada) y botón **"Analizar"**.
- Desde "Mi combinada" (`ComboPanel.vue`): botón **"Analizar esta apuesta"** que abre `/asesor` con las selecciones ya cargadas (pasarlas por el store, no por la URL).
- Resultado:
  - tarjeta del veredicto con borde izquierdo de color (como la Caja): verde `valor`, amarillo `justa`, rojo `cara`, ámbar `sospechosa`, gris `sin_datos`;
  - fila de números: probabilidad real, la que implica tu cuota, cuota mínima, resultado esperado en pesos, probabilidad de perder, ¼ Kelly;
  - lista "Qué hacer" (las `actions`);
  - tabla por selección, plegable en móvil;
  - "Para aprender" con las `lessons` en `<details>`.
- Accesibilidad: todo `select`/`input` con `aria-label`, contraste AA (usar las clases de color ya usadas en `Caja.vue`), sin scroll horizontal a 390 px.
- Captura de verificación: `frontend/audit/shot-advisor.mjs` (copiar el patrón de `shot-mybets.mjs`), que analice una apuesta real de un partido por jugar y guarde captura en escritorio y móvil.

---

## 7. Tests obligatorios (`backend/tests/application/test_advisor_service.py`)

Puros, sin DB (como `test_likely_picks_service.py`). Como mínimo:

1. `fair_probability` quita el margen: `matchWinner {p1: 1.20, p2: 5.0}` → p1 ≈ 0.806.
2. Funciona para el no favorito (< 50%), a diferencia de `likely_picks`.
3. `gamesSet` set 1 lee `set1TotalGames`; una línea faltante entre dos publicadas se interpola y deja `warning`; la del set 3 da `sin_datos` sin lanzar excepción.
4. Cuota del usuario por debajo de la cuota justa → `cara`, `pedir_cuota` primera, `breakEvenOdds` correcto.
5. Edge 25% → `sospechosa`.
6. Fuente `modelo` con edge 5% → `justa`, nunca `valor`.
7. Combinada de 2 partidos: `fair_combo` = producto; margen combinado > margen de cada una; aparece `separar_combinada`.
8. Dos selecciones del mismo partido → `fair_combo` nulo y acción `misma_partida`.
9. Kelly: edge ≤ 0 → 0; con `bankroll` el stake en pesos es `quarter * bankroll`.
10. `actions_for` nunca devuelve más de 6 y respeta el orden de prioridad.
11. Un selector inválido levanta el error que el router convierte en 422 (reutiliza `valid_selector`).

Y un test de humo del endpoint fuera de la suite (script manual): `curl -X POST http://localhost:8000/api/v1/advisor/analyze` con un partido real `SCHEDULED`.

---

## 8. Criterios de aceptación

- [ ] `POST /api/v1/advisor/analyze` responde en menos de 1,5 s con un partido real (cuidado: `band_history` tarda la primera vez; está cacheado 1 h).
- [ ] Ningún caso devuelve 500: datos faltantes → `sin_datos` con explicación.
- [ ] Ninguna frase usa "no se puede" ni sermonea.
- [ ] El modelo propio nunca produce el veredicto `valor`.
- [ ] Todos los números del texto coinciden con los del JSON (se arman desde el mismo dict).
- [ ] La vista funciona en 390 px de ancho sin scroll horizontal y sin violaciones de axe (`npm run audit`).
- [ ] Todos los tests pasan (los 220 de hoy más los nuevos).
- [ ] Entrada en `AGENTS.md` → "Recent updates" con lo construido, un ejemplo real con sus números y los límites.

## 9. Fuera de alcance (no lo hagas)

- No registrar ni modificar apuestas (eso es `my-bets`).
- No llamar a APIs externas en el análisis (api-tennis, OpenAI): todo sale de la base. OpenAI además está sin créditos.
- No cambiar el motor de predicción, los workflows de n8n ni los pesos del ensemble.
- No usar el modelo propio para declarar valor.
- No agregar fútbol.
- No crear migraciones: el feature no guarda nada.

## 10. Límites conocidos para escribir en la respuesta y en `AGENTS.md`

- La probabilidad "real" es la de la casa sin margen: el asesor no promete ganarle al mercado; enseña a no pagar de más.
- El historial por tramo existe solo para favoritos (≥ 50%) y para mercados de ganador/sets; games y no favoritos no tienen historial todavía.
- Las líneas de games se recolectan desde octubre de 2026: hay pocas muestras.
- Para la casa de referencia se usa la que guardó el collect (`book` de cada mercado); la cuota del usuario puede venir de otra casa con otro margen.
