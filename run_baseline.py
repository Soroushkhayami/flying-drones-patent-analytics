"""Run-scoped files and SHA-256 lineage for the PATSTAT notebooks (Linux/TIP)."""

import fcntl
import hashlib
import json
import os
import re
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml


def _digest(path):
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        return digest.hexdigest()


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _git_state(root):
    try:
        def git(*args):
            return subprocess.check_output(
                ["git", "--no-optional-locks", "-C", str(root), *args],
                text=True, stderr=subprocess.DEVNULL,
            ).strip()

        return {"git_commit": git("rev-parse", "--verify", "HEAD"),
                "git_dirty": bool(git("status", "--porcelain"))}
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {"git_commit": None, "git_dirty": None}


def _write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def _load_json(path):
    if path.is_symlink():
        raise ValueError(f"Refusing symlink at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def _publish_lock(directory):
    # Serialize commits across notebook kernels. The OS releases the lock on exit.
    with (directory / ".publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


class Run:
    def __init__(self, root, cfg, run_id, directory, config_sha256):
        self.root = root
        self.cfg = cfg
        self.env = cfg["env"]
        self.run_id = run_id
        self.directory = directory
        self.config_sha256 = config_sha256

    @classmethod
    def open(cls, root):
        root = Path(root).resolve(strict=True)
        config_path = root / "config" / "sector.yaml"
        raw_config = config_path.read_bytes()
        cfg = yaml.safe_load(raw_config)
        if cfg["env"] not in ("TEST", "PROD"):
            raise ValueError("config/sector.yaml env must be TEST or PROD")
        run_id = os.environ.get("PATENT_RUN_ID", "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
            raise ValueError("Set PATENT_RUN_ID to a run name of 1–128 letters, digits, dots, hyphens or underscores, starting with a letter or digit.")

        base = (root / cfg["paths"]["run_root"]).resolve()
        directory = base / cfg["env"] / run_id
        if directory.resolve() != directory:
            raise ValueError(f"Run directory crosses a symlink: {directory}")
        directory.mkdir(parents=True, exist_ok=True)
        run = cls(root, cfg, run_id, directory, hashlib.sha256(raw_config).hexdigest())
        manifest = directory / "run.json"
        with _publish_lock(directory):
            if manifest.is_symlink():
                raise ValueError(f"Refusing symlink at {manifest}")
            if not manifest.exists():
                if any(p.name != ".publish.lock" for p in directory.iterdir()):
                    raise ValueError(f"Refusing to adopt files in a run without run.json: {directory}")
                with TemporaryDirectory(dir=directory.parent, prefix=".initialize-") as tmp:
                    staged = Path(tmp) / "run.json"
                    _write_json(staged, {
                        **run._identity(), "config": cfg, "created_utc": _utc_now(),
                        **_git_state(root),
                    })
                    os.link(staged, manifest)
            run._check_identity()
        return run

    def _identity(self):
        return {
            "env": self.env,
            "run_id": self.run_id,
            "config_sha256": self.config_sha256,
            "patstat_edition": self.cfg.get("patstat_edition"),
        }

    def _check_identity(self):
        saved = _load_json(self.directory / "run.json")
        if (any(saved.get(k) != v for k, v in self._identity().items())
                or saved.get("config") != self.cfg
                or _digest(self.root / "config" / "sector.yaml") != self.config_sha256):
            raise ValueError(f"Run configuration mismatch for {self.directory}. Use a new run ID for changed settings.")

    def path(self, relative):
        rel = Path(relative)
        if (rel.is_absolute() or not rel.parts or any(p.startswith(".") for p in rel.parts)
                or rel.parts[0] == "run.json" or any(p.endswith(".receipt.json") for p in rel.parts)):
            raise ValueError(f"Expected a relative artifact path within the run: {relative}")
        path = self.directory / rel
        if path.resolve() != path:
            raise ValueError(f"Artifact path crosses a symlink: {path}")
        return path

    @staticmethod
    def _receipt_path(path):
        return path.with_name(path.name + ".receipt.json")

    def _verified_receipt(self, relative, checked, active):
        path = self.path(relative)
        key = path.relative_to(self.directory).as_posix()
        if key in checked:
            return checked[key]
        if key in active:
            raise ValueError(f"Circular input lineage at {key}")
        receipt = _load_json(self._receipt_path(path))
        if (receipt.get("path") != key
                or any(receipt.get(k) != v for k, v in self._identity().items())
                or path.stat().st_size != receipt.get("size_bytes")
                or _digest(path) != receipt.get("sha256")):
            raise ValueError(f"Artifact identity or content mismatch: {key}")
        dependencies = receipt["inputs"]
        if not isinstance(dependencies, dict):
            raise ValueError(f"Invalid input manifest for {key}")
        active.add(key)
        for parent, expected in dependencies.items():
            if self._verified_receipt(parent, checked, active)["sha256"] != expected:
                raise ValueError(f"Input fingerprint mismatch for {parent} in {key}")
        active.remove(key)
        checked[key] = receipt
        return receipt

    def receipt(self, relative):
        """Verify the artifact and all its recorded ancestors, then return its receipt."""
        self._check_identity()
        return self._verified_receipt(relative, {}, set())

    def verify(self, relative):
        self.receipt(relative)
        return self.path(relative)

    def publish(self, relative, writer, inputs=(), metadata=None):
        """Stage a file, record verified inputs and expose the completed file once."""
        self._check_identity()
        path = self.path(relative)
        key = path.relative_to(self.directory).as_posix()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Preserve the extension for writers that infer their output format from it.
        with TemporaryDirectory(dir=path.parent, prefix=".stage-") as tmp:
            staged = Path(tmp) / path.name
            writer(staged)
            if not staged.is_file() or staged.is_symlink():
                raise ValueError(f"Writer did not create a regular file for {key}")
            receipt_path = self._receipt_path(path)
            with _publish_lock(self.directory):
                self._check_identity()
                checked = {}
                parents = {}
                for parent in inputs:
                    parent_key = self.path(parent).relative_to(self.directory).as_posix()
                    parents[parent_key] = self._verified_receipt(parent_key, checked, {key})["sha256"]
                record = {
                    **self._identity(), "path": key, "sha256": _digest(staged),
                    "size_bytes": staged.stat().st_size, "inputs": parents,
                    "metadata": json.loads(json.dumps(metadata or {}, allow_nan=False)),
                }
                if path.exists():
                    existing = self._verified_receipt(key, checked, set())
                    if any(existing.get(k) != v for k, v in record.items()):
                        raise FileExistsError(f"Refusing to change published artifact: {path}")
                    return path
                if receipt_path.exists():
                    # A process can die between the two links. Only finish that exact publication.
                    existing = _load_json(receipt_path)
                    if any(existing.get(k) != v for k, v in record.items()):
                        raise ValueError(f"An interrupted publication has different content for {key}. Use a new run ID.")
                else:
                    staged_receipt = Path(tmp) / receipt_path.name
                    _write_json(staged_receipt, {
                        **record, "created_utc": _utc_now(), **_git_state(self.root),
                    })
                    os.link(staged_receipt, receipt_path)
                # The file itself is the commit point. A reader never sees a partial file.
                os.link(staged, path)
        return path
