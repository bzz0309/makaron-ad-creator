from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from makaron_ad_creator.media import bgm_similarity_in_cta
from makaron_ad_creator.util import require_binary, run


class MediaTests(unittest.TestCase):
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
