"""Research vault path resolution for magis-capital-partners/research-vault.

Physical letter/HK/SumZero content lives in a private sibling repo (or
RESEARCH_VAULT_ROOT). JSON refs in document_registry and dashboard payloads
keep the stable prefix ``_system/reference/...`` for backward compatibility.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Stable logical refs committed in ops-repo JSON (do not change).
LETTERS_REF_PREFIX = "_system/reference/superinvestor-letters"
WISDOM_REF_PREFIX = "_system/reference/investment-wisdom"
SUMZERO_REF_PREFIX = "_system/reference/sumzero-research"
PODCASTS_REF_PREFIX = "_system/reference/podcasts"
VIDEOS_REF_PREFIX = "_system/reference/video"

# Legacy in-repo locations (pre-split); used only when vault is unavailable.
LEGACY_LETTERS = ROOT / "_system" / "reference" / "superinvestor-letters"
LEGACY_WISDOM = ROOT / "_system" / "reference" / "investment-wisdom"
LEGACY_SUMZERO = ROOT / "_system" / "reference" / "sumzero-research"
LEGACY_PODCASTS = ROOT / "_system" / "reference" / "podcasts" / "_corpus"
LEGACY_VIDEOS = ROOT / "_system" / "reference" / "video" / "_corpus"

# Default clone target relative to ops repo root.
DEFAULT_VAULT_REL = Path("_external") / "research-vault"
DEFAULT_VAULT_SIBLING = Path("research-vault")


def _env_vault_root() -> Path | None:
    raw = os.environ.get("RESEARCH_VAULT_ROOT", "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    else:
        p = p.resolve()
    return p


def research_vault_root(*, create: bool = False) -> Path | None:
    """Return the research vault root directory, or None if not configured."""
    env = _env_vault_root()
    if env is not None:
        if create and not env.is_dir():
            env.mkdir(parents=True, exist_ok=True)
        return env if env.is_dir() or create else None

    for candidate in (
        (ROOT / DEFAULT_VAULT_REL).resolve(),
        (ROOT.parent / DEFAULT_VAULT_SIBLING).resolve(),
    ):
        if candidate.is_dir():
            return candidate
    return None


def _vault_subdir(name: str, legacy: Path, *, create: bool = False) -> Path:
    vault = research_vault_root(create=create)
    if vault is not None:
        path = vault / name
        if create:
            path.mkdir(parents=True, exist_ok=True)
            return path
        if path.is_dir() or os.environ.get("RESEARCH_VAULT_ROOT"):
            if create or path.is_dir():
                return path
    if legacy.is_dir() or (create and vault is None):
        if create:
            legacy.mkdir(parents=True, exist_ok=True)
        return legacy
    if vault is not None:
        path = vault / name
        if create:
            path.mkdir(parents=True, exist_ok=True)
            return path
    return legacy


def letters_root(*, create: bool = False) -> Path:
    return _vault_subdir("superinvestor-letters", LEGACY_LETTERS, create=create)


def wisdom_root(*, create: bool = False) -> Path:
    return _vault_subdir("investment-wisdom", LEGACY_WISDOM, create=create)


def sumzero_root(*, create: bool = False) -> Path:
    return _vault_subdir("sumzero-research", LEGACY_SUMZERO, create=create)


def podcasts_root(*, create: bool = False) -> Path:
    """Transcript corpus root (research-vault/podcasts or legacy _corpus)."""
    return _vault_subdir("podcasts", LEGACY_PODCASTS, create=create)


def videos_root(*, create: bool = False) -> Path:
    """Video transcript corpus root (research-vault/videos).

    No legacy location: this corpus was never in-repo, so it points at the vault
    or at the same path under the ops repo if no vault is configured.
    """
    return _vault_subdir("videos", LEGACY_VIDEOS, create=create)


def dropbox_ingestion_root(*, create: bool = False) -> Path:
    legacy = ROOT / "_system" / "dropbox_ingestion"
    vault = research_vault_root(create=create)
    if vault is not None:
        path = vault / "dropbox-ingestion"
        if create:
            path.mkdir(parents=True, exist_ok=True)
            return path
        if path.is_dir() or os.environ.get("RESEARCH_VAULT_ROOT"):
            return path if path.is_dir() or create else path
    return legacy


def letters_ref(relative: str | Path = "") -> str:
    rel = str(relative).replace("\\", "/").lstrip("/")
    return f"{LETTERS_REF_PREFIX}/{rel}" if rel else LETTERS_REF_PREFIX


def wisdom_ref(relative: str | Path = "") -> str:
    rel = str(relative).replace("\\", "/").lstrip("/")
    return f"{WISDOM_REF_PREFIX}/{rel}" if rel else WISDOM_REF_PREFIX


def podcasts_ref(relative: str | Path = "") -> str:
    rel = str(relative).replace("\\", "/").lstrip("/")
    return f"{PODCASTS_REF_PREFIX}/{rel}" if rel else PODCASTS_REF_PREFIX


def videos_ref(relative: str | Path = "") -> str:
    rel = str(relative).replace("\\", "/").lstrip("/")
    return f"{VIDEOS_REF_PREFIX}/{rel}" if rel else VIDEOS_REF_PREFIX


def resolve_ref_to_path(ref: str | None) -> Path | None:
    """Map a logical repo ref to a filesystem path under vault or legacy tree."""
    if not ref:
        return None
    clean = str(ref).strip().replace("\\", "/")
    if clean.startswith(("http://", "https://")):
        return None
    base, _, _anchor = clean.partition("#")
    if base.startswith(LETTERS_REF_PREFIX + "/") or base == LETTERS_REF_PREFIX:
        suffix = base[len(LETTERS_REF_PREFIX) :].lstrip("/")
        return letters_root() / suffix if suffix else letters_root()
    if base.startswith(WISDOM_REF_PREFIX + "/") or base == WISDOM_REF_PREFIX:
        suffix = base[len(WISDOM_REF_PREFIX) :].lstrip("/")
        return wisdom_root() / suffix if suffix else wisdom_root()
    if base.startswith(SUMZERO_REF_PREFIX + "/") or base == SUMZERO_REF_PREFIX:
        suffix = base[len(SUMZERO_REF_PREFIX) :].lstrip("/")
        return sumzero_root() / suffix if suffix else sumzero_root()
    if base.startswith(PODCASTS_REF_PREFIX + "/") or base == PODCASTS_REF_PREFIX:
        suffix = base[len(PODCASTS_REF_PREFIX) :].lstrip("/")
        # Config JSON lives in-repo under PODCASTS_REF_PREFIX; episode corpus is vault.
        config_candidate = ROOT / base
        if config_candidate.exists():
            return config_candidate
        return podcasts_root() / suffix if suffix else podcasts_root()
    if base.startswith(VIDEOS_REF_PREFIX + "/") or base == VIDEOS_REF_PREFIX:
        suffix = base[len(VIDEOS_REF_PREFIX) :].lstrip("/")
        config_candidate = ROOT / base
        if config_candidate.exists():
            return config_candidate
        return videos_root() / suffix if suffix else videos_root()
    candidate = ROOT / base
    return candidate if candidate.exists() else None


def path_to_letters_ref(path: Path) -> str | None:
    """Best-effort map from a filesystem path to the stable letters ref prefix."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for root in (letters_root(), LEGACY_LETTERS):
        try:
            rel = resolved.relative_to(root.resolve())
            return letters_ref(rel.as_posix())
        except ValueError:
            continue
    return None


def require_vault() -> Path:
    root = research_vault_root()
    if root is None:
        raise RuntimeError(
            "Research vault not found. Clone magis-capital-partners/research-vault "
            "to ../research-vault or set RESEARCH_VAULT_ROOT."
        )
    return root


def path_to_podcasts_ref(path: Path) -> str | None:
    """Best-effort map from a filesystem path to the stable podcasts ref prefix."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for root in (podcasts_root(), LEGACY_PODCASTS):
        try:
            rel = resolved.relative_to(root.resolve())
            return podcasts_ref(rel.as_posix())
        except ValueError:
            continue
    return None


def path_to_videos_ref(path: Path) -> str | None:
    """Map a video-vault path to the stable logical video reference."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for root in (videos_root(), LEGACY_VIDEOS):
        try:
            rel = resolved.relative_to(root.resolve())
            return videos_ref(rel.as_posix())
        except ValueError:
            continue
    return None


def vault_status() -> dict:
    """Diagnostic summary for setup scripts and CI smoke tests."""
    vault = research_vault_root()
    letters = letters_root()
    podcasts = podcasts_root()
    return {
        "research_vault_root": str(vault) if vault else None,
        "letters_root": str(letters),
        "letters_exists": letters.is_dir(),
        "wisdom_root": str(wisdom_root()),
        "wisdom_exists": wisdom_root().is_dir(),
        "podcasts_root": str(podcasts),
        "podcasts_exists": podcasts.is_dir(),
        "using_vault": vault is not None and str(letters).startswith(str(vault)),
        "env_research_vault_root": os.environ.get("RESEARCH_VAULT_ROOT"),
    }
