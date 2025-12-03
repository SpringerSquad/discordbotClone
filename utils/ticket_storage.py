import json
import os
from datetime import datetime
from typing import List, Dict, Optional

TICKETS_FILE = "tickets/tickets.json"

def load_tickets() -> List[Dict]:
    if not os.path.exists(TICKETS_FILE):
        return []
    with open(TICKETS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_ticket(ticket: Dict):
    tickets = load_tickets()
    tickets.append(ticket)
    with open(TICKETS_FILE, "w", encoding="utf-8") as f:
        json.dump(tickets, f, indent=4)

def update_ticket_status(channel_id: int, new_status: str):
    tickets = load_tickets()
    updated = False
    for ticket in tickets:
        if ticket["channel_id"] == channel_id:
            ticket["status"] = new_status
            updated = True
            break
    if updated:
        with open(TICKETS_FILE, "w", encoding="utf-8") as f:
            json.dump(tickets, f, indent=4)

def get_tickets() -> List[Dict]:
    return load_tickets()

def set_ticket_status_by_channel(channel_id: int, status: str):
    update_ticket_status(channel_id, status)
