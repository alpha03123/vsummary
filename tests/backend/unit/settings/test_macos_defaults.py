from pathlib import Path
from tempfile import TemporaryDirectory
import tomllib
import unittest
from unittest.mock import patch

from backend.video_summary.infrastructure.config.settings import ensure_settings_file


class MacDefaultsTests(unittest.TestCase):
    def test_new_mac_config_uses_cpp_and_cpu_embedding_without_overwriting_existing_config(self):
        template = Path(__file__).resolve().parents[4] / "config/settings.toml.example"
        with TemporaryDirectory() as directory, patch(
            "backend.video_summary.infrastructure.config.settings.sys.platform", "darwin"
        ):
            path = Path(directory) / "settings.toml"
            path.with_suffix(".toml.example").write_bytes(template.read_bytes())
            ensure_settings_file(path)
            config = tomllib.loads(path.read_text())
            self.assertEqual(config["asr"]["provider"], "whisper_cpp")
            self.assertEqual(config["agent_retrieval"]["embedding_device"], "cpu")
            path.write_text('[asr]\nprovider = "aliyun_bailian"\n')
            ensure_settings_file(path)
            self.assertEqual(tomllib.loads(path.read_text())["asr"]["provider"], "aliyun_bailian")
