"""Ready-made questions about a match, answered from the data we already hold.

No language model: each question is a fixed rule over stored numbers, so it
costs nothing, is instant, and can be checked with an ordinary test. A
question only appears when its data exists for that match.

Shape of each answer: {"id", "question", "hint" (one line, always visible),
"lines" (the detail)}. Everything is information, not a signal of value: none
of it has been measured against the bookmaker's price.
"""
from typing import Any, Dict, List, Optional

LOAD_WORD = {"leve": "leve", "media": "media", "alta": "alta"}


def _short(name: str) -> str:
    return str(name or "").split(" ")[0]


def _find(players: List[Dict[str, Any]], side: str) -> Optional[Dict[str, Any]]:
    return next((p for p in players or [] if p.get("side") == side), None)


# 1 ---------------------------------------------------------------------------
def tired(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    t = _find((d.get("tload") or {}).get("players"), "player1"), _find((d.get("tload") or {}).get("players"), "player2")
    s = _find((d.get("sload") or {}).get("players"), "player1"), _find((d.get("sload") or {}).get("players"), "player2")
    if not all(t) and not all(s):
        return None
    lines, names = [], (d["p1"], d["p2"])
    for i in (0, 1):
        bits = []
        if t[i] and t[i].get("matchesPlayed"):
            bits.append(f"{t[i]['matchesPlayed']} partidos y {t[i]['totalGames']} games en este torneo (carga {LOAD_WORD.get(t[i]['loadLevel'], t[i]['loadLevel'])})")
        if s[i] and s[i].get("restDays") is not None:
            bits.append(f"descansó {s[i]['restDays']} {'día' if s[i]['restDays'] == 1 else 'días'}")
        if s[i] and s[i].get("totalMatches"):
            bits.append(f"{s[i]['totalMatches']} partidos y {s[i]['totalGames']} games en 30 días")
        if bits:
            lines.append(f"{names[i]}: " + "; ".join(bits))
    if not lines:
        return None
    hint = ""
    if all(t) and t[0].get("totalGames") is not None and t[1].get("totalGames") is not None:
        a, b = t[0]["totalGames"], t[1]["totalGames"]
        hint = (f"{_short(names[0])} {a} games · {_short(names[1])} {b}"
                + ("" if a == b else f" · {_short(names[0] if a > b else names[1])} lleva {abs(a - b)} más"))
    return {"id": "tired", "question": "¿Quién llega más cansado?", "hint": hint, "lines": lines}


# 2 ---------------------------------------------------------------------------
def head_to_head(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    h = d.get("h2h")
    if not h or not h.get("meetings"):
        return None
    surf = d.get("surface")
    same = [m for m in h["meetings"] if surf and m.get("surface") == surf]
    lines = []
    for m in h["meetings"][:4]:
        who = d["p1"] if m.get("winner") == "p1" else d["p2"]
        lines.append(f"{m['date'][:10]} · {m.get('tournament') or '?'} · ganó {who}" + (f" ({m['sets']})" if m.get("sets") else ""))
    if same:
        w1 = sum(1 for m in same if m.get("winner") == "p1")
        lines.append(f"En esta superficie: {d['p1']} {w1}-{len(same) - w1} {d['p2']}")
    return {"id": "h2h", "question": "¿Cómo le fue contra este rival?",
            "hint": f"{_short(d['p1'])} {h['p1Wins']}-{h['p2Wins']} {_short(d['p2'])}", "lines": lines}


# 2b --------------------------------------------------------------------------
def matchup(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    m = d.get("matchup")
    if not m:
        return None
    lines, hints = [], []
    for side, name in (("p1", d["p1"]), ("p2", d["p2"])):
        blk = m.get(side) or {}
        lines.extend(blk.get("lines") or [])
        lines.extend("» " + n for n in blk.get("notes") or [])
        if blk.get("record"):
            hints.append(f"{_short(name)} {blk['record']}")
    if not lines:
        return None
    return {"id": "matchup", "question": "¿Es bueno cada uno contra este rival?",
            "hint": " · ".join(hints), "lines": lines}


# 3 ---------------------------------------------------------------------------
def serve(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    lines, hints = [], []
    for i, name in enumerate((d["p1"], d["p2"])):
        lv = (d.get("levels") or [None, None])[i]
        fg = (d.get("firstGame") or {}).get("p1" if i == 0 else "p2")
        met = {m["key"]: m for m in (lv or {}).get("metrics", [])}
        bits = []
        if "hold" in met:
            m = met["hold"]
            bits.append(f"juegos de saque ganados {round(m['recent'] * 100)}% en sus últimos {m['recentSample']} (lo normal en él: {round(m['base'] * 100)}%)")
            hints.append(f"{_short(name)} {round(m['recent'] * 100)}%")
        if "break" in met:
            m = met["break"]
            bits.append(f"juegos de resto ganados {round(m['recent'] * 100)}% (lo normal: {round(m['base'] * 100)}%)")
        if fg:
            bits.append("primer game del 1er set: " + fg["text"].lower())
        if bits:
            lines.append(f"{name}: " + "; ".join(bits))
    if not lines:
        return None
    return {"id": "serve", "question": "¿Quién defiende mejor su saque?",
            "hint": " · ".join(hints), "lines": lines}


# 4 ---------------------------------------------------------------------------
def top10(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    out, hints = [], []
    for side, name in (("p1", d["p1"]), ("p2", d["p2"])):
        it = next((i for i in (d.get("context") or {}).get(side, []) if i["key"] == "top10"), None)
        if it:
            out.append(f"{name}: {it['text']}")
            hints.append(f"{_short(name)} {it.get('short') or ''}".strip())
    if not out:
        return None
    return {"id": "top10", "question": "¿Cómo le va contra los top 10 este año?", "hint": " · ".join(hints), "lines": out}


# 5 ---------------------------------------------------------------------------
def at_stake(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    lines, hints = [], []
    for side, name in (("p1", d["p1"]), ("p2", d["p2"])):
        for it in (d.get("context") or {}).get(side, []):
            if it["key"] in ("stakes", "stakes_news"):
                lines.append(f"{name}: {it['text']}")
                hints.append(f"{_short(name)} {it['short']}" if it.get('short') else f"{_short(name)} juega por algo")
                break
    if not lines:
        return None
    return {"id": "stake", "question": "¿Qué se juega cada uno?", "hint": " · ".join(hints), "lines": lines}


# 6 ---------------------------------------------------------------------------
INJURY = {"lesion", "fisico"}


def injury(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    news = d.get("news")
    if not news:
        return None
    lines = []
    for key, name in (("player1", d["p1"]), ("player2", d["p2"])):
        for it in news.get(key) or []:
            if it.get("factor") in INJURY:
                lines.append(f"{name}: {it.get('note') or it.get('headline')}")
    n = sum(len(v) for v in (news.get("latest") or {}).values())
    if not lines and not n:
        return None
    if not lines:
        lines = ["Ningún titular marcado como lesión o problema físico en los últimos 5 días."]
    return {"id": "injury", "question": "¿Hay noticias de lesión o enfermedad?",
            "hint": "ninguna marcada" if lines[0].startswith("Ningún") else f"{len(lines)} marcada{'s' if len(lines) > 1 else ''}",
            "lines": lines}


# 7 ---------------------------------------------------------------------------
def history(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    picks = [p for p in d.get("picks") or [] if p.get("history")]
    if not picks:
        return None
    lines = []
    for p in picks[:4]:
        h = p["history"]
        lines.append(f"{p['label']}: la casa le da {round(p['probability'] * 100)}%; en apuestas del mismo tramo "
                     f"({p.get('band')}%) salió {round(h['winRate'] * 100)}% de {h['n']} (se esperaba {round(h['expected'] * 100)}%)"
                     + (f"; a la cuota de la casa rindió {h['yield'] * 100:.1f}%" if h.get("yield") is not None else ""))
    h0 = picks[0]["history"]
    return {"id": "history", "question": "¿Cuántas veces salió una apuesta así?",
            "hint": f"{picks[0]['label']}: {round(h0['winRate'] * 100)}% de {h0['n']}", "lines": lines}


# 8 ---------------------------------------------------------------------------
def why_favourite(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    mw = (d.get("odds") or {}).get("matchWinner") or {}
    if not (mw.get("p1", 0) > 1 and mw.get("p2", 0) > 1):
        return None
    f1 = (1 / mw["p1"]) / (1 / mw["p1"] + 1 / mw["p2"])
    fav, dog, pf = (d["p1"], d["p2"], f1) if f1 >= 0.5 else (d["p2"], d["p1"], 1 - f1)
    lines = [f"La cuota le da {round(pf * 100)}% a {fav} y {round((1 - pf) * 100)}% a {dog} (sin el margen de la casa)."]
    r1, r2 = d.get("rank") or (None, None)
    if r1 and r2 and r1 != r2:
        better = d["p1"] if r1 < r2 else d["p2"]
        lines.append(f"Ranking #{r1} contra #{r2}: " + (f"{fav} es favorito y tiene mejor ranking." if better == fav
                                                     else f"{fav} es favorito pese a tener peor ranking; la cuota pesa también superficie, forma y cansancio."))
    h = d.get("h2h")
    if h and h.get("meetings"):
        lead = d["p1"] if h["p1Wins"] > h["p2Wins"] else d["p2"] if h["p2Wins"] > h["p1Wins"] else None
        lines.append(f"Cara a cara {h['p1Wins']}-{h['p2Wins']}" + (f", a favor de {lead}." if lead else ", parejo."))
    for i, name in enumerate((d["p1"], d["p2"])):
        lv = (d.get("levels") or [None, None])[i]
        if lv and lv.get("level") not in (None, "normal"):
            lines.append(f"{name}: {lv['headline']}")
    return {"id": "favourite", "question": "¿Por qué la casa lo ve favorito?",
            "hint": f"{_short(fav)} {round(pf * 100)}%", "lines": lines}


RULES = (tired, head_to_head, matchup, serve, top10, at_stake, injury, history, why_favourite)


def build_questions(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for rule in RULES:
        try:
            r = rule(d)
        except Exception:        # one broken rule must not hide the others
            r = None
        if r:
            out.append(r)
    return out
