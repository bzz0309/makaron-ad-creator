from __future__ import annotations

import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from makaron_ad_creator.media import comparison_layout_qc, compose_comparison, is_vertical_resolution_acceptable, normalize_near_vertical_resolution
from makaron_ad_creator.cli import _project_for_skill, main, project_binding_key, resolve_campaign_path
from makaron_ad_creator.pipeline import Pipeline, cached_final_design_matches_effect_segments, is_non_retryable_error, plan_for
from makaron_ad_creator.prompts import after_prompt, before_prompt, bgm_prompt, effect_prompt, final_prompt, script_prompt
from makaron_ad_creator.schema import BUNDLED_LOGO_CTA_MASTER_URI, DEFAULT_LOGO_CTA, DEFAULT_LOGO_CTA_MASTER, campaign_template, locale_config, validate_config
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

    def make_timing_manifest(self) -> Path:
        path = self.root / "timing-manifest.json"
        scenes = {
            "hook": {"startMs": 0, "endMs": 2500},
            "comparison": {"startMs": 2500, "endMs": 5000},
            "workflow": {"startMs": 5000, "endMs": 9000},
            "result": {"startMs": 9000, "endMs": 15000},
            "cta": {"startMs": 15000, "endMs": 18000},
        }
        captions = [
            {"text": str(index), "startMs": start, "endMs": end, "timestampMs": start, "confidence": 1}
            for index, (start, end) in enumerate(((100, 2000), (2700, 4700), (5100, 6500), (6600, 8500), (9200, 14000)))
        ]
        write_json(path, {
            "compositionContractVersion": 2,
            "safeZone": {"topPx": 250, "bottomPx": 340, "leftPx": 90, "rightPx": 180, "captionTopPx": 250, "maxCharactersPerLine": 20},
            "captions": captions,
            "scenes": scenes,
            "lineSceneMap": ["hook", "comparison", "workflow", "workflow", "result"],
        })
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
        self.assertIn("workflow-yue", node_ids)
        self.assertNotIn("workflow-en", node_ids)
        self.assertIn("workflow-yue", final["depends_on"])

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
            self.assertIn(f"workflow-{locale}", [node["id"] for node in plan])
            final = next(node for node in plan if node["id"] == f"final-{locale}")
            self.assertIn("bgm", final["depends_on"])
            self.assertIn(f"workflow-{locale}", final["depends_on"])
            self.assertIn("hook", final["depends_on"])
            self.assertIn("result", final["depends_on"])
            self.assertNotIn("effect", final["depends_on"])
        self.assertEqual(next(node for node in plan if node["id"] == "after")["kind"], "generate_image")
        self.assertEqual(next(node for node in plan if node["id"] == "comparison")["kind"], "local")
        effect = next(node for node in plan if node["id"] == "effect")
        hook = next(node for node in plan if node["id"] == "hook")
        result = next(node for node in plan if node["id"] == "result")
        self.assertEqual(effect["kind"], "generate_video")
        self.assertEqual(hook, {"id": "hook", "kind": "local", "depends_on": ["effect"]})
        self.assertEqual(result, {"id": "result", "kind": "local", "depends_on": ["effect"]})
        self.assertEqual(next(node for node in plan if node["id"] == "workflow-en")["kind"], "local")

    def test_campaign_uses_bundled_fixed_logo_cta(self) -> None:
        path = self.make_campaign()
        config = validate_config(read_json(path), path)
        self.assertEqual(Path(config["assets"]["logo_cta"]), DEFAULT_LOGO_CTA)
        self.assertTrue(DEFAULT_LOGO_CTA.is_file())
        self.assertEqual(config["assets"]["logo_cta_excerpt_seconds"], 3.0)
        self.assertEqual(config["assets"]["logo_cta_start_seconds"], 0.0)
        self.assertEqual(config["audio"]["tts_voice"], "natural energetic young-adult female")
        self.assertEqual(config["audio"]["tts_volume_by_locale"], {"en": 1.35, "ja": 1.35, "yue": 1.35})
        self.assertEqual(config["audio"]["bgm_volume"], 0.14)
        self.assertEqual(config["audio"]["bgm_ducking"], {
            "enabled": True,
            "ducked_volume": 0.08,
            "attack_ms": 80,
            "release_ms": 240,
            "trigger": "caption_timed_seed_audio",
        })
        self.assertTrue(config["audio"]["mute_source_audio"])
        self.assertFalse(config["audio"]["cta_source_audio"])
        self.assertEqual(config["output"]["minimum_duration_seconds"], 15.0)
        self.assertEqual(config["output"]["preferred_duration_seconds"], 18.0)
        self.assertEqual(config["output"]["duration_seconds"], 20.0)
        self.assertEqual(config["output"]["minimum_width"], 720)
        self.assertEqual(config["output"]["minimum_height"], 1280)
        self.assertEqual(config["output"]["safe_zone"]["top_px"], 250)
        self.assertEqual(config["output"]["safe_zone"]["bottom_px"], 340)
        self.assertAlmostEqual(config["output"]["safe_zone"]["top_ratio"], 250 / 1920)
        self.assertAlmostEqual(config["output"]["safe_zone"]["caption_top_ratio"], 250 / 1920)
        self.assertEqual(config["output"]["safe_zone"]["max_characters_per_line"], 32)
        self.assertEqual(config["automation"]["builder_skill_id"], "tiktok-video")
        self.assertLess(DEFAULT_LOGO_CTA.stat().st_size, 1_000_000)
        self.assertGreater(DEFAULT_LOGO_CTA_MASTER.stat().st_size, DEFAULT_LOGO_CTA.stat().st_size)

    def test_legacy_caption_position_is_normalized_to_highest_meta_safe_y(self) -> None:
        path = self.make_campaign()
        config = read_json(path)
        config["output"]["safe_zone"]["caption_top_px"] = 270
        config["output"]["safe_zone"]["caption_top_ratio"] = 270 / 1920
        validated = validate_config(config, path)
        self.assertEqual(validated["output"]["safe_zone"]["caption_top_px"], 250)
        self.assertAlmostEqual(validated["output"]["safe_zone"]["caption_top_ratio"], 250 / 1920)

    def test_legacy_full_cta_uri_resolves_to_upload_safe_excerpt_for_final(self) -> None:
        path = self.make_campaign()
        config = read_json(path)
        config["assets"]["logo_cta"] = BUNDLED_LOGO_CTA_MASTER_URI
        write_json(path, config)
        pipeline = Pipeline(path, executor="agent")
        self.assertEqual(pipeline._cta_input_path(), DEFAULT_LOGO_CTA.resolve())

    def test_final_prompt_locks_body_and_young_female_tts(self) -> None:
        path = self.make_campaign()
        config = validate_config(read_json(path), path)
        scripts = {"en": [f"line {index}" for index in range(5)]}
        prompt = final_prompt(config, "en", scripts)
        self.assertIn("natural energetic young-adult female", prompt)
        self.assertIn("props.voiceoverUrl", prompt)
        self.assertIn("props.voiceoverVolume=1.35", prompt)
        self.assertIn("props.bgmVolume=0.14", prompt)
        self.assertIn("props.audioDucking={enabled:true, duckedVolume:0.08, attackMs:80, releaseMs:240", prompt)
        self.assertIn("LOCKED FINAL ORDER", prompt)
        self.assertIn("Hook video", prompt)
        self.assertIn("comparison image", prompt)
        self.assertIn("localized workflow video", prompt)
        self.assertIn("effect/result video", prompt)
        self.assertIn("Logo CTA exactly 3.0s", prompt)
        self.assertIn("15.0-20.0 second five-part final video", prompt)
        self.assertIn("aiming for 18.0 seconds", prompt)
        self.assertIn("full duration of attached video 1 for Hook", prompt)
        self.assertIn("internal Remotion workflow", prompt)
        self.assertIn("Seed Audio voiceover", prompt)
        self.assertIn("Loop audio 1 as the same continuous BGM", prompt)
        self.assertIn("including the Hook, effect video, workflow video, and Logo CTA", prompt)
        self.assertIn("Caption JSON objects", prompt)
        self.assertIn("within 150ms", prompt)
        self.assertIn("never pause to ask the user a timing question", prompt)
        self.assertIn("older 140px", prompt)
        self.assertIn("y=250", prompt)
        self.assertIn("at most 32 visible characters", prompt)
        self.assertIn("Prefer one physical line", prompt)
        self.assertIn("measured balanced wrap", prompt)
        self.assertIn("never leave an orphan line of only one or two words", prompt)
        self.assertIn("CSS top to exactly y=250", prompt)
        self.assertIn("horizontally centered inside the full safe content width", prompt)
        self.assertIn("must not contain literal backslash-n", prompt)
        self.assertIn("topRatio=", prompt)
        self.assertIn("video 1 is the opening Hook segment extracted from the target-Skill effect source", prompt)
        self.assertIn("never request or invent a separately generated Hook", prompt)
        self.assertIn("minimum 720x1280", prompt)
        self.assertIn("do not ask the CLI to perform local FFmpeg", prompt)
        effect = effect_prompt(config)
        self.assertIn("existing bound-project image 1 (<<<media_1>>>)", before_prompt(config))
        self.assertIn("do not ask for or upload another copy", before_prompt(config))
        self.assertIn("seedance-2-0", effect)
        self.assertIn("existing bound-project image 1 (<<<media_1>>>)", effect)
        self.assertIn("active Skill's own SKILL.md is the creative source of truth", effect)
        self.assertIn("fill and use its locked video prompt template", effect)
        self.assertIn("Do not add a source-photo studio introduction", effect)
        self.assertIn("derive non-overlapping Hook and Result ranges", effect)
        self.assertIn("active Skill wins", effect)
        self.assertIn("never below 720x1280", effect)
        scripts_prompt = script_prompt(config)
        self.assertIn("must not say or repeat the exact Skill name", scripts_prompt)
        self.assertIn("under 1.8 seconds", scripts_prompt)
        self.assertIn("first-person testimonial", scripts_prompt)
        self.assertIn("Open Makaron.", scripts_prompt)
        self.assertIn("Use the template.", scripts_prompt)
        self.assertIn("Makaronを開いた。", scripts_prompt)
        self.assertIn("テンプレートを選んだ。", scripts_prompt)
        self.assertIn("我揀咗個模板。", scripts_prompt)
        self.assertIn("not commands addressed to the viewer", scripts_prompt)
        self.assertIn("never a Mandarin reading", scripts_prompt)
        config["effect_segments"] = {
            "hook": {"start_seconds": 0.0, "end_seconds": 3.0, "playback_speed": 1.0},
            "result": {"start_seconds": 8.0, "end_seconds": 14.0, "playback_speed": 1.2},
        }
        segment_prompt = final_prompt(config, "en", scripts)
        self.assertIn("Hook for exactly 3.000s", segment_prompt)
        self.assertIn("Result for exactly 5.000s", segment_prompt)
        self.assertIn("override the builder's default 2.5-second Hook", segment_prompt)
        music = bgm_prompt(config)
        self.assertIn("instrumental only", music)
        self.assertIn("no vocals", music)

    def test_bound_project_source_image_is_reused_without_reupload(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="makaron")
        adapter = Mock()

        def create_output(**kwargs):
            destination = Path(kwargs["destination"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"generated")
            return {"response_id": f"response-{kwargs['node_id']}"}

        adapter.chat.side_effect = create_output
        with patch.object(pipeline, "_adapter", return_value=adapter), \
             patch("makaron_ad_creator.pipeline.probe_video", return_value={"width": 1080, "height": 1920, "duration": 8.0}), \
             patch("makaron_ad_creator.pipeline.normalize_near_vertical_resolution", return_value=False):
            pipeline._generate_before()
            pipeline._generate_effect(1)

        before_call, effect_call = adapter.chat.call_args_list
        self.assertIsNone(before_call.kwargs.get("images"))
        self.assertIsNone(effect_call.kwargs.get("images"))
        self.assertIn("<<<media_1>>>", before_call.kwargs["prompt"])
        self.assertIn("<<<media_1>>>", effect_call.kwargs["prompt"])

    def test_locale_voiceover_gain_is_validated_and_serialized(self) -> None:
        path = self.make_campaign()
        config = read_json(path)
        config["audio"]["tts_volume_by_locale"] = {"en": 1.0, "ja": 2.0, "yue": 1.0}
        write_json(path, config)
        validated = validate_config(read_json(path), path)
        scripts = {"ja": [f"line {index}" for index in range(5)]}
        prompt = final_prompt(validated, "ja", scripts)
        self.assertIn("props.voiceoverVolume=2.00", prompt)
        self.assertEqual(validated["audio"]["tts_volume_by_locale"]["ja"], 2.0)

        config = read_json(path)
        config["audio"]["tts_volume_by_locale"]["ja"] = 2.01
        write_json(path, config)
        with self.assertRaisesRegex(AdCreatorError, "tts_volume_by_locale.ja"):
            validate_config(read_json(path), path)

    def test_completed_agent_final_is_preserved_without_local_postprocess(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        pipeline.state["nodes"]["final-en"]["status"] = "WAITING_FOR_AGENT"
        pipeline.save()
        rendered = self.root / "remotion-final.mp4"
        rendered.write_bytes(b"remotion final with seed audio subtitles bgm and cta")
        pipeline.complete_agent_node("final-en", rendered, "response-final", timing_manifest=self.make_timing_manifest())
        final = pipeline.artifact("final-en", ".mp4")
        self.assertEqual(final.name, "final-artifact-en.mp4")
        self.assertEqual(final.read_bytes(), b"remotion final with seed audio subtitles bgm and cta")

    def test_agent_final_requires_timing_manifest(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        pipeline.state["nodes"]["final-en"]["status"] = "WAITING_FOR_AGENT"
        pipeline.save()
        rendered = self.root / "missing-manifest.mp4"
        rendered.write_bytes(b"video")
        with self.assertRaisesRegex(AdCreatorError, "timing manifest"):
            pipeline.complete_agent_node("final-en", rendered)

    def test_final_agent_request_drives_remotion_with_cta_and_bgm_url(self) -> None:
        path = self.make_campaign()
        config = read_json(path)
        config["locales"] = locale_config(["en"])
        write_json(path, config)
        pipeline = Pipeline(path, executor="agent")

        scripts = self.root / "scripts.json"
        write_json(scripts, {"en": [f"line {index}" for index in range(5)]})
        comparison = self.root / "comparison.png"
        hook = self.root / "hook.mp4"
        result = self.root / "result.mp4"
        bgm = self.root / "bgm.mp3"
        workflow_en = self.root / "workflow-en.mp4"
        comparison.write_bytes(b"comparison")
        hook.write_bytes(b"hook")
        result.write_bytes(b"result")
        bgm.write_bytes(b"bgm")
        workflow_en.write_bytes(b"workflow")

        pipeline.add_artifact("scripts", scripts)
        pipeline.add_artifact("comparison", comparison, source_url="https://cdn.example.com/comparison.png")
        pipeline.add_artifact("hook", hook, source_url="https://cdn.example.com/hook.mp4")
        pipeline.add_artifact("result", result, source_url="https://cdn.example.com/result.mp4")
        pipeline.add_artifact("bgm", bgm, source_url="https://cdn.example.com/bgm.mp3")
        pipeline.add_artifact("workflow-en", workflow_en, source_url="https://cdn.example.com/workflow-en.mp4")
        node = next(item for item in pipeline.plan if item["id"] == "final-en")
        publisher = SimpleNamespace(publish_local_media=lambda path, role: "https://cdn.example.com/logo.mp4")
        with patch.object(pipeline, "_adapter", return_value=publisher), \
             patch("makaron_ad_creator.pipeline.probe_video", return_value={"width": 1080, "height": 1920, "duration": 2.5}):
            pipeline._write_agent_request(node)

        request = read_json(path.parent / "run" / "requests" / "final-en.json")
        self.assertEqual(request["operation"], "assemble_localized_ad")
        self.assertEqual(request["audios"], ["https://cdn.example.com/bgm.mp3"])
        self.assertEqual(request["input_roles"]["videos"][-1], "fixed_logo_cta")
        self.assertEqual(request["input_roles"]["videos"][0], "effect_derived_hook")
        self.assertEqual(request["input_roles"]["videos"][1], "non_overlapping_effect_result")
        self.assertEqual(request["composition"]["engine"], "makaron-agent-remotion")
        self.assertEqual(request["composition"]["builder_skill_id"], "tiktok-video")
        self.assertEqual((request["composition"]["width"], request["composition"]["height"]), (1080, 1920))
        self.assertTrue(request["composition"]["dimensions_must_not_follow_source_media"])
        self.assertEqual(request["composition"]["tts_engine"], "seed-audio")
        self.assertEqual(request["composition"]["caption_format"], "remotion-caption-json")
        self.assertTrue(request["composition"]["scene_bound_caption_timing"])
        self.assertTrue(request["composition"]["hook_and_result_must_be_distinct"])
        self.assertTrue(request["composition"]["hook_and_result_share_exact_effect_source"])
        self.assertFalse(request["composition"]["local_ffmpeg_audio_or_subtitle_postprocess"])
        self.assertTrue(request["composition"]["same_bgm_looped_across_full_video"])
        self.assertEqual(request["videos"], [
            "https://cdn.example.com/hook.mp4",
            "https://cdn.example.com/result.mp4",
            "https://cdn.example.com/workflow-en.mp4",
            "https://cdn.example.com/logo.mp4",
        ])
        self.assertEqual(request["images"], ["https://cdn.example.com/comparison.png"])

    def test_design_only_final_is_rendered_after_current_asset_binding(self) -> None:
        path = self.make_campaign()
        config = read_json(path)
        config["locales"] = locale_config(["en"])
        write_json(path, config)
        pipeline = Pipeline(path, executor="makaron")
        assets = {
            "scripts": self.root / "scripts.json",
            "comparison": self.root / "comparison.png",
            "hook": self.root / "hook.mp4",
            "result": self.root / "result.mp4",
            "bgm": self.root / "bgm.mp3",
            "workflow-en": self.root / "workflow-en.mp4",
        }
        write_json(assets["scripts"], {"en": [f"line {index}" for index in range(5)]})
        for role, asset in assets.items():
            if role != "scripts":
                asset.write_bytes(role.encode())
        pipeline.add_artifact("scripts", assets["scripts"])
        pipeline.add_artifact("comparison", assets["comparison"], source_url="https://cdn.example.com/comparison.png")
        pipeline.add_artifact("hook", assets["hook"], source_url="https://cdn.example.com/hook.mp4")
        pipeline.add_artifact("result", assets["result"], source_url="https://cdn.example.com/result.mp4")
        pipeline.add_artifact("bgm", assets["bgm"], source_url="https://cdn.example.com/bgm.mp3")
        pipeline.add_artifact("workflow-en", assets["workflow-en"], source_url="https://cdn.example.com/workflow.mp4")

        props = read_json(self.make_timing_manifest())
        props.update({
            "comparisonImage": "https://cdn.example.com/comparison.png",
            "hookVideo": "https://cdn.example.com/hook.mp4",
            "resultVideo": "https://cdn.example.com/result.mp4",
            "workflowVideo": "https://cdn.example.com/workflow.mp4",
            "ctaVideo": "https://cdn.example.com/logo.mp4",
            "bgmUrl": "https://cdn.example.com/bgm.mp3",
        })
        design = {
            "width": 1080,
            "height": 1920,
            "animation": {"fps": 30, "durationInSeconds": 18},
            "code": "function Composition() { return null; } comparisonImage hookVideo resultVideo workflowVideo ctaVideo bgmUrl",
            "props": props,
        }

        def render_fallback(_: str, response: dict, destination: Path) -> dict:
            rebound = response["result"]["designs"][0]
            self.assertEqual(rebound["props"]["comparisonImage"], "https://cdn.example.com/comparison.png")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"rendered final")
            return {"engine": "local-remotion-from-makaron-design"}

        adapter = SimpleNamespace(
            publish_local_media=lambda _path, role: "https://cdn.example.com/logo.mp4",
            chat=Mock(return_value={
                "response_id": "run-1",
                "response": {"result": {"designs": [design]}},
                "remotion_design_only": True,
            }),
            render_remotion_fallback=Mock(side_effect=render_fallback),
        )
        final_info = {"width": 1080, "height": 1920, "duration": 18.0, "codec": "h264", "has_audio": True, "bytes": 1024}
        def fake_probe(video: Path) -> dict:
            if Path(video).name == "hook.mp4":
                return {**final_info, "duration": 2.5}
            if Path(video).name == "result.mp4":
                return {**final_info, "duration": 6.0}
            return final_info
        with patch.object(pipeline, "_adapter", return_value=adapter), \
             patch("makaron_ad_creator.pipeline.probe_video", side_effect=fake_probe), \
             patch("makaron_ad_creator.pipeline.bgm_similarity_in_cta", return_value=0.9):
            pipeline._generate_final("en", 1)
        adapter.render_remotion_fallback.assert_called_once()
        artifact = pipeline.state["nodes"]["final-en"]["artifacts"][0]
        self.assertEqual(artifact["render_fallback"]["engine"], "local-remotion-from-makaron-design")

    def test_makaron_asset_requests_are_explicit_and_locale_scoped(self) -> None:
        path = self.make_campaign()
        config = read_json(path)
        config["locales"] = locale_config(["en"])
        write_json(path, config)
        pipeline = Pipeline(path, executor="agent")
        effect = self.root / "effect.mp4"
        before = self.root / "before.png"
        after = self.root / "after.png"
        effect.write_bytes(b"effect")
        Image.new("RGB", (720, 1280), "blue").save(before)
        Image.new("RGB", (720, 1280), "orange").save(after)
        pipeline.add_artifact("effect", effect)
        pipeline.add_artifact("before", before)
        pipeline.add_artifact("after", after)

        after_node = next(item for item in pipeline.plan if item["id"] == "after")
        pipeline._write_agent_request(after_node)

        after_request = read_json(path.parent / "run" / "requests" / "after.json")
        self.assertEqual(after_request["operation"], "select_exact_effect_keyframe")
        self.assertIn("strongest exact decoded source frame", after_request["selection_rule"])
        self.assertNotIn("82%", after_request["prompt"])
        self.assertIn("strongest", after_prompt(config))
        self.assertFalse((path.parent / "run" / "requests" / "comparison.json").exists())
        self.assertEqual(next(item for item in pipeline.plan if item["id"] == "comparison")["kind"], "local")

    def test_hook_and_result_are_exact_non_overlapping_effect_segments(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        pipeline.config["effect_segments"] = {
            "hook": {"start_seconds": 0.0, "end_seconds": 3.0, "playback_speed": 1.0},
            "result": {"start_seconds": 8.0, "end_seconds": 14.0, "playback_speed": 1.2},
        }
        effect = self.root / "effect.mp4"
        effect.write_bytes(b"one target skill effect source")
        pipeline.add_artifact("effect", effect)
        extract_calls: list[tuple[float, float, float]] = []

        def fake_extract(source: Path, output: Path, *, start_seconds: float, duration_seconds: float, playback_speed: float) -> Path:
            self.assertEqual(source.resolve(), effect.resolve())
            extract_calls.append((start_seconds, duration_seconds, playback_speed))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(f"{start_seconds:.1f}-{duration_seconds:.1f}".encode())
            return output

        segment_plan = {
            "source_duration": 15.0,
            "hook_start": 0.0,
            "hook_duration": 2.5,
            "result_start": 2.5,
            "result_duration": 5.5,
        }
        video_info = {"width": 1080, "height": 1920, "duration": 5.0}
        with patch("makaron_ad_creator.pipeline.effect_segment_plan", return_value=segment_plan), \
             patch("makaron_ad_creator.pipeline.extract_video_segment", side_effect=fake_extract), \
             patch("makaron_ad_creator.pipeline.probe_video", return_value=video_info):
            pipeline._derive_effect_segment("hook")
            pipeline._derive_effect_segment("result")

        hook_meta = pipeline.state["nodes"]["hook"]["artifacts"][0]
        result_meta = pipeline.state["nodes"]["result"]["artifacts"][0]
        self.assertEqual(hook_meta["source_effect_sha256"], result_meta["source_effect_sha256"])
        self.assertLessEqual(
            hook_meta["start_seconds"] + hook_meta["duration_seconds"],
            result_meta["start_seconds"],
        )
        self.assertEqual(hook_meta["source"], "exact-non-overlapping-effect-segment")
        self.assertEqual(result_meta["source"], "exact-non-overlapping-effect-segment")
        self.assertEqual(extract_calls, [(0.0, 3.0, 1.0), (8.0, 6.0, 1.2)])
        self.assertEqual(result_meta["playback_speed"], 1.2)
        self.assertEqual(result_meta["output_duration_seconds"], 5.0)

    def test_cached_final_design_rejected_when_effect_segment_lengths_changed(self) -> None:
        manifest = read_json(self.make_timing_manifest())
        design = {"props": manifest, "code": "", "animation": {}}
        self.assertTrue(cached_final_design_matches_effect_segments(
            design,
            hook_duration=2.5,
            result_duration=6.0,
        ))

        stale_manifest = read_json(self.make_timing_manifest())
        stale_manifest["scenes"]["hook"] = {"startMs": 0, "endMs": 3550}
        stale_manifest["scenes"]["result"] = {"startMs": 9000, "endMs": 14270}
        stale_design = {"props": stale_manifest, "code": "", "animation": {}}
        self.assertFalse(cached_final_design_matches_effect_segments(
            stale_design,
            hook_duration=2.041667,
            result_duration=3.0,
        ))

    def test_derived_hook_ignores_stale_generated_response_url(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        hook = self.root / "hook.mp4"
        hook.write_bytes(b"derived hook")
        pipeline.add_artifact("hook", hook, source="exact-non-overlapping-effect-segment")
        response_dir = path.parent / "run" / "responses"
        response_dir.mkdir(parents=True, exist_ok=True)
        write_json(response_dir / "hook.json", {"result": {"videos": [{"videoUrl": "https://stale.example.com/hook.mp4"}]}})
        publisher = SimpleNamespace(publish_local_media=lambda media, role: "https://cdn.example.com/derived-hook.mp4")
        with patch.object(pipeline, "_adapter", return_value=publisher), \
             patch("makaron_ad_creator.pipeline.probe_video", return_value={"width": 1080, "height": 1920}):
            resolved = pipeline._final_video_input("hook", hook, role="hook")
        self.assertEqual(resolved, "https://cdn.example.com/derived-hook.mp4")

    def test_large_final_video_gets_upload_safe_1080p_proxy(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        source = self.root / "workflow.mp4"
        source.write_bytes(b"x" * (4 * 1024 * 1024 + 1))

        def fake_run(command: list[str]):
            output = Path(command[-1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"proxy")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("makaron_ad_creator.pipeline.run_command", side_effect=fake_run) as mocked_run, \
             patch("makaron_ad_creator.pipeline.probe_video", side_effect=[
                 {"width": 1080, "height": 1920},
                 {"width": 1080, "height": 1920},
             ]):
            proxy = pipeline._upload_safe_video(source, "workflow-en")
        self.assertEqual(proxy.name, "workflow-en-1080p.mp4")
        self.assertEqual(proxy.read_bytes(), b"proxy")
        command = mocked_run.call_args.args[0]
        self.assertIn("scale=1080:1920", command[command.index("-vf") + 1])
        self.assertIn("-crf", command)
        self.assertNotIn("-b:v", command)

    def test_small_720p_final_input_is_normalized_before_upload(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        source = self.root / "cta.mp4"
        source.write_bytes(b"small-720p")

        def fake_run(command: list[str]):
            Path(command[-1]).write_bytes(b"normalized-1080p")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("makaron_ad_creator.pipeline.run_command", side_effect=fake_run), \
             patch("makaron_ad_creator.pipeline.probe_video", side_effect=[
                 {"width": 720, "height": 1280},
                 {"width": 1080, "height": 1920},
             ]):
            proxy = pipeline._upload_safe_video(source, "logo-cta")
        self.assertEqual(proxy.name, "logo-cta-1080p.mp4")
        self.assertEqual(proxy.read_bytes(), b"normalized-1080p")

    def test_payload_too_large_is_not_retried(self) -> None:
        self.assertTrue(is_non_retryable_error(AdCreatorError("Error 413: Request Entity Too Large")))
        self.assertTrue(is_non_retryable_error(AdCreatorError("Error 402: insufficient_credits")))
        self.assertTrue(is_non_retryable_error(AdCreatorError("Cannot download generated artifact: curl failed")))

    def test_script_hook_rejects_exact_skill_name(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        pipeline.config["locales"] = [{"ad_locale": "en", "ui_locale": "en"}]
        with self.assertRaisesRegex(AdCreatorError, "must not repeat the Skill name"):
            pipeline._validate_scripts({"en": ["One photo. Example.", "two", "Open Makaron.", "Use the template.", "five"]})

    def test_script_validation_requires_first_person_and_rejects_detached_narration(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        valid_scripts = {
            "en": ["I never expected this.", "I used one ordinary photo.", "Open Makaron.", "Use the template.", "Now I love the result."],
            "ja": ["私がこんな姿になれるなんて。", "普通の写真一枚から始めた。", "Makaronを開いた。", "テンプレートを選んだ。", "仕上がりが本当に好き。"],
            "yue": ["我真係估唔到。", "我只係用咗一張普通相。", "我打開 Makaron。", "我揀咗個模板。", "而家個效果我好鍾意。"],
        }
        for locale, lines in valid_scripts.items():
            pipeline.config["locales"] = [{"ad_locale": locale, "ui_locale": {"en": "en", "ja": "ja", "yue": "zh-Hant"}[locale]}]
            pipeline._validate_scripts({locale: lines})

        pipeline.config["locales"] = [{"ad_locale": "en", "ui_locale": "en"}]
        with self.assertRaisesRegex(AdCreatorError, "locked action statements"):
            pipeline._validate_scripts({"en": ["I never expected this.", "I used one ordinary photo.", "I opened Makaron.", "I chose an effect.", "Now I love the result."]})
        with self.assertRaisesRegex(AdCreatorError, "first-person speaker"):
            pipeline._validate_scripts({"en": ["What a result.", "One ordinary photo.", "Open Makaron.", "Use the template.", "Looks amazing."]})
        with self.assertRaisesRegex(AdCreatorError, "third-person narration"):
            pipeline._validate_scripts({"en": ["I could not believe it.", "She used one photo.", "Open Makaron.", "Use the template.", "I love it."]})

    def test_workflow_uses_bundled_v5_skill_and_requires_qc_manifest(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        generated = self.root / "crystal-ballet-workflow-en-synthetic.mp4"
        qc = self.root / "crystal-ballet-workflow-en-synthetic.mp4.qc.json"
        keyframes = self.root / "crystal-ballet-workflow-en-synthetic.keyframes.jpg"
        manifest = self.root / "crystal-ballet-synthetic-manifest.json"
        generated.write_bytes(b"v5 workflow")
        keyframes.write_bytes(b"keyframes")
        write_json(qc, {"pass": True})
        write_json(manifest, {"version": 2, "generated_with": "edit-makaron-app-workflow-recording"})
        response = {
            "pass": True,
            "manifest": str(manifest),
            "outputs": [{"output": str(generated), "qc": str(qc), "keyframes": str(keyframes)}],
        }
        completed = SimpleNamespace(stdout=json.dumps(response), stderr="", returncode=0)
        with patch("makaron_ad_creator.pipeline.run_command", return_value=completed) as mocked_run, \
             patch("makaron_ad_creator.pipeline.probe_video", return_value={"width": 1080, "height": 1920, "duration": 4.0}):
            pipeline._generate_workflow("en")

        command = mocked_run.call_args.args[0]
        self.assertIn("workflow_recording.py", command[1])
        self.assertIn("synthesize", command)
        self.assertEqual(command[command.index("--skill") + 1], "skill-1")
        self.assertEqual(command[command.index("--locales") + 1], "en")
        self.assertNotIn("screen-demo", command)
        artifact = pipeline.state["nodes"]["workflow-en"]["artifacts"][0]
        self.assertEqual(artifact["source"], "edit-makaron-app-workflow-recording-v5")
        self.assertEqual(artifact["ui_locale"], "en")
        self.assertEqual(artifact["qc_manifest"], str(qc.resolve()))
        self.assertEqual(artifact["workflow_manifest"], str(manifest.resolve()))

    def test_comparison_pipeline_is_deterministic_local_composition(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        before = self.root / "before-local.png"
        after = self.root / "after-local.png"
        Image.new("RGB", (600, 1000), "blue").save(before)
        Image.new("RGB", (1200, 800), "orange").save(after)
        pipeline.add_artifact("before", before)
        pipeline.add_artifact("after", after)
        with patch.object(pipeline, "_adapter") as adapter:
            pipeline._generate_comparison()
        adapter.assert_not_called()
        artifact = pipeline.state["nodes"]["comparison"]["artifacts"][0]
        self.assertEqual(artifact["source"], "deterministic-local-common-height-composition")
        self.assertEqual(artifact["resolution"], "1080x1920")
        report = read_json(Path(artifact["qc_report"]))
        self.assertEqual(report["status"], "PASS")

    def test_orphaned_running_node_is_resumed_without_spending_an_attempt(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        pipeline.state["status"] = "RUNNING"
        pipeline.state["runner"] = {"pid": 99999999, "host": __import__("socket").gethostname()}
        pipeline.state["nodes"]["validate"].update({"status": "PASS", "attempts": 1})
        pipeline.state["nodes"]["scripts"].update({"status": "RUNNING", "attempts": 1})
        pipeline.save()

        resumed = Pipeline(path, executor="agent")
        self.assertEqual(resumed.run(), "WAITING_FOR_AGENT")
        state = read_json(path.parent / "state.json")
        self.assertEqual(state["nodes"]["scripts"]["status"], "WAITING_FOR_AGENT")
        self.assertEqual(state["nodes"]["scripts"]["attempts"], 1)
        self.assertEqual(state["recoveries"][-1]["nodes"], ["scripts"])

    def test_campaign_reference_accepts_id_directory_and_config_path(self) -> None:
        path = self.make_campaign("reference-test")
        with patch.dict("os.environ", {"MAKARON_AD_WORKSPACE": str(self.root)}):
            self.assertEqual(resolve_campaign_path("reference-test"), path.resolve())
            self.assertEqual(resolve_campaign_path(str(path.parent)), path.resolve())
            self.assertEqual(resolve_campaign_path(str(path)), path.resolve())

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
        write_json(scripts, {
            "en": ["I never expected this.", "I used one photo.", "Open Makaron.", "Use the template.", "I love the result."],
            "ja": ["私がこんな姿になれるなんて。", "普通の写真一枚から始めた。", "Makaronを開いた。", "テンプレートを選んだ。", "仕上がりが好き。"],
            "yue": ["我真係估唔到。", "我只係用咗一張相。", "我打開 Makaron。", "我揀咗個模板。", "我好鍾意個效果。"],
        })
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

    def test_legacy_skill_binding_migrates_without_breaking_resume(self) -> None:
        path = self.make_campaign("legacy", "skill-1", "project-legacy")
        config = read_json(path)
        config["project_binding"] = {
            "strategy": "one_skill_one_persistent_project",
            "skill_id": "skill-1",
            "project_id": "project-legacy",
        }
        write_json(path, config)
        write_json(self.root / "project-registry.json", {
            "version": 1,
            "bindings": {"skill-1": "project-legacy"},
        })
        pipeline = Pipeline(path, executor="agent")
        self.assertEqual(pipeline.run(), "WAITING_FOR_AGENT")
        registry = read_json(self.root / "project-registry.json")
        self.assertEqual(registry["bindings"][project_binding_key("skill-1", self.image)], "project-legacy")
        self.assertEqual(registry["version"], 2)

    def test_comparison_is_exact_vertical_canvas(self) -> None:
        before = self.root / "before.png"
        after = self.root / "after.png"
        output = self.root / "comparison.png"
        Image.new("RGB", (700, 900), "blue").save(before)
        Image.new("RGB", (900, 700), "orange").save(after)
        compose_comparison(before, after, output)
        report = comparison_layout_qc(before, after, output)
        with Image.open(output) as image:
            self.assertEqual(image.size, (1080, 1920))
            self.assertEqual(image.mode, "RGB")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["layout"]["images"]["before"]["rendered_height"], report["layout"]["images"]["after"]["rendered_height"])

    def test_vertical_resolution_accepts_720p_but_rejects_lower(self) -> None:
        output = {"minimum_width": 720, "minimum_height": 1280}
        self.assertTrue(is_vertical_resolution_acceptable({"width": 1080, "height": 1920}, output))
        self.assertTrue(is_vertical_resolution_acceptable({"width": 720, "height": 1280}, output))
        self.assertFalse(is_vertical_resolution_acceptable({"width": 540, "height": 960}, output))
        self.assertFalse(is_vertical_resolution_acceptable({"width": 1280, "height": 720}, output))

    def test_near_720p_vertical_result_is_padded_to_minimum(self) -> None:
        source = self.root / "near-vertical.mp4"
        source.write_bytes(b"source")
        normalized = source.with_name("near-vertical.normalized.mp4")

        def fake_run(command: list[str], timeout: int = 600):
            normalized.write_bytes(b"normalized")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        probes = [
            {"width": 720, "height": 1264},
        ]
        with patch("makaron_ad_creator.media.probe_video", side_effect=probes), \
             patch("makaron_ad_creator.media.require_binary", return_value="ffmpeg"), \
             patch("makaron_ad_creator.media.run", side_effect=fake_run):
            changed = normalize_near_vertical_resolution(source, {"minimum_width": 720, "minimum_height": 1280})
        self.assertTrue(changed)
        self.assertEqual(source.read_bytes(), b"normalized")

    def test_agent_fail_advances_attempt_and_blocks_at_budget(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        self.assertEqual(pipeline.run(), "WAITING_FOR_AGENT")
        request = read_json(path.parent / "run" / "requests" / "scripts.json")
        self.assertEqual(request["attempt"], 1)
        self.assertEqual(request["model_preference"], "seedance-2-0")
        pipeline.fail_agent_node("scripts", "provider error")

        self.assertEqual(pipeline.run(), "WAITING_FOR_AGENT")
        request = read_json(path.parent / "run" / "requests" / "scripts.json")
        self.assertEqual(request["attempt"], 2)
        self.assertEqual(request["model_preference"], "kling")
        pipeline.fail_agent_node("scripts", "provider error")

        self.assertEqual(pipeline.run(), "WAITING_FOR_AGENT")
        request = read_json(path.parent / "run" / "requests" / "scripts.json")
        self.assertEqual(request["attempt"], 3)
        self.assertEqual(request["model_preference"], "grok")
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
        key = project_binding_key("market-skill-1", self.image)
        self.assertEqual(registry["bindings"][key], "project-created-1")
        self.assertEqual(registry["version"], 2)
        configs = list((self.root / "campaigns").glob("*/campaign.json"))
        self.assertEqual(len(configs), 1)
        config = read_json(configs[0])
        self.assertEqual(config["target_skill"]["name"], "Rainy Kiss")
        self.assertEqual(config["automation"]["executor"], "makaron")
        self.assertEqual(mocked_run.call_count, 2)

    def test_project_binding_reuses_same_image_but_isolates_a_new_image(self) -> None:
        second_image = self.root / "second.jpg"
        Image.new("RGB", (600, 900), "#204080").save(second_image)
        created_one = SimpleNamespace(stdout="ID: project-one\n", stderr="", returncode=0)
        media_one = SimpleNamespace(stdout=json.dumps({"media": [{"id": "m1"}]}), stderr="", returncode=0)
        created_two = SimpleNamespace(stdout="ID: project-two\n", stderr="", returncode=0)
        with patch("makaron_ad_creator.cli.run", side_effect=[created_one, media_one, created_two]) as mocked_run:
            first = _project_for_skill(self.root, "makaron", "skill-1", "Example", self.image)
            repeated = _project_for_skill(self.root, "makaron", "skill-1", "Example", self.image)
            second = _project_for_skill(self.root, "makaron", "skill-1", "Example", second_image)
        self.assertEqual((first, repeated, second), ("project-one", "project-one", "project-two"))
        registry = read_json(self.root / "project-registry.json")
        self.assertEqual(registry["bindings"][project_binding_key("skill-1", self.image)], "project-one")
        self.assertEqual(registry["bindings"][project_binding_key("skill-1", second_image)], "project-two")
        self.assertEqual(mocked_run.call_count, 3)

    def test_project_binding_rotates_when_media_capacity_is_reached(self) -> None:
        binding_key = project_binding_key("skill-1", self.image)
        write_json(self.root / "project-registry.json", {
            "version": 2,
            "bindings": {binding_key: "project-full"},
            "history": {},
        })
        full_media = SimpleNamespace(
            stdout=json.dumps({"media": [{"id": f"m{index}"} for index in range(60)]}),
            stderr="",
            returncode=0,
        )
        created = SimpleNamespace(stdout="ID: project-rotated\n", stderr="", returncode=0)
        with patch("makaron_ad_creator.cli.run", side_effect=[full_media, created]):
            project = _project_for_skill(self.root, "makaron", "skill-1", "Example", self.image)
        self.assertEqual(project, "project-rotated")
        registry = read_json(self.root / "project-registry.json")
        self.assertEqual(registry["bindings"][binding_key], "project-rotated")
        self.assertEqual(registry["history"][binding_key][-1]["project_id"], "project-full")
        self.assertEqual(registry["history"][binding_key][-1]["reason"], "media-capacity")

    def test_rotated_project_history_keeps_old_campaign_resumable(self) -> None:
        path = self.make_campaign("before-rotation", "skill-1", "project-full")
        binding_key = project_binding_key("skill-1", self.image)
        write_json(self.root / "project-registry.json", {
            "version": 2,
            "bindings": {binding_key: "project-rotated"},
            "history": {
                binding_key: [{
                    "project_id": "project-full",
                    "reason": "media-capacity",
                    "media_count": 60,
                }],
            },
        })
        pipeline = Pipeline(path, executor="agent")
        self.assertEqual(pipeline.run(), "WAITING_FOR_AGENT")
        registry = read_json(self.root / "project-registry.json")
        self.assertEqual(registry["bindings"][binding_key], "project-rotated")

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
