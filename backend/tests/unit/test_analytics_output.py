"""Unit tests for utils/analytics_output.py."""

import json
import tempfile
import unittest
from pathlib import Path

from utils.analytics_output import write_outputs


class TestWriteOutputs(unittest.TestCase):
    def test_writes_compact_json_and_reports_sizes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "nested"
            sizes = write_outputs({"metadata": {"a": 1}}, output_dir)
            written = (output_dir / "metadata.json").read_text(encoding="utf-8")
            self.assertEqual(written, '{"a":1}')
            self.assertEqual(json.loads(written), {"a": 1})
            self.assertEqual(sizes, {"metadata.json": len(written)})
