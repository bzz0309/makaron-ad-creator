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
from makaron_ad_creator.schema import campaign_template, validate_config
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


if __name__ == "__main__":
    unittest.main()
