from __future__ import annotations

import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from makaron_ad_creator.media import compose_comparison
from makaron_ad_creator.cli import main
from makaron_ad_creator.pipeline import Pipeline, plan_for
from makaron_ad_creator.prompts import bgm_prompt, final_prompt
from makaron_ad_creator.schema import DEFAULT_LOGO_CTA, campaign_template, locale_config, validate_config
from makaron_ad_creator.util import AdCreatorError, read_json, write_json


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.image = self.root / "input.jpg"
        Image.new("RGB", (600, 900), "#9060a0").save(self.image)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_campaign(self, campaign_id: str = "test", skill_id: str = "skill-1", project_id: str = "project-1") -> Path:
        campaign_dir = self.root / "campaigns" / campaign_id
        campaign_dir.mkdir(parents=True)
        config = campaign_template(
            campaign_id=campaign_id,
            image=self.image,
            skill_id=skill_id,
            skill_name="Example",
            skill_core="turn the authorized portrait into a cinematic scene",
            project_id=project_id,
            subject_description="authorized adult",
        )
        path = campaign_dir / "campaign.json"
        write_json(path, config)
        write_json(campaign_dir / "plan.json", {"version": 1, "nodes": plan_for(config)})
        return path

    def test_schema_rejects_auto_project(self) -> None:
        path = self.make_campaign()
        config = read_json(path)
        config["project_binding"]["project_id"] = "auto"
        write_json(path, config)
        with self.assertRaisesRegex(AdCreatorError, "non-auto"):
            validate_config(read_json(path), path)

    def test_single_cantonese_locale_uses_traditional_chinese_workflow(self) -> None:
        path = self.make_campaign()
        config = read_json(path)
        config["locales"] = locale_config(["yue"])
        write_json(path, config)
        validated = validate_config(read_json(path), path)
        self.assertEqual(validated["locales"], [{"ad_locale": "yue", "ui_locale": "zh-Hant"}])
        plan = plan_for(validated)
        node_ids = [node["id"] for node in plan]
        self.assertIn("final-yue", node_ids)
        self.assertNotIn("final-en", node_ids)
        self.assertNotIn("final-ja", node_ids)
        qc = next(node for node in plan if node["id"] == "qc")
        self.assertEqual(qc["depends_on"], ["final-yue"])
        final = next(node for node in plan if node["id"] == "final-yue")
        self.assertIn("bgm", final["depends_on"])

    def test_all_ad_locales_have_fixed_ui_mapping(self) -> None:
        self.assertEqual(
            locale_config(["en", "ja", "yue"]),
            [
                {"ad_locale": "en", "ui_locale": "en"},
                {"ad_locale": "ja", "ui_locale": "ja"},
                {"ad_locale": "yue", "ui_locale": "zh-Hant"},
            ],
        )

        path = self.make_campaign()
        plan = plan_for(validate_config(read_json(path), path))
        self.assertEqual([node["id"] for node in plan].count("bgm"), 1)
        for locale in ("en", "ja", "yue"):
            final = next(node for node in plan if node["id"] == f"final-{locale}")
            self.assertIn("bgm", final["depends_on"])

    def test_campaign_uses_bundled_fixed_logo_cta(self) -> None:
        path = self.make_campaign()
        config = validate_config(read_json(path), path)
        self.assertEqual(Path(config["assets"]["logo_cta"]), DEFAULT_LOGO_CTA)
        self.assertTrue(DEFAULT_LOGO_CTA.is_file())
        self.assertEqual(config["assets"]["logo_cta_excerpt_seconds"], 3.0)
        self.assertEqual(config["assets"]["logo_cta_start_seconds"], 0.0)
        self.assertEqual(config["audio"]["tts_voice"], "natural energetic young-adult female")
        self.assertEqual(config["audio"]["bgm_volume"], 0.22)
        self.assertTrue(config["audio"]["mute_source_audio"])
        self.assertFalse(config["audio"]["cta_source_audio"])
        self.assertEqual(config["output"]["minimum_duration_seconds"], 15.0)
        self.assertEqual(config["output"]["preferred_duration_seconds"], 18.0)
        self.assertEqual(config["output"]["duration_seconds"], 20.0)

    def test_final_prompt_locks_body_and_young_female_tts(self) -> None:
        path = self.make_campaign()
        config = validate_config(read_json(path), path)
        scripts = {"en": [f"line {index}" for index in range(5)]}
        prompt = final_prompt(config, "en", scripts)
        self.assertIn("natural energetic young-adult female", prompt)
        self.assertIn("LOCKED FINAL ORDER", prompt)
        self.assertIn("Hook video", prompt)
        self.assertIn("comparison image", prompt)
        self.assertIn("localized workflow video", prompt)
        self.assertIn("effect/result video", prompt)
        self.assertIn("Logo CTA exactly 3.0s", prompt)
        self.assertIn("15.0-20.0 second five-part final video", prompt)
        self.assertIn("aiming for 18.0 seconds", prompt)
        self.assertIn("Hook 2.5-5.0s", prompt)
        self.assertIn("internal Remotion workflow", prompt)
        self.assertIn("Seed Audio voiceover", prompt)
        self.assertIn("Loop audio 1 as the same continuous BGM", prompt)
        self.assertIn("including the effect video, workflow video, and Logo CTA", prompt)
        self.assertIn("top-aligned 140px", prompt)
        self.assertIn("do not ask the CLI to perform local FFmpeg", prompt)
        music = bgm_prompt(config)
        self.assertIn("instrumental only", music)
        self.assertIn("no vocals", music)

    def test_completed_agent_final_is_preserved_without_local_postprocess(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        pipeline.state["nodes"]["final-en"]["status"] = "WAITING_FOR_AGENT"
        pipeline.save()
        rendered = self.root / "remotion-final.mp4"
        rendered.write_bytes(b"remotion final with seed audio subtitles bgm and cta")
        pipeline.complete_agent_node("final-en", rendered, "response-final")
        final = pipeline.artifact("final-en", ".mp4")
        self.assertEqual(final.name, "final-artifact-en.mp4")
        self.assertEqual(final.read_bytes(), b"remotion final with seed audio subtitles bgm and cta")

    def test_final_agent_request_drives_remotion_with_cta_and_bgm_url(self) -> None:
        path = self.make_campaign()
        config = read_json(path)
        config["locales"] = locale_config(["en"])
        write_json(path, config)
        pipeline = Pipeline(path, executor="agent")

        scripts = self.root / "scripts.json"
        write_json(scripts, {"en": [f"line {index}" for index in range(5)]})
        comparison = self.root / "comparison.png"
        effect = self.root / "effect.mp4"
        bgm = self.root / "bgm.mp3"
        workflow = self.root / "workflow.json"
        workflow_en = self.root / "workflow-en.mp4"
        comparison.write_bytes(b"comparison")
        effect.write_bytes(b"effect")
        bgm.write_bytes(b"bgm")
        write_json(workflow, {"ok": True})
        workflow_en.write_bytes(b"workflow")

        pipeline.add_artifact("scripts", scripts)
        pipeline.add_artifact("comparison", comparison)
        pipeline.add_artifact("effect", effect)
        pipeline.add_artifact("bgm", bgm, source_url="https://cdn.example.com/bgm.mp3")
        workflow_item = pipeline.add_artifact("workflow", workflow)
        workflow_item["locale_outputs"] = {"en": str(workflow_en)}
        node = next(item for item in pipeline.plan if item["id"] == "final-en")
        pipeline._write_agent_request(node)

        request = read_json(path.parent / "run" / "requests" / "final-en.json")
        self.assertEqual(request["operation"], "assemble_localized_ad")
        self.assertEqual(request["audios"], ["https://cdn.example.com/bgm.mp3"])
        self.assertEqual(request["input_roles"]["videos"][-1], "fixed_logo_cta")
        self.assertEqual(request["composition"]["engine"], "makaron-agent-remotion")
        self.assertEqual(request["composition"]["tts_engine"], "seed-audio")
        self.assertFalse(request["composition"]["local_ffmpeg_audio_or_subtitle_postprocess"])
        self.assertTrue(request["composition"]["same_bgm_looped_across_full_video"])

    def test_schema_rejects_wrong_ui_mapping_for_selected_locale(self) -> None:
        path = self.make_campaign()
        config = read_json(path)
        config["locales"] = [{"ad_locale": "yue", "ui_locale": "zh"}]
        write_json(path, config)
        with self.assertRaisesRegex(AdCreatorError, "yue->zh-Hant"):
            validate_config(read_json(path), path)

    def test_agent_executor_emits_one_request_and_resumes(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        self.assertEqual(pipeline.run(), "WAITING_FOR_AGENT")
        state = read_json(path.parent / "state.json")
        self.assertEqual(state["nodes"]["validate"]["status"], "PASS")
        self.assertEqual(state["nodes"]["scripts"]["status"], "WAITING_FOR_AGENT")
        request = read_json(Path(state["nodes"]["scripts"]["request"]))
        self.assertEqual(request["project_id"], "project-1")
        self.assertTrue(request["must_use_bound_project"])

        scripts = self.root / "scripts.json"
        write_json(scripts, {locale: [f"{locale}-{index}" for index in range(5)] for locale in ("en", "ja", "yue")})
        pipeline.complete_agent_node("scripts", scripts, "response-1")
        self.assertEqual(pipeline.run(), "WAITING_FOR_AGENT")
        state = read_json(path.parent / "state.json")
        self.assertEqual(state["nodes"]["scripts"]["status"], "PASS")
        self.assertEqual(state["nodes"]["before"]["status"], "WAITING_FOR_AGENT")

    def test_registry_rejects_project_reuse_by_another_skill(self) -> None:
        first = self.make_campaign("one", "skill-1", "project-shared")
        self.assertEqual(Pipeline(first, executor="agent").run(), "WAITING_FOR_AGENT")
        second = self.make_campaign("two", "skill-2", "project-shared")
        pipeline = Pipeline(second, executor="agent")
        self.assertEqual(pipeline.run(), "BLOCKED")
        state = read_json(second.parent / "state.json")
        self.assertIn("another Skill", state["nodes"]["validate"]["last_error"])

    def test_comparison_is_exact_vertical_canvas(self) -> None:
        before = self.root / "before.png"
        after = self.root / "after.png"
        output = self.root / "comparison.png"
        Image.new("RGB", (700, 900), "blue").save(before)
        Image.new("RGB", (900, 700), "orange").save(after)
        compose_comparison(before, after, output)
        with Image.open(output) as image:
            self.assertEqual(image.size, (1080, 1920))
            self.assertEqual(image.mode, "RGB")

    def test_agent_fail_advances_attempt_and_blocks_at_budget(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        self.assertEqual(pipeline.run(), "WAITING_FOR_AGENT")
        request = read_json(path.parent / "run" / "requests" / "scripts.json")
        self.assertEqual(request["attempt"], 1)
        pipeline.fail_agent_node("scripts", "provider error")

        self.assertEqual(pipeline.run(), "WAITING_FOR_AGENT")
        request = read_json(path.parent / "run" / "requests" / "scripts.json")
        self.assertEqual(request["attempt"], 2)
        pipeline.fail_agent_node("scripts", "provider error")

        self.assertEqual(pipeline.run(), "WAITING_FOR_AGENT")
        request = read_json(path.parent / "run" / "requests" / "scripts.json")
        self.assertEqual(request["attempt"], 3)
        pipeline.fail_agent_node("scripts", "provider error")
        self.assertEqual(read_json(path.parent / "state.json")["nodes"]["scripts"]["status"], "BLOCKED")

    def test_two_argument_entrypoint_resolves_skill_and_creates_binding(self) -> None:
        marketplace = {
            "id": "market-skill-1",
            "label": "Rainy Kiss",
            "description": "turn an authorized adult portrait into a cinematic rain scene",
        }
        responses = [
            SimpleNamespace(stdout=json.dumps(marketplace), stderr="", returncode=0),
            SimpleNamespace(stdout="✅ Project created\n   ID: project-created-1\n", stderr="", returncode=0),
        ]
        with patch.dict("os.environ", {"MAKARON_AD_WORKSPACE": str(self.root), "MAKARON_AD_MAKARON_BIN": "fake-makaron"}), \
             patch("makaron_ad_creator.cli.run", side_effect=responses) as mocked_run, \
             patch("makaron_ad_creator.cli.Pipeline.run", return_value="PASS"):
            self.assertEqual(main([str(self.image), "Rainy Kiss"]), 0)
        registry = read_json(self.root / "project-registry.json")
        self.assertEqual(registry["bindings"]["market-skill-1"], "project-created-1")
        configs = list((self.root / "campaigns").glob("*/campaign.json"))
        self.assertEqual(len(configs), 1)
        config = read_json(configs[0])
        self.assertEqual(config["target_skill"]["name"], "Rainy Kiss")
        self.assertEqual(config["automation"]["executor"], "makaron")
        self.assertEqual(mocked_run.call_count, 2)

    def test_public_entrypoint_accepts_one_selected_locale(self) -> None:
        marketplace = {
            "id": "market-skill-1",
            "label": "Screen Burst",
            "description": "make the authorized subject burst through a screen",
        }
        responses = [
            SimpleNamespace(stdout=json.dumps(marketplace), stderr="", returncode=0),
            SimpleNamespace(stdout="ID: project-created-1\n", stderr="", returncode=0),
        ]
        with patch.dict("os.environ", {"MAKARON_AD_WORKSPACE": str(self.root), "MAKARON_AD_MAKARON_BIN": "fake-makaron"}), \
             patch("makaron_ad_creator.cli.run", side_effect=responses), \
             patch("makaron_ad_creator.cli.Pipeline.run", return_value="PASS"):
            self.assertEqual(main([str(self.image), "Screen Burst", "--locale", "yue"]), 0)
        config_path = next((self.root / "campaigns").glob("*/campaign.json"))
        config = read_json(config_path)
        self.assertEqual(config["locales"], [{"ad_locale": "yue", "ui_locale": "zh-Hant"}])

    def test_public_entrypoint_rejects_unknown_locale_before_external_calls(self) -> None:
        with patch("makaron_ad_creator.cli.run") as mocked_run:
            self.assertEqual(main([str(self.image), "Screen Burst", "--locale", "fr"]), 2)
        mocked_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
