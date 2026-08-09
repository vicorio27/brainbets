import json
import os
import requests
import time
from datetime import datetime, timezone, timedelta

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
WORKFLOW_EXECUTOR_URL = os.getenv("WORKFLOW_EXECUTOR_URL", "http://workflow_executor:5001")

last_update_id = 0
processed_update_ids = set()
MAX_PROCESSED_IDS = 200


def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        response = requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=30)
        return response.status_code == 200
    except Exception as e:
        print(f"[ERROR] Telegram: {e}")
        return False


def get_updates():
    global last_update_id
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = {"offset": last_update_id + 1, "timeout": 5}
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("ok") and data.get("result"):
                return data["result"]
    except Exception as e:
        print(f"[ERROR] Get updates: {e}")
    return []


def _today_str():
    bogota_tz = timezone(timedelta(hours=-5))
    return datetime.now(bogota_tz).strftime("%Y-%m-%d")


def trigger_workflow(workflow_name, sport=None, date_from=None, date_to=None):
    """Trigger a workflow via the executor service"""
    try:
        if sport:
            url = f"{WORKFLOW_EXECUTOR_URL}/execute/{workflow_name}/{sport}"
        else:
            url = f"{WORKFLOW_EXECUTOR_URL}/execute/{workflow_name}"
        params = {}
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        response = requests.post(url, params=params, timeout=180)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[ERROR] Workflow executor: {response.status_code}")
            return None
    except Exception as e:
        print(f"[ERROR] Workflow executor: {e}")
        return None


def cmd_collect(sport=None):
    label = sport if sport else "todos los deportes"
    send_telegram(f"Recolectando datos ({label})...")
    result = trigger_workflow("collect", sport)
    if not result:
        send_telegram(f"Error al ejecutar Data Collection ({label}).")


def cmd_predict(sport=None):
    label = sport if sport else "todos los deportes"
    today = _today_str()
    send_telegram(f"Generando predicciones del día ({label})...")
    result = trigger_workflow("predict", sport, date_from=today, date_to=today)
    if not result:
        send_telegram(f"Error al generar predicciones del día ({label}).")


def cmd_predict_all(sport=None):
    """Run prediction over all available matches (legacy behavior)."""
    label = sport if sport else "todos los deportes"
    send_telegram(f"Generando predicciones históricas/disponibles ({label})...")
    result = trigger_workflow("predict_all", sport)
    if not result:
        send_telegram(f"Error al generar predicciones históricas ({label}).")


def cmd_validate(sport=None):
    label = sport if sport else "todos los deportes"
    today = _today_str()
    send_telegram(f"Validando predicciones del día ({label})...")
    result = trigger_workflow("validate", sport, date_from=today, date_to=today)
    if not result:
        send_telegram(f"Error al validar predicciones del día ({label}).")


def cmd_pipeline(sport=None):
    """Run the full pipeline via the dedicated endpoint."""
    label = sport if sport else "todos los deportes"
    today = _today_str()
    send_telegram(f"Ejecutando Pipeline completo del día ({label})...")
    result = trigger_workflow("pipeline", sport, date_from=today, date_to=today)
    if not result:
        send_telegram(f"Error al ejecutar el pipeline completo del día ({label}).")
    else:
        send_telegram(f"Pipeline completo del día ({label})!")


def cmd_train():
    """Train Elo and Poisson models from historical data."""
    send_telegram("Entrenando modelos Elo y Poisson...")
    result = trigger_workflow("train")
    if not result:
        send_telegram("Error al entrenar modelos.")

def cmd_update_scores(sport=None):
    """Update live scores and prediction fulfillment for a sport or all sports."""
    label = sport if sport else "todos los deportes"
    send_telegram(f"Actualizando progreso en vivo ({label})...")
    workflow = "update_scores"
    if sport == "football":
        workflow = "update_scores_football"
    elif sport == "tennis":
        workflow = "update_scores_tennis"
    result = trigger_workflow(workflow)
    if not result:
        send_telegram(f"Error al actualizar progreso en vivo ({label}).")


def cmd_update_tennis_scores():
    """Update finished tennis match scores from the API."""
    send_telegram("Actualizando scores de tenis...")
    result = trigger_workflow("update_tennis_scores")
    if not result:
        send_telegram("Error al actualizar scores de tenis.")


def cmd_help():
    send_telegram(
        "BrainBets Bot Commands\n\n"
        "Generales:\n"
        "/collect - Recolectar datos de todos los deportes\n"
        "/predict - Generar predicciones del día para todos los deportes\n"
        "/predict_all - Generar predicciones sobre todos los partidos disponibles\n"
        "/validate - Validar predicciones de todos los deportes\n"
        "/pipeline - Ejecutar pipeline completo del día para todos los deportes\n\n"
        "Futbol:\n"
        "/collect_football - Recolectar partidos de futbol\n"
        "/predict_football - Predecir partidos de futbol del día\n"
        "/predict_all_football - Predecir todos los partidos de futbol disponibles\n"
        "/validate_football - Validar predicciones de futbol\n"
        "/pipeline_football - Pipeline completo de futbol\n\n"
        "Tenis:\n"
        "/collect_tennis - Recolectar partidos de tenis\n"
        "/predict_tennis - Predecir partidos de tenis del día\n"
        "/predict_all_tennis - Predecir todos los partidos de tenis disponibles\n"
        "/validate_tennis - Validar predicciones de tenis\n"
        "/pipeline_tennis - Pipeline completo de tenis\n"
        "/update_tennis_scores - Actualizar scores de tenis finalizados\n\n"
        "Progreso en vivo:\n"
        "/update_scores - Actualizar progreso de todos los deportes\n"
        "/update_scores_football - Progreso en vivo de futbol\n"
        "/update_scores_tennis - Progreso en vivo de tenis\n\n"
        "/train - Entrenar modelos Elo/Poisson\n"
        "/help - Mostrar esta ayuda"
    )


def process_command(text):
    command = text.strip().lower()

    # General commands
    if command == '/collect':
        cmd_collect()
    elif command == '/predict':
        cmd_predict()
    elif command == '/predict_all':
        cmd_predict_all()
    elif command == '/validate':
        cmd_validate()
    elif command == '/pipeline':
        cmd_pipeline()
    elif command == '/train':
        cmd_train()
    elif command == '/update_tennis_scores':
        cmd_update_tennis_scores()
    elif command == '/update_scores':
        cmd_update_scores()
    elif command == '/update_scores_football':
        cmd_update_scores('football')
    elif command == '/update_scores_tennis':
        cmd_update_scores('tennis')
    elif command == '/help':
        cmd_help()
    # Sport-specific commands
    elif command == '/collect_football':
        cmd_collect('football')
    elif command == '/predict_football':
        cmd_predict('football')
    elif command == '/predict_all_football':
        cmd_predict_all('football')
    elif command == '/validate_football':
        cmd_validate('football')
    elif command == '/pipeline_football':
        cmd_pipeline('football')
    elif command == '/collect_tennis':
        cmd_collect('tennis')
    elif command == '/predict_tennis':
        cmd_predict('tennis')
    elif command == '/predict_all_tennis':
        cmd_predict_all('tennis')
    elif command == '/validate_tennis':
        cmd_validate('tennis')
    elif command == '/pipeline_tennis':
        cmd_pipeline('tennis')
    else:
        send_telegram(f"Comando no reconocido: {command}\n\nUsa /help para ver los comandos disponibles.")


print("=" * 50)
print("BrainBets - Telegram Bot")
print("=" * 50)
print(f"\nWorkflow Executor URL: {WORKFLOW_EXECUTOR_URL}")
print("\nBot iniciado. Escuchando comandos...")
print("Envia un comando en Telegram:")
print("  /collect, /predict, /validate, /pipeline, /train, /help")
print("  /collect_football, /predict_football, /validate_football, /pipeline_football")
print("  /collect_tennis, /predict_tennis, /validate_tennis, /pipeline_tennis")
print("  /update_scores, /update_scores_football, /update_scores_tennis")
print("\nPresiona Ctrl+C para detener\n")

send_telegram(
    "BrainBets Bot iniciado!\n\n"
    "Envia un comando:\n"
    "/collect, /predict, /validate, /pipeline, /train, /help\n"
    "/collect_football, /predict_football, /validate_football, /pipeline_football\n"
    "/collect_tennis, /predict_tennis, /validate_tennis, /pipeline_tennis\n"
    "/update_scores, /update_scores_football, /update_scores_tennis"
)

while True:
    try:
        updates = get_updates()
        for update in updates:
            update_id = update.get("update_id", 0)
            last_update_id = update_id
            if update_id in processed_update_ids:
                continue
            processed_update_ids.add(update_id)
            if len(processed_update_ids) > MAX_PROCESSED_IDS:
                processed_update_ids = set(sorted(processed_update_ids)[-MAX_PROCESSED_IDS:])

            message = update.get("message", {})
            text = message.get("text", "")
            chat_id = str(message.get("chat", {}).get("id", ""))

            if text and chat_id == CHAT_ID:
                print(f"[COMMAND] {text}")
                process_command(text)

        time.sleep(1)
    except KeyboardInterrupt:
        print("\nBot detenido.")
        send_telegram("BrainBets Bot detenido.")
        break
    except Exception as e:
        print(f"[ERROR] {e}")
        time.sleep(5)
