import argparse
import importlib.util
import io
import json
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

    def test_static_templates_match_cli(self):
        vast = load("vast_training")
        for profile in ("qlora", "lora", "full"):
            output = io.StringIO()
            with (
                patch(
                    "sys.argv", ["vast_training.py", "template", "--profile", profile]
                ),
                patch("sys.stdout", output),
            ):
                self.assertEqual(vast.main(), 0)
            saved = json.loads((ROOT / "templates" / (profile + ".json")).read_text())
            self.assertEqual(json.loads(output.getvalue()), saved)

    def test_execute_requires_cli_and_propagates_failure_without_shell(self):
        vast = load("vast_training")
        with (
            patch("sys.argv", ["vast_training.py", "offers", "--execute"]),
            patch.object(vast.shutil, "which", return_value=None),
            patch.object(vast.subprocess, "run") as execute,
        ):
            with self.assertRaises(SystemExit) as error:
                vast.main()
            self.assertEqual(error.exception.code, 2)
            execute.assert_not_called()
        with (
            patch(
                "sys.argv",
                ["vast_training.py", "create", "--offer", "123", "--execute"],
            ),
            patch.object(vast.shutil, "which", return_value="/cli/vastai"),
            patch.object(
                vast.subprocess, "run", return_value=argparse.Namespace(returncode=3)
            ) as execute,
        ):
            self.assertEqual(vast.main(), 3)
            self.assertIsInstance(execute.call_args.args[0], list)
            self.assertNotIn("shell", execute.call_args.kwargs)

    def test_stack_is_shared_by_doctor_and_offer_filters(self):
        vast = load("vast_training")
        doctor = load("doctor")
        config = vast.stack()
        self.assertEqual(
            doctor.version_errors(config, (3, 12), "2.13.0", "13.0", ["580.1"]), []
        )
        errors = doctor.version_errors(config, (3, 11), "2.12.0", "12.0", ["579.1"])
        self.assertEqual(len(errors), 3)
        changed = dict(config, cuda="14.0", minimum_driver_major=600)
        with patch.object(vast, "stack", return_value=changed):
            query = vast.offer_query(config["profiles"]["qlora"], 1)
        self.assertIn("cuda_vers>=14.0", query)
        self.assertIn("driver_version>=600000000", query)

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
