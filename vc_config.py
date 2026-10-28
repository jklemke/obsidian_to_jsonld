"""Shared settings for the Vernacular Cloud build scripts.

Every script imports its paths, version and URLs from here, and this module
reads them from config.toml. Change config.toml, not the scripts.
"""
import re
import tomllib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.toml"

with open(CONFIG_FILE, "rb") as f:
    _cfg = tomllib.load(f)


def _path(value):
    p = Path(value)
    return p if p.is_absolute() else (BASE_DIR / p).resolve()


VERSION = str(_cfg["version"]).strip()
if not re.fullmatch(r"\d+\.\d+\.\d+", VERSION):
    raise ValueError(f"config.toml: version must look like 1.2.3, got {VERSION!r}")

DOMAIN = _cfg["domain"].rstrip("/")
VAULT_DIR = _path(_cfg["vault_dir"])
SITE_DIR = _path(_cfg["site_dir"])
OUTPUT_DIR = SITE_DIR / VERSION
TEMPLATE_DIR = BASE_DIR / "templates"
PORT = int(_cfg.get("port", 8899))

VERSION_URL = f"{DOMAIN}/{VERSION}"
SCHEME_URI = f"{VERSION_URL}/concept-scheme/"
ROOT_CONCEPT_URI = f"{VERSION_URL}/{_cfg['root_concept_key']}/"


def concept_uri(key):
    """Absolute permalink for a concept in the current version."""
    return f"{VERSION_URL}/{key}/"


def check_paths():
    """Return a list of problems with the configured folders (empty if all good)."""
    problems = []
    if not VAULT_DIR.is_dir():
        problems.append(f"vault_dir not found: {VAULT_DIR}")
    if not SITE_DIR.is_dir():
        problems.append(f"site_dir not found: {SITE_DIR}")
    return problems
