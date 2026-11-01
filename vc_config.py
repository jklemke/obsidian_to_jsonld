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

# D-006: two kinds of address.
#   IRI  = the concept itself, permanent and version-independent:  https://vernacular.cloud/<key>/
#   page = what the concept said in one release, frozen (D-007):     https://vernacular.cloud/<version>/<key>/
# JSON-LD @id and SKOS links use IRIs; HTML navigation inside a version uses pages.
KEY_PATTERN = r"[A-Za-z][0-9A-Za-z]{23}"   # key-map-hash: letter + base62, 24 chars
VERSION_PATTERN = r"\d+\.\d+\.\d+"

ROOT_CONCEPT_KEY = _cfg["root_concept_key"]
SCHEME_LABEL = _cfg.get("scheme_label", "Badinagean Nomenclature")
SCHEME_IRI = f"{DOMAIN}/concept-scheme/"
SCHEME_PAGE_URL = f"{VERSION_URL}/concept-scheme/"


def concept_iri(key):
    """Permanent, version-independent IRI of a concept (D-006)."""
    return f"{DOMAIN}/{key}/"


def page_url(key, version=VERSION):
    """Frozen page for a concept in one version (default: the version being built)."""
    return f"{DOMAIN}/{version}/{key}/"


ROOT_CONCEPT_IRI = concept_iri(ROOT_CONCEPT_KEY)

# One JSON-LD @context for every generated page. The "@type": "@id" entries say
# that these properties hold links (IRIs), not text; without them a plain string
# such as "skos:broader": "https://..." is read as a text value.
_LINK = {"@type": "@id"}
JSONLD_CONTEXT = {
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "dct": "http://purl.org/dc/terms/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "owl": "http://www.w3.org/2002/07/owl#",
    "skos:broader": _LINK,
    "skos:narrower": _LINK,
    "skos:related": _LINK,
    "skos:inScheme": _LINK,
    "skos:hasTopConcept": _LINK,
    "dct:isVersionOf": _LINK,
    "dct:hasVersion": _LINK,
    "owl:versionIRI": _LINK,
}


def check_paths():
    """Return a list of problems with the configured folders (empty if all good)."""
    problems = []
    if not VAULT_DIR.is_dir():
        problems.append(f"vault_dir not found: {VAULT_DIR}")
    if not SITE_DIR.is_dir():
        problems.append(f"site_dir not found: {SITE_DIR}")
    return problems
