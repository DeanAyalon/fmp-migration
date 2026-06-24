from pathlib import Path

# Local staging directory
STAGING_DIR = Path("staging")

# Command logging
_SENSITIVE_FLAGS = frozenset({"-p", "--password"})

# FMS database status
_OPEN_STATUSES = frozenset({"Normal", "Opening"})
_CLOSED_STATUSES = frozenset({"Closed"})

# Close / graceful disconnect
_CLOSE_POLL_INTERVAL_SECONDS = 2    # interval between db status checks
_CLOSE_POLL_TIMEOUT_SECONDS = 120   # max wait for db to close
_GRACE_WAIT_SECONDS = 60            # user warning delay before closing
_GRACE_POLL_INTERVAL_SECONDS = 2    # interval between client connection checks
_MAINTENANCE_WARNING = "המערכת תסגר בעוד דקה למען עדכון, נא לשמור את העבודה שלכם."
_MIGRATION_DISCONNECT_MESSAGE = "המערכת מבצעת עדכון, נא להתחבר מחדש בעוד מספר דקות."

# Reopen
_REOPEN_DELAY_SECONDS = 5
_REOPEN_RETRY_INTERVAL_SECONDS = 5
_REOPEN_MAX_ATTEMPTS = 6
