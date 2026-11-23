"""Run-scoped working files for the Step 0 notebook review process."""

import hashlib
import json
import os
import shutil
from contextlib import contextmanager
from fcntl import LOCK_EX, flock
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd


@contextmanager
def _locked(path):
    # Review files and the JSONL cache are shared by kernels using the same run.
    with path.with_suffix(path.suffix + ".lock").open("a") as lock:
        flock(lock, LOCK_EX)
        yield


def _replace(path, content):
    with NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        scratch = Path(temp.name)
        try:
            temp.write(content)
            temp.flush()
            os.fsync(temp.fileno())
            os.replace(scratch, path)
        finally:
            scratch.unlink(missing_ok=True)


def validation_directory(run):
    """Seed only working inputs, leaving historical reports in the checkout."""
    directory = run.path("validation")
    directory.mkdir(parents=True, exist_ok=True)
    source = run.root / "Step0" / "validation"
    seeds = [source / "llm_cache.jsonl"]
    if run.env == "TEST":
        seeds.append(source / "hand_check.csv")
        seeds.extend(path for path in sorted(source.glob("review_*.csv")) if "_prod_" not in path.name)
    for seed in seeds:
        if not seed.is_file():
            continue
        # Keep the seeds' original identities distinct from this run's mutable copies.
        snapshot = run.publish(
            f"validation/seeds/{seed.name}", lambda path: shutil.copyfile(seed, path),
            metadata={"historical_source": str(seed.relative_to(run.root))},
        )
        target = run.path(f"validation/{seed.name}")
        with _locked(target):
            if not target.exists():
                _replace(target, snapshot.read_bytes())
    return directory


def input_fingerprints(*paths):
    """Record the bytes of mutable cache/review inputs used by a published report."""
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths if path.is_file()}


def store_answer(path, answer):
    """Persist a complete response and reuse an existing record for this key."""
    with _locked(path):
        content = path.read_bytes() if path.exists() else b""
        for line in content.splitlines():
            if line.strip():
                old = json.loads(line)
                if (old["docdb_family_id"], old["prompt_id"]) == (answer["docdb_family_id"], answer["prompt_id"]):
                    return old
        if content and not content.endswith(b"\n"):
            content += b"\n"
        _replace(path, content + (json.dumps(answer, ensure_ascii=False) + "\n").encode())
    return answer


def add_review_rows(path, rows):
    """Add unseen families without replacing any existing manual review rows."""
    with _locked(path):
        if path.exists():
            current = pd.read_csv(path, keep_default_na=False)
            rows = rows.loc[~rows["docdb_family_id"].isin(current["docdb_family_id"])]
            if rows.empty:
                return
            rows = pd.concat([current, rows], ignore_index=True)
        _replace(path, rows.to_csv(index=False).encode())


def fill_labels(path, labels):
    """Fill empty slots only. Existing decisions, including manual edits, win."""
    with _locked(path):
        rows = pd.read_csv(path, keep_default_na=False)
        new = rows["docdb_family_id"].map(labels)
        update = new.notna() & rows["human_label"].astype(str).str.strip().eq("")
        if update.any():
            rows.loc[update, "human_label"] = new.loc[update]
            _replace(path, rows.to_csv(index=False).encode())
        return rows
