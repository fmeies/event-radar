import logging
import sys


_FMT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> None:
    formatter = logging.Formatter(_FMT, datefmt=_DATEFMT)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)

    # App loggers stay at DEBUG so the SSE stream and file logs retain detail.
    # Root at INFO keeps third-party libs quiet without needing per-lib overrides.
    for name in ("pipeline", "claude", "sonar", "extract", "email", "auth", "web"):
        logging.getLogger(name).setLevel(logging.DEBUG)

    # Apply our formatter to uvicorn's loggers so their lines also get timestamps
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    # Belt-and-suspenders: suppress known chatty libs even though root is now INFO
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
