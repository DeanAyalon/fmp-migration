import subprocess

from src.config import Settings
from src.pipeline.commands import fmsadmin_cmd


def list_files(container: str, settings: Settings) -> str:
    cmd = fmsadmin_cmd(container, settings, "list", "files", "-s")
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


def list_clients(container: str, settings: Settings) -> str:
    cmd = fmsadmin_cmd(container, settings, "list", "clients", "-s")
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


def solution_client_ids(listing: str, solution: str) -> list[str]:
    """Return client IDs connected to the solution database (File Name column)."""
    client_ids: list[str] = []
    for line in listing.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Client ID"): continue
        if solution not in stripped: continue

        client_id = stripped.split(None, 1)[0]
        if client_id.isdigit(): client_ids.append(client_id)
    return client_ids


def db_status_line(listing: str, db_file: str) -> str | None:
    for line in listing.splitlines():
        if db_file in line and not line.strip().startswith("ID "): return line
    return None


def parse_db_status(line: str, db_file: str) -> str | None:
    parts = line.split()
    try: file_index = parts.index(db_file)
    except ValueError: return None

    status_index = file_index + 3
    if status_index >= len(parts): return None

    return parts[status_index]


def db_status(listing: str, db_file: str) -> str | None:
    line = db_status_line(listing, db_file)
    if line is None: return None
    return parse_db_status(line, db_file)
