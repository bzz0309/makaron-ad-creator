from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from makaron_ad_creator.util import AdCreatorError, download, run


class UtilTests(unittest.TestCase):
    def test_run_can_preserve_nonzero_stdout_when_check_is_disabled(self) -> None:
        failed = SimpleNamespace(stdout='{"status":"failed","result":{"designs":[]}}', stderr="", returncode=1)
        with patch("makaron_ad_creator.util.subprocess.run", return_value=failed):
            result = run(["makaron", "responses", "get", "run-1"], check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn('"status":"failed"', result.stdout)
            with self.assertRaisesRegex(AdCreatorError, "Command failed"):
                run(["makaron", "responses", "get", "run-1"])

    def test_download_prefers_curl_and_atomically_moves_nonempty_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            destination = Path(temp_name) / "assets" / "artifact.mp4"

            def fake_run(command: list[str], **_: object) -> SimpleNamespace:
                output = Path(command[command.index("--output") + 1])
                output.write_bytes(b"generated-media")
                return SimpleNamespace(stdout="", stderr="", returncode=0)

            with patch("makaron_ad_creator.util.shutil.which", return_value="/usr/bin/curl"), \
                 patch("makaron_ad_creator.util.run", side_effect=fake_run) as mocked_run:
                result = download("https://example.com/artifact.mp4", destination)

            self.assertEqual(result, destination)
            self.assertEqual(destination.read_bytes(), b"generated-media")
            command = mocked_run.call_args.args[0]
            self.assertIn("--retry", command)
            self.assertIn("--fail", command)
            self.assertIn("--http1.1", command)


if __name__ == "__main__":
    unittest.main()
