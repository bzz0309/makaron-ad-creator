from __future__ import annotations

import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from makaron_ad_creator.media import compose_comparison, is_vertical_resolution_acceptable, normalize_near_vertical_resolution
from makaron_ad_creator.cli import main
from makaron_ad_creator.pipeline import Pipeline, cached_final_design_matches_effect_segments, is_non_retryable_error, plan_for
from makaron_ad_creator.prompts import after_prompt, bgm_prompt, comparison_prompt, effect_prompt, final_prompt, script_prompt
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
            "safeZone": {"topPx": 250, "bottomPx": 340, "leftPx": 90, "rightPx": 180, "captionTopPx": 270, "maxCharactersPerLine": 20},
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
        self.assertEqual(next(node for node in plan if node["id"] == "comparison")["kind"], "generate_image")
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
        self.assertEqual(config["audio"]["bgm_volume"], 0.22)
        self.assertTrue(config["audio"]["mute_source_audio"])
        self.assertFalse(config["audio"]["cta_source_audio"])
        self.assertEqual(config["output"]["minimum_duration_seconds"], 15.0)
        self.assertEqual(config["output"]["preferred_duration_seconds"], 18.0)
        self.assertEqual(config["output"]["duration_seconds"], 20.0)
        self.assertEqual(config["output"]["minimum_width"], 720)
        self.assertEqual(config["output"]["minimum_height"], 1280)
        self.assertEqual(config["output"]["safe_zone"]["top_px"], 250)
        self.assertEqual(config["output"]["safe_zone"]["bottom_px"], 340)
        self.assertEqual(config["automation"]["builder_skill_id"], "tiktok-video")
        self.assertLess(DEFAULT_LOGO_CTA.stat().st_size, 1_000_000)
        self.assertGreater(DEFAULT_LOGO_CTA_MASTER.stat().st_size, DEFAULT_LOGO_CTA.stat().st_size)

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
        self.assertIn("y=270", prompt)
        self.assertIn("at most 20 visible characters", prompt)
        self.assertIn("video 1 is the opening Hook segment extracted from the target-Skill effect source", prompt)
        self.assertIn("never request or invent a separately generated Hook", prompt)
        self.assertIn("minimum 720x1280", prompt)
        self.assertIn("do not ask the CLI to perform local FFmpeg", prompt)
        effect = effect_prompt(config)
        self.assertIn("seedance-2-0", effect)
        self.assertIn("active Skill's own SKILL.md is the creative source of truth", effect)
        self.assertIn("fill and use its locked video prompt template", effect)
        self.assertIn("Do not add a source-photo studio introduction", effect)
        self.assertIn("derive non-overlapping Hook and Result ranges", effect)
        self.assertIn("active Skill wins", effect)
        self.assertIn("never below 720x1280", effect)
        scripts_prompt = script_prompt(config)
        self.assertIn("must not say or repeat the exact Skill name", scripts_prompt)
        self.assertIn("under 1.8 seconds", scripts_prompt)
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
             patch("makaron_ad_creator.pipeline.probe_video", return_value={"duration": 2.5}):
            pipeline._write_agent_request(node)

        request = read_json(path.parent / "run" / "requests" / "final-en.json")
        self.assertEqual(request["operation"], "assemble_localized_ad")
        self.assertEqual(request["audios"], ["https://cdn.example.com/bgm.mp3"])
        self.assertEqual(request["input_roles"]["videos"][-1], "fixed_logo_cta")
        self.assertEqual(request["input_roles"]["videos"][0], "effect_derived_hook")
        self.assertEqual(request["input_roles"]["videos"][1], "non_overlapping_effect_result")
        self.assertEqual(request["composition"]["engine"], "makaron-agent-remotion")
        self.assertEqual(request["composition"]["builder_skill_id"], "tiktok-video")
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

        for node_id in ("after", "comparison"):
            node = next(item for item in pipeline.plan if item["id"] == node_id)
            pipeline._write_agent_request(node)

        after_request = read_json(path.parent / "run" / "requests" / "after.json")
        self.assertEqual(after_request["operation"], "select_exact_effect_keyframe")
        self.assertIn("strongest exact decoded source frame", after_request["selection_rule"])
        self.assertNotIn("82%", after_request["prompt"])
        comparison_request = read_json(path.parent / "run" / "requests" / "comparison.json")
        self.assertEqual(comparison_request["operation"], "compose_comparison_in_makaron")
        self.assertIn("strongest", after_prompt(config))
        self.assertIn("Makaron", comparison_prompt(config))

    def test_hook_and_result_are_exact_non_overlapping_effect_segments(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        effect = self.root / "effect.mp4"
        effect.write_bytes(b"one target skill effect source")
        pipeline.add_artifact("effect", effect)

        def fake_extract(source: Path, output: Path, *, start_seconds: float, duration_seconds: float) -> Path:
            self.assertEqual(source.resolve(), effect.resolve())
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(f"{start_seconds:.1f}-{duration_seconds:.1f}".encode())
            return output

        segment_plan = {
            "source_duration": 8.0,
            "hook_start": 0.0,
            "hook_duration": 2.5,
            "result_start": 2.5,
            "result_duration": 5.5,
        }
        video_info = {"width": 1080, "height": 1920, "duration": 2.5}
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
        with patch.object(pipeline, "_adapter", return_value=publisher):
            resolved = pipeline._final_video_input("hook", hook, role="hook")
        self.assertEqual(resolved, "https://cdn.example.com/derived-hook.mp4")

    def test_large_final_video_gets_upload_safe_720p_proxy(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        source = self.root / "workflow.mp4"
        source.write_bytes(b"x" * (4 * 1024 * 1024 + 1))

        def fake_run(command: list[str]):
            output = Path(command[-1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"proxy")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("makaron_ad_creator.pipeline.run_command", side_effect=fake_run), \
             patch("makaron_ad_creator.pipeline.probe_video", return_value={"width": 720, "height": 1280}):
            proxy = pipeline._upload_safe_video(source, "workflow-en")
        self.assertEqual(proxy.name, "workflow-en-720p.mp4")
        self.assertEqual(proxy.read_bytes(), b"proxy")

    def test_payload_too_large_is_not_retried(self) -> None:
        self.assertTrue(is_non_retryable_error(AdCreatorError("Error 413: Request Entity Too Large")))

    def test_script_hook_rejects_exact_skill_name(self) -> None:
        path = self.make_campaign()
        pipeline = Pipeline(path, executor="agent")
        pipeline.config["locales"] = [{"ad_locale": "en", "ui_locale": "en"}]
        with self.assertRaisesRegex(AdCreatorError, "must not repeat the Skill name"):
            pipeline._validate_scripts({"en": ["One photo. Example.", "two", "Open Makaron.", "Use the template.", "five"]})

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
