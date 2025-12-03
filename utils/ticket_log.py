import os
import json
from datetime import datetime

LOGS_DIR = "logs"
LOG_FILE = os.path.join(LOGS_DIR, "ticket_events.json")


def log_ticket_event(event_type: str, data: dict):
    """Allgemeine Logging-Funktion für alle Ticket-Events"""
    os.makedirs(LOGS_DIR, exist_ok=True)

    log_entry = {
        "time": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "data": data
    }

    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
                if not isinstance(logs, list):
                    logs = []
        except json.JSONDecodeError:
            logs = []
    else:
        logs = []

    logs.append(log_entry)

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=4, ensure_ascii=False)


# ==== Alte Funktionsnamen als Wrapper ====
def log_ticket_create(channel_name: str, user_id: int, channel_id: int, username: str = None):
    """Kompatibilitäts-Funktion für 'ticket_created'"""
    log_ticket_event("ticket_created", {
        "channel_name": channel_name,
        "user_id": user_id,
        "username": username,
        "channel_id": channel_id
    })


def log_ticket_close(channel_name: str, user_id: int, channel_id: int, reason: str = None):
    """Kompatibilitäts-Funktion für 'ticket_closed'"""
    log_ticket_event("ticket_closed", {
        "channel_name": channel_name,
        "user_id": user_id,
        "channel_id": channel_id,
        "reason": reason
    })


def log_ticket_reopen(channel_name: str, user_id: int, channel_id: int, reason: str = None):
    """Kompatibilitäts-Funktion für 'ticket_reopened'"""
    log_ticket_event("ticket_reopened", {
        "channel_name": channel_name,
        "user_id": user_id,
        "channel_id": channel_id,
        "reason": reason
    })


def update_ticket_status(ticket_id: str, new_status: str):
    """
    Aktualisiert den Status eines Tickets in der tickets.json.
    """
    tickets_file = "tickets/tickets.json"
    try:
        if not os.path.exists(tickets_file):
            return

        with open(tickets_file, "r", encoding="utf-8") as f:
            tickets = json.load(f)

        # Ticket suchen und Status ändern
        for ticket in tickets:
            if str(ticket.get("ticket_id")) == str(ticket_id):
                ticket["status"] = new_status
                break

        with open(tickets_file, "w", encoding="utf-8") as f:
            json.dump(tickets, f, indent=4, ensure_ascii=False)

        # Log schreiben
        log_ticket_event("ticket_status_updated", {
            "ticket_id": ticket_id,
            "new_status": new_status
        })
    except Exception as e:
        print(f"[update_ticket_status] Fehler: {e}")
