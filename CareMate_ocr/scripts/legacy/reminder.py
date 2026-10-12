"""Run the CareMate reminder worker separately from the API if needed."""
import asyncio
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.reminder_worker import run_reminder_worker


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run_reminder_worker())
    except KeyboardInterrupt:
        pass
