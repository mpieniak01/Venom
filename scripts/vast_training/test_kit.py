import argparse
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KitTests(unittest.TestCase):
    def test_modes_and_model_revision(self):
        config = load("configure")
        with tempfile.TemporaryDirectory() as folder:
            dataset = Path(folder) / "train.jsonl"
            dataset.write_text('{"text":"one"}\n{"text":"two"}\n')
            for mode in ("qlora", "lora", "full"):
                result = config.make_config(
                    mode, "test/model", "a" * 40, dataset, Path(folder) / mode
                )
                self.assertEqual(result.get("load_in_4bit", False), mode == "qlora")
                self.assertEqual("adapter" in result, mode != "full")
                self.assertFalse(result["flash_attention"])
                self.assertEqual(result["revision_of_model"], "a" * 40)
            with self.assertRaises(ValueError):
                config.make_config("lora", "test/model", "main", dataset, folder)

    def test_invalid_dataset(self):
        config = load("configure")
        with tempfile.TemporaryDirectory() as folder:
            dataset = Path(folder) / "train.jsonl"
            dataset.write_text('{"text":""}\n')
            with self.assertRaises(ValueError):
                config.make_config("qlora", "m", "a" * 40, dataset, folder)

    def test_create_is_dry_run(self):
        vast = load("vast_training")
        with (
            patch("sys.argv", ["vast_training.py", "create", "--offer", "123"]),
            patch.object(vast.subprocess, "run") as run,
        ):
            self.assertEqual(vast.main(), 0)
            run.assert_not_called()

    def test_bad_offer_and_query(self):
        vast = load("vast_training")
        with self.assertRaises(ValueError):
            vast.command(argparse.Namespace(action="create", profile="qlora", offer=0))
        for price in (-1, 0, float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                vast.offer_query(vast.stack()["profiles"]["qlora"], price)

    def test_image_and_storage(self):
        vast = load("vast_training")
        image = vast.stack()["image"]
        self.assertRegex(image, r"^axolotlai/axolotl-cloud@sha256:[0-9a-f]{64}$")
        args = argparse.Namespace(action="create", profile="full", offer=123)
        command = vast.command(args)
        self.assertIn("--ssh", command)
        self.assertNotIn("pip install", vast.startup())
        self.assertNotIn("train.sh", vast.startup())


if __name__ == "__main__":
    unittest.main()
