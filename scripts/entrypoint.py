"""Run migrations before EVERY init-data command, including eval and pytest."""

import os
import sys

from scripts.migrate import migrate


if __name__ == "__main__":
    migrate()
    os.environ["OLIST_MIGRATIONS_READY"] = "1"
    os.execvp(sys.argv[1], sys.argv[1:])
