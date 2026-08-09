"""BrainBets Workflow Executor.

This service acts as a thin proxy between the Telegram Bot and n8n.
It receives pipeline commands and triggers the corresponding n8n workflows
via webhooks. All business logic lives inside n8n workflows.
"""
from flask import Flask, request, jsonify
from datetime import datetime, timezone, timedelta
import os
import requests

app = Flask(__name__)


def _today_str() -> str:
    # Use America/Bogota timezone (UTC-5) for consistent date handling
    bogota_tz = timezone(timedelta(hours=-5))
    return datetime.now(bogota_tz).strftime("%Y-%m-%d")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://n8n:5678")

# Map command names to n8n webhook paths.
# Defaults target the DB-first workflows. Override via env vars to use file-based workflows.
WORKFLOW_WEBHOOKS = {
    "collect": os.getenv("WEBHOOK_COLLECT", f"{N8N_BASE_URL}/webhook/data-collection-db"),
    "predict": os.getenv("WEBHOOK_PREDICT", f"{N8N_BASE_URL}/webhook/predictions-db"),
    "predict_all": os.getenv("WEBHOOK_PREDICT_ALL", f"{N8N_BASE_URL}/webhook/predictions-db-all"),
    "validate": os.getenv("WEBHOOK_VALIDATE", f"{N8N_BASE_URL}/webhook/validation-db"),
    "historical": os.getenv("WEBHOOK_HISTORICAL", f"{N8N_BASE_URL}/webhook/historical-ingestion"),
    "train": os.getenv("WEBHOOK_TRAIN", f"{N8N_BASE_URL}/webhook/train-models"),
    "update_scores": os.getenv("WEBHOOK_UPDATE_SCORES", f"{N8N_BASE_URL}/webhook/update-scores"),
    "update_scores_football": os.getenv("WEBHOOK_UPDATE_SCORES_FOOTBALL", f"{N8N_BASE_URL}/webhook/update-scores-football"),
    "update_scores_tennis": os.getenv("WEBHOOK_UPDATE_SCORES_TENNIS", f"{N8N_BASE_URL}/webhook/update-scores-tennis"),
    "update_tennis_scores": os.getenv("WEBHOOK_UPDATE_TENNIS_SCORES", f"{N8N_BASE_URL}/webhook/update-tennis-scores"),
}

# Supported sport codes.
SPORTS = {"football", "tennis"}


def send_telegram(message: str) -> bool:
    """Send a notification to Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        response = requests.post(
            url,
            json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=30,
        )
        return response.status_code == 200
    except Exception as e:
        print(f"[ERROR] Telegram: {e}")
        return False


def trigger_n8n_workflow(workflow_name: str, sport: str = None, extra_query: dict = None) -> dict:
    """Trigger an n8n workflow via its webhook."""
    url = WORKFLOW_WEBHOOKS.get(workflow_name)
    if not url:
        return {"status": "error", "message": f"Unknown workflow: {workflow_name}"}

    params = {}
    if sport and sport.lower() != "all":
        params["sport"] = sport.lower()
    if extra_query:
        params.update({k: v for k, v in extra_query.items() if v is not None})

    try:
        response = requests.post(url, params=params, timeout=180)
        if response.status_code in (200, 201):
            try:
                return {"status": "success", "data": response.json()}
            except ValueError:
                return {"status": "success", "data": response.text}
        else:
            return {
                "status": "error",
                "message": f"n8n returned {response.status_code}",
                "details": response.text,
            }
    except requests.exceptions.Timeout:
        return {"status": "error", "message": "n8n workflow timed out"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _sport_label(sport: str) -> str:
    return sport.lower() if sport and sport.lower() != "all" else "todos los deportes"


def _ensure_date_query(extra_query: dict) -> dict:
    """Fill missing from/to with today's UTC date so n8n never sends empty dates."""
    today = _today_str()
    if not extra_query.get("from"):
        extra_query["from"] = today
    if not extra_query.get("to"):
        extra_query["to"] = today
    return extra_query


@app.route("/execute/<workflow_name>", methods=["POST"])
def execute_workflow(workflow_name: str):
    """Execute a pipeline workflow in n8n for all sports (legacy endpoint)."""
    return _execute_workflow_sport(workflow_name, None)


@app.route("/execute/<workflow_name>/<sport>", methods=["POST"])
def execute_workflow_sport(workflow_name: str, sport: str):
    """Execute a pipeline workflow in n8n for a specific sport."""
    return _execute_workflow_sport(workflow_name, sport)


@app.route("/execute/predict_all", methods=["POST"])
def execute_predict_all():
    """Execute prediction over all available matches (legacy /matches/latest behavior)."""
    return _execute_workflow_sport("predict_all", None)


@app.route("/execute/predict_all/<sport>", methods=["POST"])
def execute_predict_all_sport(sport: str):
    """Execute prediction over all available matches for a specific sport."""
    return _execute_workflow_sport("predict_all", sport)


def _execute_workflow_sport(workflow_name: str, sport: str):
    """Internal helper to execute a workflow and notify Telegram."""
    if sport and sport.lower() not in SPORTS and sport.lower() != "all":
        return jsonify({"status": "error", "message": f"Unsupported sport: {sport}"}), 400

    extra_query = _ensure_date_query({
        "from": request.args.get("from"),
        "to": request.args.get("to"),
    })
    date_label = f" ({extra_query['from']} a {extra_query['to']})"

    sport_label = _sport_label(sport)
    send_telegram(f"🚀 Ejecutando workflow: <b>{workflow_name}</b> ({sport_label}){date_label}")

    result = trigger_n8n_workflow(workflow_name, sport, extra_query=extra_query)

    if result["status"] == "success":
        send_telegram(f"✅ Workflow <b>{workflow_name}</b> ({sport_label}) completado.")
        return jsonify(result), 200
    else:
        error_msg = result.get("message", "Unknown error")
        send_telegram(f"❌ Error en workflow <b>{workflow_name}</b> ({sport_label}): {error_msg}")
        return jsonify(result), 502


@app.route("/execute/pipeline", methods=["POST"])
def execute_pipeline():
    """Execute the full pipeline for all sports: collect -> predict -> validate."""
    return _execute_pipeline_sport(None)


@app.route("/execute/update_scores", methods=["POST"])
def execute_update_scores():
    """Execute live score updates for all sports."""
    return _execute_update_scores(None)


@app.route("/execute/update_scores/<sport>", methods=["POST"])
def execute_update_scores_sport(sport: str):
    """Execute live score updates for a specific sport."""
    return _execute_update_scores(sport)


def _execute_update_scores(sport: str):
    """Run football and/or tennis live score update workflows."""
    if sport and sport.lower() not in SPORTS and sport.lower() != "all":
        return jsonify({"status": "error", "message": f"Unsupported sport: {sport}"}), 400

    sport_label = _sport_label(sport)
    send_telegram(f"🔄 Actualizando progreso en vivo ({sport_label})...")

    results = {}
    if not sport or sport.lower() in ("all", "football"):
        results["football"] = trigger_n8n_workflow("update_scores_football")
    if not sport or sport.lower() in ("all", "tennis"):
        results["tennis"] = trigger_n8n_workflow("update_scores_tennis")

    failed = [k for k, v in results.items() if v.get("status") != "success"]
    if failed:
        send_telegram(f"❌ Error actualizando progreso en vivo ({sport_label}): {', '.join(failed)}")
        return jsonify({"status": "error", "results": results}), 502

    send_telegram(f"✅ Progreso en vivo actualizado ({sport_label}).")
    return jsonify({"status": "success", "results": results}), 200


@app.route("/execute/pipeline/<sport>", methods=["POST"])
def execute_pipeline_sport(sport: str):
    """Execute the full pipeline for a specific sport: collect -> predict -> validate."""
    return _execute_pipeline_sport(sport)


def _execute_pipeline_sport(sport: str):
    """Internal helper to run collect -> predict -> validate for a sport."""
    if sport and sport.lower() not in SPORTS and sport.lower() != "all":
        return jsonify({"status": "error", "message": f"Unsupported sport: {sport}"}), 400

    extra_query = _ensure_date_query({
        "from": request.args.get("from"),
        "to": request.args.get("to"),
    })
    date_label = f" ({extra_query['from']} a {extra_query['to']})"

    sport_label = _sport_label(sport)
    send_telegram(f"🚀 Ejecutando pipeline completo ({sport_label}){date_label}: collect → predict → validate")

    collect_result = trigger_n8n_workflow("collect", sport)
    collect_ok = collect_result["status"] == "success"
    if not collect_ok:
        send_telegram(f"⚠️ Data Collection ({sport_label}) falló. Continuando con datos existentes...")

    predict_result = trigger_n8n_workflow("predict", sport, extra_query=extra_query)
    if predict_result["status"] != "success":
        error_msg = predict_result.get("message", "Unknown error")
        send_telegram(f"❌ Error en Predict ({sport_label}): {error_msg}")
        return jsonify({"status": "error", "stage": "predict", "details": predict_result}), 502

    validate_result = trigger_n8n_workflow("validate", sport, extra_query=extra_query)
    if validate_result["status"] != "success":
        error_msg = validate_result.get("message", "Unknown error")
        send_telegram(f"❌ Error en Validate ({sport_label}): {error_msg}")
        return jsonify({"status": "error", "stage": "validate", "details": validate_result}), 502

    send_telegram(f"✅ Pipeline completo ({sport_label}){date_label} finalizado.")
    return jsonify({
        "status": "success",
        "collect": {"success": collect_ok, "details": collect_result},
        "predict": predict_result,
        "validate": validate_result,
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
