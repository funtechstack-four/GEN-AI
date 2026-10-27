"""Environment driven runtime settings. Secrets are read only at runtime."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv
except ImportError:  # Keep the pure guardrail checks usable without optional runtime installs.
    def load_dotenv(path: Path) -> None:
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() and not key.lstrip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


ENV_FILE = ROOT / ".env"
if not ENV_FILE.exists():
    ENV_FILE = ROOT / "env"  # Windows users sometimes save the dotenv file without the leading dot.
load_dotenv(ENV_FILE)


def setting(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def enabled(name: str, default: bool = False) -> bool:
    return setting(name, str(default)).lower() in {"1", "true", "yes", "on"}


SAMPLE_MODE = enabled("SAMPLE_MODE", True)
ZETARIS_REST_URL = setting("ZETARIS_REST_URL", "http://localhost:8888/api/v1.0").rstrip("/")
ZETARIS_API_KEY = setting("ZETARIS_API_KEY")
ZETARIS_ORG_ID = setting("ZETARIS_ORG_ID", "1")
ZETARIS_NOTICES_TABLE = setting("ZETARIS_NOTICES_TABLE", "land_files.gazette_notices")
ZETARIS_JUDGMENTS_TABLE = setting("ZETARIS_JUDGMENTS_TABLE", "land_files.judgments")
ZETARIS_REGISTRY_TABLE = setting("ZETARIS_REGISTRY_TABLE", "land_files.synthetic_registry")
ZETARIS_SERIALS_TABLE = setting("ZETARIS_SERIALS_TABLE", "land_files.cancelled_serials")
METERLESS_BRIDGE_URL = setting("METERLESS_BRIDGE_URL", "http://localhost:4001").rstrip("/")
METERLESS_BASE_URL = setting("METERLESS_BASE_URL", "http://127.0.0.1:8088/v1").rstrip("/")
METERLESS_RUNTIME_TOKEN = setting("METERLESS_RUNTIME_TOKEN")
METERLESS_MODEL = setting("NEMOTRON_MODEL", setting("METERLESS_MODEL", "meterless/auto"))
