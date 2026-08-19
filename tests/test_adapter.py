from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from makaron_ad_creator.adapter import MakaronAdapter, extract_json_object


class AdapterTests(unittest.TestCase):
    def test_extract_json_object_accepts_selected_locale_subset(self) -> None:
        response = {"result": {"text": '{"yue":["一","二","三","四","五"]}'}}
        scripts = extract_json_object(response, ("yue",))
        self.assertEqual(scripts["yue"][0], "一")

    def test_background_text_response_is_polled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            fake = root / "fake-makaron"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "assert '--video-model' not in sys.argv\n"
                "if len(sys.argv) > 1 and sys.argv[1] == 'chat':\n"
                "    print(json.dumps({'runId':'run-1'}))\n"
                "else:\n"
                "    print(json.dumps({'text': json.dumps({'en':['e1','e2','e3','e4','e5'],'ja':['j1','j2','j3','j4','j5'],'yue':['y1','y2','y3','y4','y5']})}))\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            adapter = MakaronAdapter("project-1", root / "run", str(fake))
            result = adapter.chat(node_id="scripts", prompt="return JSON")
            scripts = extract_json_object(result["response"])
            self.assertEqual(scripts["en"][0], "e1")
            self.assertEqual(result["response_id"], "run-1")


if __name__ == "__main__":
    unittest.main()
