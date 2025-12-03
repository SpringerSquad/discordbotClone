import os

TICKET_COUNTER_FILE = "ticket_counter.txt"

def get_next_ticket_number() -> int:
    if not os.path.exists(TICKET_COUNTER_FILE):
        with open(TICKET_COUNTER_FILE, "w", encoding="utf-8") as f:
            f.write("1")
        return 1

    with open(TICKET_COUNTER_FILE, "r+", encoding="utf-8") as f:
        content = f.read().strip()
        number = int(content) if content.isdigit() else 0
        number += 1
        f.seek(0)
        f.write(str(number))
        f.truncate()
        return number
