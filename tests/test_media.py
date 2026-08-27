from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from makaron_ad_creator.media import bgm_similarity_in_cta, comparison_layout_qc, compose_comparison, extract_video_segment
from makaron_ad_creator.util import AdCreatorError, require_binary, run


class MediaTests(unittest.TestCase):
    def test_comparison_uses_one_common_rendered_height_and_black_background(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            before = root / "before.png"
            after = root / "after.png"
            output = root / "comparison.png"
            Image.new("RGB", (600, 1200), "blue").save(before)
            Image.new("RGB", (1200, 1200), "orange").save(after)
            compose_comparison(before, after, output)
            report = comparison_layout_qc(before, after, output)
            left = report["layout"]["images"]["before"]
            right = report["layout"]["images"]["after"]
            labels = report["layout"]["labels"]
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["layout"]["canvas"], {"width": 1080, "height": 1920, "background": "#000000"})
            self.assertEqual(report["layout"]["gap_px"], 10)
            self.assertEqual(left["rendered_height"], right["rendered_height"])
            self.assertEqual((left["top"], left["bottom"]), (right["top"], right["bottom"]))
            self.assertEqual(right["left"] - left["right"], 10)
            self.assertLessEqual(
                abs(report["layout"]["group"]["outer_left"] - report["layout"]["group"]["outer_right"]),
                1,
            )
            self.assertGreaterEqual(report["layout"]["group"]["outer_left"], 40)
            self.assertGreaterEqual(report["layout"]["group"]["outer_right"], 40)
            self.assertLessEqual(labels["before"]["image_center_delta_px"], 1)
            self.assertLessEqual(labels["after"]["image_center_delta_px"], 1)
            self.assertEqual(labels["before"]["baseline_y"], labels["after"]["baseline_y"])
            self.assertLessEqual(abs((labels["before"]["visible_top"] - left["bottom"]) - 35), 1)
            self.assertLessEqual(abs((labels["after"]["visible_top"] - right["bottom"]) - 35), 1)
            self.assertTrue(report["checks"]["background_outside_images_and_labels_black"])

    def test_comparison_qc_rejects_non_black_background_pixel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            before = root / "before.png"
            after = root / "after.png"
            output = root / "comparison.png"
            Image.new("RGB", (600, 1200), "blue").save(before)
            Image.new("RGB", (1200, 1200), "orange").save(after)
            compose_comparison(before, after, output)
            with Image.open(output) as raw:
                tampered = raw.convert("RGB")
            tampered.putpixel((0, 0), (255, 0, 0))
            tampered.save(output)
            with self.assertRaisesRegex(AdCreatorError, "background_outside_images_and_labels_black"):
                comparison_layout_qc(before, after, output)

    def test_extract_video_segment_uses_uniform_playback_speed(self) -> None:
        with patch("makaron_ad_creator.media.require_binary", return_value="ffmpeg"), \
             patch("makaron_ad_creator.media.run") as mocked_run:
            extract_video_segment(
                Path("source.mp4"),
                Path("result.mp4"),
                start_seconds=8.0,
                duration_seconds=6.0,
                playback_speed=1.2,
            )
        command = mocked_run.call_args.args[0]
        self.assertIn("setpts=(PTS-STARTPTS)/1.200000", command)
        self.assertLess(command.index("-ss"), command.index("-i"))
        self.assertLess(command.index("-t"), command.index("-i"))

    def test_bgm_similarity_detects_same_track_in_cta(self) -> None:
        ffmpeg = require_binary("ffmpeg")
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            final = root / "final.mp4"
            matching = root / "matching.wav"
            different = root / "different.wav"
            run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=black:s=180x320:r=30:d=2",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
                "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(final),
            ])
            run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3", str(matching),
            ])
            run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=48000:duration=3", str(different),
            ])
            self.assertGreater(bgm_similarity_in_cta(final, matching, 0.8), 0.8)
            self.assertLess(bgm_similarity_in_cta(final, different, 0.8), 0.3)


if __name__ == "__main__":
    unittest.main()
