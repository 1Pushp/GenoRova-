from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENOROVA_OUTPUTS = ROOT / "genorova" / "outputs"
MOLECULE_DB_PATH = GENOROVA_OUTPUTS / "genorova_memory.db"
GENERATED_DIR = GENOROVA_OUTPUTS / "generated"
REPORT_PATH = GENOROVA_OUTPUTS / "genorova_report.html"
BACKUP_ROOT = ROOT / "backups"
MANIFEST_NAME = "manifest.json"


def _utc_now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _default_auth_db_path() -> Path:
    override = os.getenv("GENOROVA_AUTH_DB_PATH", "").strip()
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        localappdata = os.getenv("LOCALAPPDATA", "").strip()
        if localappdata:
            return Path(localappdata) / "GenorovaAI" / "genorova_auth.db"

    return Path(tempfile.gettempdir()) / "GenorovaAI" / "genorova_auth.db"


def _chat_storage_candidates() -> list[Path]:
    candidates: list[Path] = []
    override = os.getenv("CHAT_MEMORY_DB_PATH", "").strip()
    if override:
        candidates.append(Path(override).expanduser())

    if os.name == "nt":
        localappdata = os.getenv("LOCALAPPDATA", "").strip()
        if localappdata:
            candidates.append(Path(localappdata) / "GenorovaAI" / "chat_memory.db")

    candidates.append(ROOT / "runtime" / "chat_memory.db")
    candidates.append(Path(tempfile.gettempdir()) / "GenorovaAI" / "chat_memory.db")
    return candidates


def _existing_chat_db_path() -> Path | None:
    seen: set[str] = set()
    for candidate in _chat_storage_candidates():
        normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate.exists():
            return candidate
    return None


def _sqlite_sidecars(path: Path) -> list[Path]:
    return [
        path,
        path.with_name(path.name + "-wal"),
        path.with_name(path.name + "-shm"),
        path.with_name(path.name + "-journal"),
    ]


def _copy_file_bundle(label: str, source_path: Path, destination_root: Path, manifest_items: list[dict]) -> None:
    source_path = source_path.expanduser()
    if not source_path.exists():
        manifest_items.append(
            {
                "label": label,
                "kind": "file_bundle",
                "source": str(source_path),
                "backup_dir": None,
                "copied_files": [],
                "status": "missing",
            }
        )
        return

    bundle_dir = destination_root / label
    bundle_dir.mkdir(parents=True, exist_ok=True)
    copied_files: list[dict[str, str]] = []

    for artifact in _sqlite_sidecars(source_path):
        if not artifact.exists():
            continue
        destination = bundle_dir / artifact.name
        shutil.copy2(artifact, destination)
        copied_files.append(
            {
                "source": str(artifact),
                "backup": str(destination),
                "name": artifact.name,
            }
        )

    manifest_items.append(
        {
            "label": label,
            "kind": "file_bundle",
            "source": str(source_path),
            "backup_dir": str(bundle_dir),
            "copied_files": copied_files,
            "status": "copied" if copied_files else "missing",
        }
    )


def _copy_directory(label: str, source_dir: Path, destination_root: Path, manifest_items: list[dict]) -> None:
    source_dir = source_dir.expanduser()
    if not source_dir.exists():
        manifest_items.append(
            {
                "label": label,
                "kind": "directory",
                "source": str(source_dir),
                "backup_dir": None,
                "status": "missing",
            }
        )
        return

    bundle_dir = destination_root / label
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    shutil.copytree(source_dir, bundle_dir)
    manifest_items.append(
        {
            "label": label,
            "kind": "directory",
            "source": str(source_dir),
            "backup_dir": str(bundle_dir),
            "status": "copied",
        }
    )


def backup(output_dir: Path | None = None) -> Path:
    backup_root = (output_dir or BACKUP_ROOT).expanduser()
    backup_root.mkdir(parents=True, exist_ok=True)
    bundle_root = backup_root / f"genorova_runtime_backup_{_utc_now_stamp()}"
    bundle_root.mkdir(parents=True, exist_ok=True)

    manifest_items: list[dict] = []

    _copy_file_bundle("auth_db", _default_auth_db_path(), bundle_root, manifest_items)
    _copy_file_bundle("molecule_db", MOLECULE_DB_PATH, bundle_root, manifest_items)
    chat_db_path = _existing_chat_db_path()
    if chat_db_path is not None:
        _copy_file_bundle("chat_memory_db", chat_db_path, bundle_root, manifest_items)
    else:
        manifest_items.append(
            {
                "label": "chat_memory_db",
                "kind": "file_bundle",
                "source": None,
                "backup_dir": None,
                "copied_files": [],
                "status": "not_applicable",
                "note": "The active src.api chat session store is process memory only and cannot be backed up.",
            }
        )

    _copy_directory("generated_outputs", GENERATED_DIR, bundle_root, manifest_items)
    _copy_file_bundle("html_report", REPORT_PATH, bundle_root, manifest_items)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "bundle_root": str(bundle_root),
        "items": manifest_items,
        "notes": [
            "The live src.api chat-session store is in process memory only and does not survive restart.",
            "SQLite sidecar files (-wal, -shm, -journal) are copied when present.",
        ],
    }

    manifest_path = bundle_root / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Backup created: {bundle_root}")
    print(f"Manifest: {manifest_path}")
    return manifest_path


def restore(manifest_path: Path, force: bool = False) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest.get("items", []):
        if item.get("status") not in {"copied"}:
            continue

        if item.get("kind") == "directory":
            source_dir = Path(item["source"])
            backup_dir = Path(item["backup_dir"])
            if source_dir.exists() and any(source_dir.iterdir()) and not force:
                raise RuntimeError(
                    f"Refusing to overwrite populated directory without --force: {source_dir}"
                )
            source_dir.parent.mkdir(parents=True, exist_ok=True)
            if source_dir.exists():
                shutil.rmtree(source_dir)
            shutil.copytree(backup_dir, source_dir)
            print(f"Restored directory: {source_dir}")
            continue

        if item.get("kind") == "file_bundle":
            source_path = item.get("source")
            if not source_path:
                continue
            source_root = Path(source_path)
            source_root.parent.mkdir(parents=True, exist_ok=True)
            for copied in item.get("copied_files", []):
                destination = source_root.parent / copied["name"]
                if destination.exists() and not force:
                    raise RuntimeError(
                        f"Refusing to overwrite existing file without --force: {destination}"
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(copied["backup"], destination)
                print(f"Restored file: {destination}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup or restore Genorova runtime state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="Create a timestamped runtime backup bundle.")
    backup_parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKUP_ROOT,
        help="Directory where backup bundles should be stored.",
    )

    restore_parser = subparsers.add_parser("restore", help="Restore from a backup manifest.")
    restore_parser.add_argument("manifest", type=Path, help="Path to a backup manifest.json file.")
    restore_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting existing files and directories.",
    )

    args = parser.parse_args()

    if args.command == "backup":
        backup(args.output_dir)
        return 0

    restore(args.manifest, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
