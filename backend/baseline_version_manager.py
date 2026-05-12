"""
Baseline Version Manager
========================

Manages versioned baseline CSV snapshots with timestamp directories.
Each upload creates a new version; symlinks point to the active version.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger

TZ_TAIPEI = timezone(timedelta(hours=8))

MAX_VERSIONS = 5

BASE_DIR = Path(__file__).resolve().parent.parent
HANDOFF_DATA = BASE_DIR / "handoff" / "data"
VERSIONS_DIR = HANDOFF_DATA / "versions"
CURRENT_LINK = HANDOFF_DATA / "current"

PRECISE_NAME = "search_keyword_precise.csv"
BROAD_NAME = "search_keyword_broad.csv"


class BaselineVersionManager:
    def __init__(self):
        VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

    def create_version(self, precise_csv: str | None, broad_csv: str | None,
                       source_filename: str = "") -> dict:
        """
        Create a new version directory with the given CSV content.
        Returns version metadata dict.
        """
        ts = datetime.now(TZ_TAIPEI).strftime("%Y%m%d_%H%M%S")
        version_dir = VERSIONS_DIR / ts
        version_dir.mkdir(parents=True, exist_ok=True)

        # Copy existing files for the type not being uploaded
        if precise_csv is not None:
            (version_dir / PRECISE_NAME).write_text(precise_csv, encoding="utf-8")
        else:
            existing = self._resolve_current_file(PRECISE_NAME)
            if existing:
                shutil.copy2(existing, version_dir / PRECISE_NAME)

        if broad_csv is not None:
            (version_dir / BROAD_NAME).write_text(broad_csv, encoding="utf-8")
        else:
            existing = self._resolve_current_file(BROAD_NAME)
            if existing:
                shutil.copy2(existing, version_dir / BROAD_NAME)

        # Count keywords
        precise_count = self._count_csv_rows(version_dir / PRECISE_NAME)
        broad_count = self._count_csv_rows(version_dir / BROAD_NAME)

        meta = {
            "timestamp": ts,
            "created_at": datetime.now(TZ_TAIPEI).isoformat(),
            "source": source_filename,
            "precise_keywords": precise_count,
            "broad_keywords": broad_count,
        }
        (version_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        self._activate(ts)
        self._cleanup()

        logger.info(f"[Baseline] Created version {ts}: precise={precise_count}, broad={broad_count}")
        return meta

    def activate(self, timestamp: str) -> dict | None:
        """Switch active version to the given timestamp. Returns meta or None."""
        version_dir = VERSIONS_DIR / timestamp
        if not version_dir.is_dir():
            return None
        self._activate(timestamp)
        meta = self._read_meta(version_dir)
        logger.info(f"[Baseline] Activated version {timestamp}")
        return meta

    def archive(self, timestamp: str) -> bool:
        """Archive a version by renaming its directory with _archived suffix."""
        version_dir = VERSIONS_DIR / timestamp
        if not version_dir.is_dir():
            return False
        if self._is_active(timestamp):
            return False  # cannot archive active version
        archived_dir = VERSIONS_DIR / f"{timestamp}_archived"
        version_dir.rename(archived_dir)
        logger.info(f"[Baseline] Archived version {timestamp}")
        return True

    def list_versions(self) -> list[dict]:
        """List all non-archived versions sorted by timestamp descending."""
        versions = []
        if not VERSIONS_DIR.exists():
            return versions
        for d in sorted(VERSIONS_DIR.iterdir(), reverse=True):
            if not d.is_dir() or d.name.endswith("_archived"):
                continue
            meta = self._read_meta(d)
            if meta:
                meta["is_active"] = self._is_active(d.name)
                versions.append(meta)
        return versions

    def get_active_version(self) -> dict | None:
        """Return metadata of the currently active version."""
        if CURRENT_LINK.is_symlink() or CURRENT_LINK.is_dir():
            target = CURRENT_LINK.resolve()
            meta = self._read_meta(target)
            if meta:
                meta["is_active"] = True
            return meta
        return None

    # ── Internal ──────────────────────────────────────────────────────────

    def _activate(self, timestamp: str):
        """Update symlinks to point to the given version."""
        version_dir = VERSIONS_DIR / timestamp

        # Update current symlink
        if CURRENT_LINK.is_symlink() or CURRENT_LINK.exists():
            CURRENT_LINK.unlink()
        CURRENT_LINK.symlink_to(f"./versions/{timestamp}", target_is_directory=True)

        # Update root-level CSV symlinks for backward compatibility
        for name in (PRECISE_NAME, BROAD_NAME):
            src = version_dir / name
            dst = HANDOFF_DATA / name
            if src.exists():
                if dst.is_symlink() or dst.exists():
                    dst.unlink()
                dst.symlink_to(f"./versions/{timestamp}/{name}")

    def _is_active(self, timestamp: str) -> bool:
        if not CURRENT_LINK.is_symlink():
            return False
        try:
            target = CURRENT_LINK.resolve()
            return target.name == timestamp
        except Exception:
            return False

    def _resolve_current_file(self, filename: str) -> Path | None:
        """Get the path to a file in the currently active version."""
        # Try current symlink first
        f = CURRENT_LINK / filename
        if f.exists():
            return f
        # Fallback to root-level file
        f = HANDOFF_DATA / filename
        if f.exists() and not f.is_symlink():
            return f
        return None

    def _cleanup(self):
        """Archive oldest non-archived versions beyond MAX_VERSIONS."""
        if not VERSIONS_DIR.exists():
            return
        dirs = sorted(
            [d for d in VERSIONS_DIR.iterdir() if d.is_dir() and not d.name.endswith("_archived")],
            key=lambda d: d.name,
            reverse=True,
        )
        for old in dirs[MAX_VERSIONS:]:
            archived = VERSIONS_DIR / f"{old.name}_archived"
            old.rename(archived)
            logger.info(f"[Baseline] Auto-archived old version {old.name}")

    @staticmethod
    def _count_csv_rows(path: Path) -> int:
        if not path.exists():
            return 0
        try:
            lines = path.read_text(encoding="utf-8").strip().split("\n")
            return max(0, len(lines) - 1)  # subtract header
        except Exception:
            return 0

    @staticmethod
    def _read_meta(version_dir: Path) -> dict | None:
        meta_path = version_dir / "meta.json"
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None


# Migrate existing root-level CSVs into a version if no versions exist yet
def _migrate_existing():
    mgr = BaselineVersionManager()
    if list(VERSIONS_DIR.iterdir()) if VERSIONS_DIR.exists() else []:
        return mgr  # versions already exist

    precise = HANDOFF_DATA / PRECISE_NAME
    broad = HANDOFF_DATA / BROAD_NAME
    if not precise.exists() and not broad.exists():
        return mgr  # nothing to migrate

    p_text = precise.read_text(encoding="utf-8") if precise.exists() and not precise.is_symlink() else None
    b_text = broad.read_text(encoding="utf-8") if broad.exists() and not broad.is_symlink() else None

    if p_text or b_text:
        mgr.create_version(p_text, b_text, source_filename="migrated_from_existing")
        logger.info("[Baseline] Migrated existing CSVs into versioned format")

    return mgr


baseline_version_manager = _migrate_existing()
