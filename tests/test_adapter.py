from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from makaron_ad_creator.adapter import (
    MakaronAdapter,
    extract_generated_image_urls,
    extract_generated_video_urls,
    extract_json_object,
    extract_remotion_design,
    validate_ad_remotion_design,
    validate_screen_demo_remotion_design,
)
from makaron_ad_creator.util import AdCreatorError


class AdapterTests(unittest.TestCase):
    def test_generated_image_urls_exclude_uploaded_source_attachments(self) -> None:
        response = {
            "media_urls": ["https://example.com/uploaded-input.jpg"],
            "output": [{"type": "text", "content": "no generated image"}],
            "result": {"images": []},
        }
        self.assertEqual(extract_generated_image_urls(response), [])

    def test_generated_image_urls_accept_authoritative_result_image(self) -> None:
        response = {
            "output": [{"type": "image", "url": "https://example.com/after.png"}],
            "result": {"images": [{"imageUrl": "https://example.com/after.png"}]},
        }
        self.assertEqual(extract_generated_image_urls(response), ["https://example.com/after.png"])

    def test_generated_video_urls_exclude_uploaded_source_attachments(self) -> None:
        response = {
            "media_urls": ["https://example.com/uploaded-cta.mp4"],
            "output": [{"type": "text", "content": "export was Forbidden"}],
            "result": {"videos": [], "designs": [{"snapshotId": "draft-1"}]},
        }
        self.assertEqual(extract_generated_video_urls(response), [])

    def test_generated_video_urls_accept_authoritative_result_video(self) -> None:
        response = {
            "output": [{"type": "video", "status": "completed", "url": "https://example.com/final.mp4"}],
            "result": {"videos": [{"videoUrl": "https://example.com/final.mp4"}]},
        }
        self.assertEqual(extract_generated_video_urls(response), ["https://example.com/final.mp4"])

    def test_extract_remotion_design_accepts_completed_design_payload(self) -> None:
        design = {
            "snapshotId": "snapshot-1",
            "code": "function Composition() { return null; }",
            "props": {},
            "animation": {"fps": 30, "durationInSeconds": 18},
        }
        self.assertEqual(extract_remotion_design({"result": {"designs": [design]}}), design)

    def test_remotion_contract_rejects_caption_crossing_scene_boundary(self) -> None:
        scenes = {
            "hook": {"startMs": 0, "endMs": 2500},
            "comparison": {"startMs": 2500, "endMs": 5000},
            "workflow": {"startMs": 5000, "endMs": 9000},
            "result": {"startMs": 9000, "endMs": 15000},
            "cta": {"startMs": 15000, "endMs": 18000},
        }
        captions = [
            {"text": str(index), "startMs": start, "endMs": end, "timestampMs": start, "confidence": 1}
            for index, (start, end) in enumerate(((100, 2000), (3900, 6100), (5100, 6500), (6600, 8500), (9200, 14000)))
        ]
        design = {
            "props": {
                "compositionContractVersion": 2,
                "safeZone": {"topPx": 250, "bottomPx": 340, "leftPx": 90, "rightPx": 180, "captionTopPx": 270, "maxCharactersPerLine": 20},
                "captions": captions,
                "scenes": scenes,
                "lineSceneMap": ["hook", "comparison", "workflow", "workflow", "result"],
            }
        }
        with self.assertRaisesRegex(AdCreatorError, "crosses.*comparison"):
            validate_ad_remotion_design(design)

    def test_final_chat_rejects_source_video_when_export_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            fake = root / "fake-makaron"
            fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            adapter = MakaronAdapter("project-1", root / "run", str(fake))
            raw = {
                "responseId": "response-1",
                "uploadedVideo": "https://example.com/uploaded-cta.mp4",
                "output": [{"type": "text", "content": "Forbidden"}],
                "result": {"videos": [], "designs": [{"snapshotId": "draft-1"}]},
            }
            with patch("makaron_ad_creator.adapter.run", return_value=SimpleNamespace(stdout=json.dumps(raw), stderr="", returncode=0)):
                with self.assertRaisesRegex(AdCreatorError, "no exported final MP4"):
                    adapter.chat(
                        node_id="final-en",
                        prompt="export",
                        destination=root / "final.mp4",
                        require_generated_video=True,
                    )
            self.assertTrue((root / "run" / "responses" / "final-en.json").is_file())

    def test_screen_demo_does_not_use_local_remotion_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            fake = root / "fake-makaron"
            fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            adapter = MakaronAdapter("project-1", root / "run", str(fake))
            raw = {
                "responseId": "response-1",
                "result": {"videos": [], "designs": [{"snapshotId": "draft-1"}]},
            }
            with patch("makaron_ad_creator.adapter.run", return_value=SimpleNamespace(stdout=json.dumps(raw), stderr="", returncode=0)), \
                 patch.object(adapter, "render_remotion_fallback") as fallback:
                with self.assertRaisesRegex(AdCreatorError, "no generated video"):
                    adapter.chat(
                        node_id="workflow-en",
                        prompt="screen demo",
                        destination=root / "workflow.mp4",
                        require_generated_video=True,
                        allow_remotion_fallback=False,
                    )
            fallback.assert_not_called()

    def test_screen_demo_contract_accepts_four_second_vertical_design(self) -> None:
        design = {
            "width": 1080,
            "height": 1920,
            "animation": {"fps": 30, "durationInSeconds": 4},
        }
        validate_screen_demo_remotion_design(design)

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

    def test_music_create_polls_and_downloads_instrumental(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            fake = root / "fake-makaron"
            fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            destination = root / "run" / "assets" / "bgm.mp3"
            responses = [
                SimpleNamespace(stdout='{"taskId":"music-1","status":"queued"}', stderr="", returncode=0),
                SimpleNamespace(stdout='{"taskId":"music-1","status":"completed","audioUrl":"https://example.com/bgm.mp3"}', stderr="", returncode=0),
            ]

            def fake_download(_: str, output: Path) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"music")
                return output

            adapter = MakaronAdapter("project-1", root / "run", str(fake))
            with patch("makaron_ad_creator.adapter.run", side_effect=responses) as mocked_run, \
                 patch("makaron_ad_creator.adapter.download", side_effect=fake_download), \
                 patch("makaron_ad_creator.adapter.time.sleep"):
                result = adapter.create_music(
                    node_id="bgm",
                    prompt="instrumental only",
                    style="cinematic electronic",
                    destination=destination,
                )
            self.assertEqual(result["response_id"], "music-1")
            self.assertEqual(destination.read_bytes(), b"music")
            self.assertEqual(mocked_run.call_args_list[0].args[0][1:3], ["music", "create"])
            self.assertEqual(mocked_run.call_args_list[1].args[0][1:3], ["music", "status"])


if __name__ == "__main__":
    unittest.main()
