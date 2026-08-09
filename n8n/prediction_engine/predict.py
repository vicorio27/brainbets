# -*- coding: utf-8 -*-
"""CLI entry point for the BrainBets prediction engine.

Usage:
    python predict.py '{"sport": "football", "match": {...}}'
    python predict.py '{"matches": [{"sport": "football", "match": {...}}, ...]}'
    echo '{"sport": "football", "match": {...}}' | python predict.py

Output:
    JSON with predictions array (or array of results for batch input).
"""
import json
import os
import sys
import urllib.error
import urllib.request

from football import predict_football
from tennis import predict_tennis, compute_ml_tennis_batch


OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
OPENAI_ENDPOINT = os.environ.get('OPENAI_ENDPOINT', 'https://api.openai.com/v1/chat/completions')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')


def _match_label(match: dict, sport: str) -> str:
    """Return a human-readable match label."""
    if sport == 'football':
        return f"{match.get('homeTeam', 'Local')} vs {match.get('awayTeam', 'Visitante')}"
    if sport == 'tennis':
        return f"{match.get('player1', 'Jugador 1')} vs {match.get('player2', 'Jugador 2')}"
    return "Partido"


def _build_nl_prompt(sport: str, match: dict, predictions: list) -> str:
    """Build a Spanish prompt asking OpenAI for natural-language explanations."""
    match_label = _match_label(match, sport)
    prompt = (
        "Eres un analista deportivo que explica predicciones a usuarios no expertos en español. "
        "A partir de los datos numéricos del siguiente partido, genera una explicación breve "
        "(máximo 3 frases por predicción) en lenguaje natural, fácil de entender. "
        "No inventes datos que no aparezcan en la entrada. Usa porcentajes enteros cuando sea posible.\n\n"
        f"Partido: {match_label} ({sport})\n"
    )

    # Include a few relevant numeric context fields.
    if sport == 'football':
        for key, label in [
            ('homePosition', 'Posición local'),
            ('awayPosition', 'Posición visitante'),
            ('homeElo', 'Elo local'),
            ('awayElo', 'Elo visitante'),
            ('expectedHomeGoals', 'Goles esperados local'),
            ('expectedAwayGoals', 'Goles esperados visitante'),
        ]:
            if match.get(key) is not None:
                prompt += f"{label}: {match[key]}\n"
    elif sport == 'tennis':
        for key, label in [
            ('rankingPlayer1', 'Ranking jugador 1'),
            ('rankingPlayer2', 'Ranking jugador 2'),
            ('eloPlayer1', 'Elo jugador 1'),
            ('eloPlayer2', 'Elo jugador 2'),
            ('surface', 'Superficie'),
        ]:
            if match.get(key) is not None:
                prompt += f"{label}: {match[key]}\n"

    prompt += "\nPredicciones:\n"
    for idx, pred in enumerate(predictions, start=1):
        prompt += (
            f"{idx}. Mercado: {pred.get('market')}\n"
            f"   Predicción: {pred.get('prediction')}\n"
            f"   Confianza: {pred.get('confidence')}%\n"
            f"   Probabilidades: {json.dumps(pred.get('probabilities', {}), ensure_ascii=False)}\n"
            f"   Justificación estadística: {pred.get('reasoning', '')}\n"
        )

    prompt += (
        "\nDevuelve únicamente un JSON array con un objeto por predicción. "
        "Cada objeto debe tener exactamente dos campos: 'market' y 'naturalLanguageReasoning'.\n"
        "Ejemplo: [{\"market\": \"Match Winner\", \"naturalLanguageReasoning\": \"...\"}]"
    )
    return prompt


def _call_openai(prompt: str) -> list:
    """Call OpenAI chat completions and return the parsed JSON array."""
    if not OPENAI_API_KEY:
        return []

    payload = {
        'model': OPENAI_MODEL,
        'messages': [
            {'role': 'system', 'content': 'Eres un asistente que responde únicamente en JSON válido.'},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.5,
        'max_tokens': 700,
        'response_format': {'type': 'json_object'},
    }

    data = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        OPENAI_ENDPOINT,
        data=data,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {OPENAI_API_KEY}',
        },
        method='POST',
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        response_text = response.read().decode('utf-8')

    response_json = json.loads(response_text)
    content = response_json['choices'][0]['message']['content']
    parsed = json.loads(content)
    if isinstance(parsed, dict) and 'predictions' in parsed:
        return parsed['predictions']
    if isinstance(parsed, list):
        return parsed
    return []


def _fallback_natural_language(pred: dict) -> str:
    """Simple fallback explanation when OpenAI is unavailable."""
    market = pred.get('market', '')
    prediction = pred.get('prediction', '')
    confidence = pred.get('confidence', 0)
    return (
        f"Para el mercado '{market}', el modelo indica '{prediction}' "
        f"con una confianza del {confidence}%. Revisa la pestaña de justificación estadística para ver los números detrás de esta recomendación."
    )


def _fmt_pct(v):
    """Format a probability as a percentage string."""
    if v is None:
        return 'N/A'
    return f"{int(round(float(v) * 100))}%"


def _build_expert_analysis_prompt(results: list) -> tuple:
    """Build a compact Spanish prompt asking OpenAI to analyze all matches like a betting expert."""
    lines = []
    for r in results:
        if r.get('error') or not r.get('predictions'):
            continue
        sport = r['sport']
        match = r.get('match', {})
        first_pred = r['predictions'][0]
        rd = first_pred.get('reasoningData', {}) or {}

        if sport == 'football':
            label = f"{match.get('homeTeam', 'Local')} vs {match.get('awayTeam', 'Visitante')}"
            tournament = match.get('tournament', match.get('league', ''))
            line = (
                f"{r['matchId']} ({sport}): {label} ({tournament}). "
                f"Calidad: {rd.get('dataQuality', 'N/A')}. "
                f"Elo: {_fmt_pct((rd.get('elo') or {}).get('home'))}/{_fmt_pct((rd.get('elo') or {}).get('draw'))}/{_fmt_pct((rd.get('elo') or {}).get('away'))}. "
                f"Poisson: {rd.get('expectedScore', 'N/A')}. "
                f"Odds: {_fmt_pct((rd.get('odds') or {}).get('home'))}/{_fmt_pct((rd.get('odds') or {}).get('draw'))}/{_fmt_pct((rd.get('odds') or {}).get('away'))}. "
            )
        else:
            label = f"{match.get('player1', 'P1')} vs {match.get('player2', 'P2')}"
            tournament = match.get('tournament', '')
            surface = rd.get('surface', match.get('surface', ''))
            line = (
                f"{r['matchId']} ({sport}): {label} ({tournament}, {surface}). "
                f"Ranking: #{match.get('rankingPlayer1', '?')} vs #{match.get('rankingPlayer2', '?')}. "
                f"Elo: {_fmt_pct((rd.get('elo') or {}).get('player1'))} vs {_fmt_pct((rd.get('elo') or {}).get('player2'))}. "
                f"ML: {_fmt_pct((rd.get('ml') or {}).get('player1'))} vs {_fmt_pct((rd.get('ml') or {}).get('player2'))}. "
                f"Odds: {_fmt_pct((rd.get('odds') or {}).get('player1'))} vs {_fmt_pct((rd.get('odds') or {}).get('player2'))}. "
            )

        pred_lines = '; '.join([f"{p['market']}={p['prediction']} ({p['confidence']}%)" for p in r['predictions']])
        lines.append(line + pred_lines)

    system_prompt = (
        "Eres un experto en apuestas deportivas con amplia experiencia en modelos predictivos "
        "(Elo, Poisson, xG, machine learning, odds) y análisis de partidos de fútbol y tenis. "
        "Tu trabajo es analizar los coeficientes y probabilidades de cada partido y dar una opinión experta, "
        "concisa y enfocada en valor de apuesta. Responde siempre en español."
    )
    user_prompt = (
        f"Analiza los siguientes {len(lines)} partidos como si fueras a asesorar a un apostador sofisticado. "
        "Para cada partido devuelve un objeto JSON con exactamente estos campos: matchId, analysis (2-3 párrafos en español con tu lectura del partido, si hay valor en la predicción del modelo comparando con las odds, y riesgos), "
        "valueBet (true/false), risks (string breve con los principales riesgos). Responde ÚNICAMENTE con un JSON válido de este formato: "
        '{"analyses": [{"matchId": "...", "analysis": "...", "valueBet": true, "risks": "..."}]}.\n\n'
        "PARTIDOS:\n" + "\n".join(lines)
    )
    return system_prompt, user_prompt


def _call_openai_batch(system_prompt: str, user_prompt: str) -> dict:
    """Call OpenAI chat completions and return parsed analyses by matchId."""
    if not OPENAI_API_KEY:
        return {}

    payload = {
        'model': OPENAI_MODEL,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': 0.7,
        'max_tokens': 4000,
        'response_format': {'type': 'json_object'},
    }

    data = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        OPENAI_ENDPOINT,
        data=data,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {OPENAI_API_KEY}',
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response_text = response.read().decode('utf-8')
        response_json = json.loads(response_text)
        content = response_json['choices'][0]['message']['content']
        parsed = json.loads(content)
        analyses = parsed.get('analyses', [])
        return {a['matchId']: a for a in analyses if 'matchId' in a and 'analysis' in a}
    except Exception:
        return {}


def predict(payload: dict, ml_probs_by_match: dict = None) -> dict:
    """Route prediction to the correct sport model."""
    sport = payload.get('sport', '').lower()
    match = payload.get('match', {})
    match_id = match.get('matchId', 'UNKNOWN')
    ml_probs = None
    if ml_probs_by_match and match_id in ml_probs_by_match:
        ml_probs = ml_probs_by_match[match_id]

    if sport == 'football':
        predictions = predict_football(match)
    elif sport == 'tennis':
        predictions = predict_tennis(match, ml_probs=ml_probs)
    else:
        raise ValueError(f"Unsupported sport: {sport}")

    return {
        'matchId': match_id,
        'sport': sport,
        'match': match,
        'predictions': predictions,
    }


def predict_batch(payload: dict) -> list:
    """Process a batch of matches."""
    matches = payload.get('matches', [])

    # Pre-compute tennis ML probabilities in a single backend call.
    ml_probs_by_match = {}
    tennis_items = [
        (idx, item) for idx, item in enumerate(matches)
        if item.get('sport', '').lower() == 'tennis'
    ]
    if tennis_items:
        tennis_matches = [item for _, item in tennis_items]
        batch_probs = compute_ml_tennis_batch([item.get('match', {}) for item in tennis_matches])
        if batch_probs:
            for (idx, item), probs in zip(tennis_items, batch_probs):
                match_id = item.get('match', {}).get('matchId', 'UNKNOWN')
                if probs:
                    ml_probs_by_match[match_id] = probs

    results = []
    for item in matches:
        try:
            results.append(predict(item, ml_probs_by_match=ml_probs_by_match))
        except Exception as e:
            # Include error result so one bad match doesn't break the batch
            match_id = item.get('match', {}).get('matchId', 'UNKNOWN')
            results.append({
                'matchId': match_id,
                'sport': item.get('sport', 'unknown'),
                'predictions': [],
                'error': str(e),
            })

    # Enrich all results with chunked OpenAI calls for expert analysis.
    analyses_by_match = {}
    chunk_size = 12
    for i in range(0, len(results), chunk_size):
        chunk = results[i:i + chunk_size]
        system_prompt, user_prompt = _build_expert_analysis_prompt(chunk)
        chunk_analyses = _call_openai_batch(system_prompt, user_prompt)
        analyses_by_match.update(chunk_analyses)

    for r in results:
        if r.get('error') or not r.get('predictions'):
            continue
        analysis = analyses_by_match.get(r['matchId'])
        if analysis and analysis.get('analysis'):
            r['naturalLanguageReasoning'] = analysis['analysis']
            r['openAiValueBet'] = analysis.get('valueBet', False)
            r['openAiRisks'] = analysis.get('risks', '')
        else:
            r['naturalLanguageReasoning'] = r['predictions'][0].get('reasoning') or _fallback_natural_language(r['predictions'][0])

    return results


def read_input() -> str:
    """Read JSON payload from stdin, file path, or first CLI argument."""
    if len(sys.argv) >= 2 and sys.argv[1] != '-':
        arg = sys.argv[1]
        # If the argument looks like a file path rather than inline JSON, read it.
        if not arg.lstrip().startswith(('{', '[')):
            try:
                with open(arg, 'r', encoding='utf-8') as f:
                    return f.read()
            except FileNotFoundError:
                sys.stderr.buffer.write(json.dumps({'error': f'File not found: {arg}'}, ensure_ascii=True).encode('utf-8'))
                sys.stderr.buffer.write(b'\n')
                sys.exit(1)
            except Exception as e:
                sys.stderr.buffer.write(json.dumps({'error': f'Failed to read file {arg}: {str(e)}'}, ensure_ascii=True).encode('utf-8'))
                sys.stderr.buffer.write(b'\n')
                sys.exit(1)
        return arg
    # Read stdin as bytes and decode as UTF-8 to preserve non-ASCII characters.
    return sys.stdin.buffer.read().decode('utf-8')


if __name__ == '__main__':
    raw = read_input().strip()
    if not raw:
        sys.stderr.buffer.write(json.dumps({'error': 'Missing JSON payload'}, ensure_ascii=True).encode('utf-8'))
        sys.stderr.buffer.write(b'\n')
        sys.exit(1)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.buffer.write(json.dumps({'error': f'Invalid JSON: {str(e)}'}, ensure_ascii=True).encode('utf-8'))
        sys.stderr.buffer.write(b'\n')
        sys.exit(1)

    try:
        if isinstance(payload, list) or 'matches' in payload:
            result = predict_batch(payload if isinstance(payload, dict) else {'matches': payload})
        else:
            result = predict(payload)
        output = json.dumps(result, ensure_ascii=True, indent=2)
        sys.stdout.buffer.write(output.encode('utf-8'))
        sys.stdout.buffer.write(b'\n')
    except Exception as e:
        sys.stderr.buffer.write(json.dumps({'error': str(e)}, ensure_ascii=True).encode('utf-8'))
        sys.stderr.buffer.write(b'\n')
        sys.exit(1)
