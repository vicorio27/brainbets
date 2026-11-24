"""News of each team before a football match (injuries, suspensions, the coach, rotations, what is at stake).

Same source and idea as the tennis player news (`player_news_service`: Google News RSS, last 5 days, no key),
but WITHOUT a language model: the newest headlines are kept as they are, each tagged by keywords, so what
matters before kick-off (a key player out, a sacked coach, a rotated side) is in front of the person who bets.
Stored in `matches.extra_data['team_news']`:

    {fetchedAt, prematchAt?, home: [{headline, source, link, published, tags}], away: [...]}

Refresh rules as in tennis: matches starting within HOURS_AHEAD hours, re-read when the stored read is older than
STALE_MINUTES (STALE_MINUTES_NEAR once the match is closer than NEAR_HOURS), and one last read in the
PREMATCH_MINUTES before the start. Headlines only: what a coach says in the last minutes is not in them.
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.application import player_news_service as pn
from src.application.football_collect_service import ALIASES
from src.domain.models import Match, Sport

LOOKBACK_DAYS = pn.LOOKBACK_DAYS
HOURS_AHEAD = 30
STALE_MINUTES = 180
STALE_MINUTES_NEAR = 60
NEAR_HOURS = 4
PREMATCH_MINUTES = pn.PREMATCH_MINUTES
MAX_PER_TEAM = 8
SHOWN = 5

TAGS = {
    "lesion": re.compile(r"injur|lesi[oó]n|lesionad|\bbaja\b|\bbajas\b|out for|ruled out|sidelined|doubt|duda|molest|knock|"
                         r"hamstring|isquio|tobillo|ankle|knee|rodilla|muscular|surgery|operad|miss(es|ing)?\b|return(s|ing)? from",
                         re.I),
    "sancion": re.compile(r"suspend|sanci[oó]n|sancionad|expulsad|red card|tarjeta roja|\bban(ned)?\b|apercibid|ciclo de tarjetas|"
                          r"yellow card suspension", re.I),
    "entrenador": re.compile(r"sack|despid|destitu|\bcoach\b|manager|entrenador|t[eé]cnico|new boss|nuevo t[eé]cnico|"
                             r"resign|dimisi[oó]n|interim", re.I),
    "alineacion": re.compile(r"line-?up|alineaci[oó]n|once inicial|team news|rotaci|rotate|rest(ed|s)?\b|descanso|"
                             r"probable|starting xi|expected xi|convocatoria|squad", re.I),
    "en_juego": re.compile(r"title|t[ií]tulo|relegation|descenso|clasific|qualif|derby|cl[aá]sico|"
                           r"top[- ]?4|promotion|ascenso|survival|permanencia|must[- ]win|eliminat|eliminad", re.I),
}
PRIORITY = ("lesion", "sancion", "entrenador", "alineacion", "en_juego")

# Pages that tell you where to watch, the odds or a pick, a live score or a preview table: never news about the team.
NOISE = re.compile(
    r"odds|prediction|pron[oó]stico|picks?|how to watch|d[oó]nde (y c[oó]mo )?ver|live ?stream|streaming|en vivo|en directo|"
    r"live score|livescore|live:|marcador|horario|fecha, hora|tv channels?|cuotas|apuestas|betting|head-to-head|stats & |"
    r"pregame|qu[eé] hora se juega|c[oó]mo ver|how to watch|kick-?off time",
    re.I,
)

REVERSE_ALIASES: Dict[str, str] = {}
for _api, _ours in ALIASES.items():
    REVERSE_ALIASES.setdefault(_ours, _api)


def search_name(name: str) -> str:
    """Our stored name -> the name the press uses ('Man City' -> 'Manchester City')."""
    return REVERSE_ALIASES.get(name, name)


def aliases_of(name: str) -> List[str]:
    full = search_name(name)
    out = {name, full}
    out.add(re.sub(r"^(AFC|FC|CF|SC|RC|Real|Club|Atl[eé]tico de)\s+|\s+(FC|CF|SC|AFC)$", "", full).strip())
    return [a for a in out if len(a) >= 4]


def mentions_team(title: str, names: List[str]) -> bool:
    t = pn._fold(title)
    return any(pn._fold(n) in t for n in names)


def tag_headline(title: str) -> List[str]:
    return [k for k in PRIORITY if TAGS[k].search(title or "")]


def team_headlines(name: str) -> List[Dict[str, Any]]:
    """Recent, de-duplicated, non-noise headlines that mention the team. Injury / suspension / coach first."""
    q = search_name(name)
    names = aliases_of(name)
    hurt = "injury OR injured OR suspended OR doubtful OR \"ruled out\" OR sacked OR \"team news\" OR lineup"
    hurt_es = "lesión OR lesionado OR baja OR sancionado OR duda OR destituido OR alineación OR rotaciones"
    items: List[Dict[str, Any]] = []
    for query, hl, gl in ((f'"{q}" when:{LOOKBACK_DAYS}d', "en-US", "US"),
                          (f'"{q}" fútbol when:{LOOKBACK_DAYS}d', "es-419", "CO"),
                          (f'"{q}" ({hurt}) when:{LOOKBACK_DAYS}d', "en-US", "US"),
                          (f'"{q}" ({hurt_es}) when:{LOOKBACK_DAYS}d', "es-419", "CO")):
        try:
            items += pn._rss(query, hl, gl)
        except Exception as exc:               # news is optional: never fail the caller
            logging.warning("[FOOTBALL-NEWS] rss failed for %s: %s", query, exc)
    return select(items, names)


def select(items: List[Dict[str, Any]], names: List[str]) -> List[Dict[str, Any]]:
    kept, sigs = [], []
    for it in sorted(items, key=lambda x: x["published"], reverse=True):
        if not mentions_team(it["title"], names):
            continue
        if NOISE.search(it["title"]) or pn.is_noise(it["title"], it["source"]) and not (pn.is_injury(it["title"])):
            continue
        sig = pn.headline_signature(it["title"], names[0])
        if any(pn.same_story(sig, s) for s in sigs):
            continue
        sigs.append(sig)
        kept.append({**it, "tags": tag_headline(it["title"])})
    tagged = [k for k in kept if k["tags"]][:MAX_PER_TEAM]
    rest = [k for k in kept if k not in tagged][: max(0, MAX_PER_TEAM - len(tagged))]
    return sorted(tagged + rest, key=lambda x: x["published"], reverse=True)


def view(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What is stored and shown: the newest SHOWN headlines, but a tagged one is never pushed out by an untagged one."""
    tagged = [k for k in items if k["tags"]]
    rest = [k for k in items if not k["tags"]]
    pick = (tagged + rest)[:SHOWN]
    pick.sort(key=lambda x: x["published"], reverse=True)
    return [{"headline": k["title"], "source": k["source"], "link": k["link"], "tags": k["tags"],
             "published": k["published"].astimezone(timezone.utc).isoformat()} for k in pick]


def news_for_match(match: Match) -> Optional[Dict[str, Any]]:
    sides = {mc.side: mc.competitor.name for mc in match.competitors}
    if "home" not in sides or "away" not in sides:
        return None
    return {"fetchedAt": datetime.now(timezone.utc).isoformat(),
            "home": view(team_headlines(sides["home"])), "away": view(team_headlines(sides["away"]))}


def refresh_news(db: Session, hours_ahead: int = HOURS_AHEAD, match_id: Optional[str] = None,
                 force: bool = False, prematch: bool = False) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    q = db.query(Match).join(Sport, Sport.id == Match.sport_id).filter(Sport.code == "football", Match.external_id.like("FOOTBALL-AF-%"))
    if match_id:
        q = q.filter(Match.external_id == match_id)
    elif prematch:
        q = q.filter(Match.status == "SCHEDULED", Match.match_date > now, Match.match_date <= now + timedelta(minutes=PREMATCH_MINUTES))
    else:
        q = q.filter(Match.status == "SCHEDULED", Match.match_date > now, Match.match_date <= now + timedelta(hours=hours_ahead))
    done = skipped = failed = 0
    for match in q.all():
        old = (match.extra_data or {}).get("team_news")
        if prematch:
            if not pn.needs_prematch(old, match.match_date, now):
                skipped += 1
                continue
        elif not force and not pn.is_stale(old, match.match_date, now):
            skipped += 1
            continue
        try:
            news = news_for_match(match)
        except Exception as exc:
            logging.warning("[FOOTBALL-NEWS] %s failed: %s", match.external_id, exc)
            news = None
        if news is None:
            failed += 1
            continue
        if prematch:
            news["prematchAt"] = now.isoformat()
        elif (old or {}).get("prematchAt"):
            news["prematchAt"] = old["prematchAt"]
        match.extra_data = {**(match.extra_data or {}), "team_news": news}      # new dict (gotcha #43)
        db.commit()
        done += 1
    return {"refreshed": done, "fresh": skipped, "failed": failed}


SCHEDULER_SECONDS = 600     # the football news read runs inside the backend every 10 minutes (hourly + pre-match rules)


def _tick() -> None:
    from src.infrastructure.database import SessionLocal

    session = SessionLocal()
    try:
        a = refresh_news(session)
        b = refresh_news(session, prematch=True)
        if a["refreshed"] or b["refreshed"]:
            logging.warning("[FOOTBALL-NEWS] hourly %s, pre-match %s", a, b)
    finally:
        session.close()


def start_scheduler() -> None:
    """Background thread: one process, so no duplicate runs. Football has no n8n workflow for this on purpose."""
    import threading
    import time

    def loop() -> None:
        time.sleep(90)                      # let the app settle after a restart
        while True:
            try:
                _tick()
            except Exception as exc:
                logging.warning("[FOOTBALL-NEWS] tick failed: %s", exc)
            time.sleep(SCHEDULER_SECONDS)

    threading.Thread(target=loop, name="football-news", daemon=True).start()
