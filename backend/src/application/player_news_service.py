"""Recent news on both players of each upcoming tennis match, read for what
could matter on the day: injury, illness, fatigue, personal matters, a home
or family connection to the city, a coaching change, motivation.

Source: Google News RSS (free, no key), searched by surname in English and
Spanish over the last few days. The headlines are noisy (live-score pages,
betting markets, other people with the same surname), so GPT-4o-mini keeps
only those about this player that say something beyond the result, and
writes one line on each. It may only use the headlines it is given.

Information only: nothing here has been tested against the price, and most
news that is public is already in it. Stored in matches.extra_data['player_news'].
"""
import json
import logging
import os
import re
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.domain.models import Match, Sport
from src.timezone import to_bogota

OPENAI_ENDPOINT = os.environ.get("OPENAI_ENDPOINT", "https://api.openai.com/v1/chat/completions")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

LOOKBACK_DAYS = 5
MAX_HEADLINES = 25            # per player, newest first, sent to the model
HOURS_AHEAD = 18              # matches starting within this window get news
STALE_MINUTES = 180           # refresh after this long...
STALE_MINUTES_NEAR = 60       # ...or this long once the match is less than NEAR_HOURS away
NEAR_HOURS = 4

# Pages that only carry a score, a live feed, odds or a pick: never news.
NOISE = re.compile(
    r"prediction market|en directo|en vivo|live score|livescore|marcador|resultados? y|h2h|head to head|"
    r"betting|odds|pron[oó]stico|prediction|picks?\b|apuestas?|cuotas?|highlights|resumen|"
    r"\svs?\.?\s.*·|match atp|watchalong|how to watch|live stream|d[oó]nde ver|fecha, hora|hot shot",
    re.I,
)
NOISE_SOURCES = {"robinhood", "sofascore", "flashscore", "sportytrader", "oddschecker", "unisba media", "bet365"}

FACTORS = {"lesion", "fisico", "personal", "local", "entrenador", "motivacion", "calendario", "otro"}
IMPACTS = {"positivo", "negativo", "incierto"}


def surname(name: str) -> str:
    """'Fritz T.' -> 'Fritz'; 'J-L. Struff' -> 'Struff'; 'Carreno-Busta P.' -> 'Carreno-Busta'."""
    words = [w for w in (name or "").split() if "." not in w and len(w.replace("-", "")) > 2]
    return " ".join(words) or (name or "").strip()


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return re.sub(r"[\s\-]+", " ", "".join(c for c in s if not unicodedata.combining(c)).lower()).strip()


def mentions(title: str, name: str) -> bool:
    """'Carreño Busta wins' mentions 'Carreno-Busta P.'"""
    return _fold(surname(name)) in _fold(title)


def is_noise(title: str, source: str) -> bool:
    src = (source or "").strip().lower()
    src = re.sub(r"^www\.|\.(com|es|net|org|co)$", "", src)
    return bool(NOISE.search(title or "")) or any(src.startswith(n) for n in NOISE_SOURCES)


def _rss(query: str, hl: str, gl: str) -> List[Dict[str, Any]]:
    ceid = f"{gl}:{hl.split('-')[0]}" if hl == "en-US" else f"{gl}:{hl}"
    url = (
        "https://news.google.com/rss/search?q=" + urllib.parse.quote(query)
        + f"&hl={hl}&gl={gl}&ceid={ceid}"
    )
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    if resp.status_code != 200:
        logging.warning("[NEWS] rss %s -> %s", query, resp.status_code)
        return []
    out = []
    for it in ET.fromstring(resp.content).findall("./channel/item"):
        try:
            published = parsedate_to_datetime(it.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        title = (it.findtext("title") or "").strip()
        source = (it.findtext("source") or "").strip()
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        out.append({"title": title, "source": source, "link": it.findtext("link"), "published": published})
    return out


def headlines(name: str) -> List[Dict[str, Any]]:
    """Recent, de-duplicated, non-noise headlines mentioning the player's surname."""
    s = surname(name)
    items: List[Dict[str, Any]] = []
    for query, hl, gl in ((f'"{s}" tennis when:{LOOKBACK_DAYS}d', "en-US", "US"),
                          (f'"{s}" tenis when:{LOOKBACK_DAYS}d', "es-419", "CO")):
        try:
            items += _rss(query, hl, gl)
        except Exception as exc:  # network / XML: news is optional, never fail the caller
            logging.warning("[NEWS] rss failed for %s: %s", query, exc)
    seen, kept = set(), []
    for it in sorted(items, key=lambda x: x["published"], reverse=True):
        key = re.sub(r"\W+", " ", it["title"].lower()).strip()
        if key in seen or is_noise(it["title"], it["source"]) or not mentions(it["title"], name):
            continue
        seen.add(key)
        kept.append(it)
    return kept[:MAX_HEADLINES]


SYSTEM_PROMPT = (
    "Eres analista de tenis para apuestas. Recibes titulares recientes que mencionan el apellido de cada "
    "jugador de un partido ATP. Algunos son de otra persona con el mismo apellido, o solo dicen un resultado. "
    "Quédate SOLO con los que son sobre ESE jugador y dicen algo que pueda influir en este partido más allá del "
    "marcador: lesión, enfermedad, molestias, cansancio o calendario cargado, asuntos personales o familiares, "
    "conexión con la ciudad o el país del torneo (juega en casa, familia allí, público a favor), cambio de "
    "entrenador, motivación (defiende puntos, carrera por las Finals, retiro), declaraciones sobre su estado. "
    "Usa EXCLUSIVAMENTE lo que dicen los titulares: no agregues datos que sepas por tu cuenta ni supongas. "
    "Si nada aporta, devuelve la lista vacía. Responde en español, en JSON."
)


def _ask_model(match_ctx: Dict[str, Any], p1: List[Dict[str, Any]], p2: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        logging.warning("[NEWS] OPENAI_API_KEY missing in the backend environment")
        return None

    def listing(items):
        return [{"i": i, "fecha": it["published"].strftime("%Y-%m-%d"), "fuente": it["source"], "titular": it["title"]}
                for i, it in enumerate(items)]

    user = {
        "partido": match_ctx,
        "jugador1": {"nombre": match_ctx["player1"], "titulares": listing(p1)},
        "jugador2": {"nombre": match_ctx["player2"], "titulares": listing(p2)},
        "responde_con_exactamente_estas_claves": {
            "jugador1": "LISTA de objetos {i: índice del titular, factor: " + "|".join(sorted(FACTORS))
                        + ", impacto: positivo|negativo|incierto (para ese jugador en este partido), "
                        "nota: una frase con qué dice y por qué podría importar}; lista vacía si nada aporta",
            "jugador2": "igual que jugador1",
            "resumen": "una o dos frases sobre lo extra-cancha del partido, o cadena vacía si no hay nada",
        },
    }
    resp = requests.post(
        OPENAI_ENDPOINT,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": OPENAI_MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
        },
        timeout=60,
    )
    if resp.status_code != 200:
        logging.warning("[NEWS] openai -> %s %s", resp.status_code, resp.text[:200])
        return None
    try:
        return json.loads(resp.json()["choices"][0]["message"]["content"])
    except (KeyError, ValueError, TypeError):
        return None


def clean_items(raw: Any, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only model rows that point at a real headline; attach its source, date and link."""
    if isinstance(raw, dict):  # the model sometimes echoes the input shape: {nombre, titulares: [...]}
        raw = raw.get("titulares") or raw.get("items") or []
    out, used = [], set()
    for row in raw if isinstance(raw, list) else []:
        try:
            i = int(row.get("i"))
        except (TypeError, ValueError, AttributeError):
            continue
        if not 0 <= i < len(items) or i in used:
            continue
        used.add(i)
        it = items[i]
        factor = str(row.get("factor") or "otro").lower()
        impact = str(row.get("impacto") or "incierto").lower()
        out.append({
            "headline": it["title"],
            "source": it["source"],
            "link": it["link"],
            "date": to_bogota(it["published"]).strftime("%Y-%m-%d"),
            "factor": factor if factor in FACTORS else "otro",
            "impact": impact if impact in IMPACTS else "incierto",
            "note": str(row.get("nota") or "").strip()[:300],
        })
    return out


def news_for_match(match: Match) -> Optional[Dict[str, Any]]:
    p1 = next((c for c in match.competitors if c.side == "player1"), None)
    p2 = next((c for c in match.competitors if c.side == "player2"), None)
    if not p1 or not p2:
        return None
    n1, n2 = p1.competitor.name, p2.competitor.name
    h1, h2 = headlines(n1), headlines(n2)
    ctx = {
        "player1": n1,
        "player2": n2,
        "torneo": match.league.name if match.league else None,
        "superficie": (match.extra_data or {}).get("surface"),
        "fecha": to_bogota(match.match_date).strftime("%Y-%m-%d %H:%M") if match.match_date else None,
    }
    answer = _ask_model(ctx, h1, h2) if (h1 or h2) else {}
    if answer is None:
        return None
    return {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "headlinesRead": {"player1": len(h1), "player2": len(h2)},
        "player1": clean_items(answer.get("jugador1"), h1),
        "player2": clean_items(answer.get("jugador2"), h2),
        "summary": str(answer.get("resumen") or "").strip()[:500],
    }


def is_stale(news: Optional[Dict[str, Any]], starts_at: datetime, now: datetime) -> bool:
    if not news or not news.get("fetchedAt"):
        return True
    try:
        fetched = datetime.fromisoformat(news["fetchedAt"])
    except ValueError:
        return True
    limit = STALE_MINUTES_NEAR if starts_at - now <= timedelta(hours=NEAR_HOURS) else STALE_MINUTES
    return now - fetched >= timedelta(minutes=limit)


def refresh_news(db: Session, hours_ahead: int = HOURS_AHEAD, match_id: Optional[str] = None,
                 force: bool = False) -> Dict[str, Any]:
    """Fetch news for upcoming tennis matches whose stored news is missing or stale."""
    now = datetime.now(timezone.utc)
    q = db.query(Match).join(Sport, Sport.id == Match.sport_id).filter(Sport.code == "tennis")
    if match_id:
        q = q.filter(Match.external_id == match_id)
    else:
        q = q.filter(Match.status == "SCHEDULED", Match.match_date > now,
                     Match.match_date <= now + timedelta(hours=hours_ahead))
    done = skipped = failed = 0
    for match in q.all():
        if not force and not is_stale((match.extra_data or {}).get("player_news"), match.match_date, now):
            skipped += 1
            continue
        try:
            news = news_for_match(match)
        except Exception as exc:
            logging.warning("[NEWS] %s failed: %s", match.external_id, exc)
            news = None
        if news is None:
            failed += 1
            continue
        match.extra_data = {**(match.extra_data or {}), "player_news": news}  # new dict: gotcha #43
        db.commit()
        done += 1
    return {"refreshed": done, "fresh": skipped, "failed": failed}
