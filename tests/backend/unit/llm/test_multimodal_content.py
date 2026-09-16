from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.shared.llm.multimodal import build_multimodal_user_content


class MultimodalContentTests(unittest.TestCase):
    def test_encodes_local_jpeg_as_data_url(self) -> None:
        with TemporaryDirectory() as directory:
            image = Path(directory) / "frame.jpg"
            image.write_bytes(b"jpeg")

            content = build_multimodal_user_content(text="识别画面", image_paths=[image])

            self.assertEqual(content[0], {"type": "text", "text": "识别画面"})
            self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    def test_rejects_non_jpeg(self) -> None:
        with TemporaryDirectory() as directory:
            image = Path(directory) / "frame.png"
            image.write_bytes(b"png")

            with self.assertRaisesRegex(ValueError, "JPEG"):
                build_multimodal_user_content(text="识别画面", image_paths=[image])
