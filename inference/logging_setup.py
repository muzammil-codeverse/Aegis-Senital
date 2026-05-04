from __future__ import annotations
import logging
import logging.handlers
from pathlib import Path

_LOG_DIR = Path(__file__).parent.parent / "logs"

_FMT = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
_DATE_FMT = "%Y-%m-%dT%H:%M:%S"

_configured = False


def configure_logging(log_level: int = logging.INFO) -> None:
    """
    Set up file-based logging for the Aegis Sentinel inference pipeline.

    Creates three daily-rotating log files (7-day retention):
      logs/inference.log       all inference pipeline events  (INFO+)
      logs/event.log           threat events from EventEngine (INFO+)
      logs/system_health.log   system state snapshots         (INFO+)

    Idempotent: calling multiple times has no effect after the first call.
    """
    global _configured
    if _configured:
        return
    _configured = True

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    _attach("inference",                _LOG_DIR / "inference.log",     log_level)
    _attach("inference.event_engine",   _LOG_DIR / "event.log",         logging.INFO)
    _attach("inference.scenario_engine", _LOG_DIR / "event.log",        logging.INFO)
    _attach("inference.system_state",   _LOG_DIR / "system_health.log", logging.INFO)


def _attach(logger_name: str, log_path: Path, level: int) -> None:
    lg = logging.getLogger(logger_name)
    # Avoid adding duplicate handlers if the logger already has one pointing here
    if any(
        isinstance(h, logging.handlers.TimedRotatingFileHandler)
        and getattr(h, "baseFilename", None) == str(log_path)
        for h in lg.handlers
    ):
        return

    handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(log_path),
        when="midnight",
        backupCount=7,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))
    lg.addHandler(handler)
    if lg.level == logging.NOTSET:
        lg.setLevel(level)
    else:
        lg.setLevel(min(lg.level, level))
