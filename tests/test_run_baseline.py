import os
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import pandas as pd
import yaml

from run_baseline import Run
from validation_state import add_review_rows, fill_labels, validation_directory


class RunBaselineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config_path = self.root / "config" / "sector.yaml"
        self.config_path.parent.mkdir()
        template = Path(__file__).resolve().parents[1] / "config" / "sector.yaml"
        self.config = yaml.safe_load(template.read_text())
        self.config["env"] = "TEST"
        self.config["paths"]["run_root"] = "outputs/runs"
        self.write_config()
        env = patch.dict(os.environ, PATENT_RUN_ID="trial-01")
        env.start()
        self.addCleanup(env.stop)

    def write_config(self):
        self.config_path.write_text(yaml.safe_dump(self.config))

    def test_run_requires_an_explicit_safe_id(self):
        del os.environ["PATENT_RUN_ID"]
        with self.assertRaises(ValueError):
            Run.open(self.root)
        with patch.dict(os.environ, PATENT_RUN_ID="../another-run"), self.assertRaises(ValueError):
            Run.open(self.root)

    def test_inputs_recorded_and_verified_after_reopening(self):
        run = Run.open(self.root)
        run.publish("raw.csv", lambda p: p.write_bytes(b"one"))
        run.publish("derived.csv", lambda p: p.write_bytes(b"two"), inputs=("raw.csv",))
        reopened = Run.open(self.root)
        reopened.verify("derived.csv")
        self.assertEqual(
            reopened.receipt("derived.csv")["inputs"]["raw.csv"],
            reopened.receipt("raw.csv")["sha256"],
        )
        reopened.path("raw.csv").write_bytes(b"six")
        with self.assertRaises(ValueError):
            reopened.verify("raw.csv")
        with self.assertRaises(ValueError):
            reopened.verify("derived.csv")

    def test_upstream_from_another_run_is_rejected_even_with_identical_bytes(self):
        original = Run.open(self.root)
        original.publish("raw.csv", lambda p: p.write_bytes(b"one"))
        original.publish("derived.csv", lambda p: p.write_bytes(b"two"), inputs=("raw.csv",))
        with patch.dict(os.environ, PATENT_RUN_ID="trial-02"):
            other = Run.open(self.root)
            other.publish("raw.csv", lambda p: p.write_bytes(b"one"))
        for name in ("raw.csv", "raw.csv.receipt.json"):
            shutil.copyfile(other.directory / name, original.directory / name)
        with self.assertRaises(ValueError):
            original.verify("derived.csv")

    def test_configuration_drift_requires_a_new_run(self):
        run = Run.open(self.root)
        run.publish("raw.csv", lambda p: p.write_bytes(b"one"))
        self.config["years"]["min"] += 1
        self.write_config()
        with self.assertRaises(ValueError):
            Run.open(self.root)
        with self.assertRaises(ValueError):
            run.verify("raw.csv")

    def test_test_data_is_unavailable_in_prod(self):
        test_run = Run.open(self.root)
        test_run.publish("raw.csv", lambda p: p.write_bytes(b"test data"))
        self.config["env"] = "PROD"
        self.write_config()
        prod_run = Run.open(self.root)
        self.assertNotEqual(test_run.path("raw.csv"), prod_run.path("raw.csv"))
        with self.assertRaises((FileNotFoundError, ValueError)):
            prod_run.verify("raw.csv")

    def test_duplicate_publication_preserves_original(self):
        run = Run.open(self.root)
        run.publish("raw.csv", lambda p: p.write_bytes(b"one"))
        original = run.receipt("raw.csv")
        before = run.path("raw.csv").stat()
        run.publish("raw.csv", lambda p: p.write_bytes(b"one"))
        after = run.path("raw.csv").stat()
        self.assertEqual((before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns))
        with self.assertRaises(FileExistsError):
            run.publish("raw.csv", lambda p: p.write_bytes(b"two"))
        with self.assertRaises(FileExistsError):
            run.publish("raw.csv", lambda p: p.write_bytes(b"one"), metadata={"edition": "other"})
        self.assertEqual(run.path("raw.csv").read_bytes(), b"one")
        self.assertEqual(run.receipt("raw.csv"), original)

    def test_failed_writer_allows_clean_retry(self):
        run = Run.open(self.root)

        def interrupted(path):
            path.write_bytes(b"partial")
            raise RuntimeError("interrupted")

        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            run.publish("raw.csv", interrupted)
        self.assertFalse(run.path("raw.csv").exists())
        run.publish("raw.csv", lambda p: p.write_bytes(b"complete"))
        run.verify("raw.csv")
        self.assertEqual(run.path("raw.csv").read_bytes(), b"complete")

    def test_historical_labels_are_seeded_only_for_their_workflow(self):
        evidence = self.root / "Step0" / "validation"
        evidence.mkdir(parents=True)
        original = b"docdb_family_id,human_label\n1,pertinente\n"
        (evidence / "hand_check.csv").write_bytes(original)
        (evidence / "llm_cache.jsonl").write_bytes(b"")
        test_run = Run.open(self.root)
        working = validation_directory(test_run) / "hand_check.csv"
        self.assertEqual(working.read_bytes(), original)
        working.write_bytes(original.replace(b"pertinente", b"non_pertinente"))
        validation_directory(test_run)
        self.assertNotEqual(working.read_bytes(), original)
        self.assertEqual(test_run.verify("validation/seeds/hand_check.csv").read_bytes(), original)
        self.assertEqual((evidence / "hand_check.csv").read_bytes(), original)

        self.config["env"] = "PROD"
        self.write_config()
        prod_dir = validation_directory(Run.open(self.root))
        self.assertFalse((prod_dir / "hand_check.csv").exists())

    def test_repeated_review_preserves_manual_decision(self):
        path = self.root / "review.csv"
        families = pd.DataFrame({"docdb_family_id": [10, 20], "human_label": ["", ""]})
        add_review_rows(path, families)
        fill_labels(path, {10: "pertinente"})
        add_review_rows(path, families)
        fill_labels(path, {20: "non_pertinente"})
        result = pd.read_csv(path).set_index("docdb_family_id")
        self.assertEqual(result["human_label"].to_dict(), {10: "pertinente", 20: "non_pertinente"})

    def test_two_publishers_cannot_overwrite_each_other(self):
        run = Run.open(self.root)
        start = Barrier(2)

        def publish(value):
            start.wait(timeout=5)
            try:
                run.publish("raw.csv", lambda p: p.write_bytes(value))
            except FileExistsError:
                return None
            return value

        with ThreadPoolExecutor(max_workers=2) as pool:
            winners = [value for value in pool.map(publish, [b"one", b"two"]) if value]
        self.assertEqual(len(winners), 1)
        run.verify("raw.csv")
        self.assertEqual(run.path("raw.csv").read_bytes(), winners[0])
