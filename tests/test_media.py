# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from unittest import mock

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


import core.archive as core_archive
import core.ytdl_format as core_ytdl_format
import ui.theme as ui_theme
from core.config import ConfigManager

sys.path.insert(0, os.path.dirname(__file__))

class TestMetadataAndTitlePreservation(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.cfg_path = os.path.join(self.tmp_dir.name, "test_config.json")
        self.cfg = ConfigManager(self.cfg_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_default_embed_metadata_is_true(self):
        self.assertTrue(self.cfg.get_default_embed_metadata())
        self.cfg.set_default_embed_metadata(False)
        self.assertFalse(self.cfg.get_default_embed_metadata())
        self.cfg.set_default_embed_metadata(True)
        self.assertTrue(self.cfg.get_default_embed_metadata())

    def test_exact_title_preservation(self):
        long_title = "This Is A Very Long Exact Title That Exceeds Fifty Characters And Must Not Be Truncated"
        sanitized = core_archive.sanitize_filename(long_title, max_len=140)
        self.assertEqual(sanitized, long_title)
        self.assertGreater(len(sanitized), 50)

    def test_get_ydl_format_includes_metadata_and_artwork_converter(self):
        fmt, pps = core_ytdl_format.get_ydl_format(mode="video", embed_metadata=True)
        pp_keys = [p.get("key") for p in pps]
        self.assertIn("FFmpegMetadata", pp_keys)
        self.assertIn("FFmpegThumbnailsConvertor", pp_keys)
        self.assertIn("EmbedThumbnail", pp_keys)

        fmt_a, pps_a = core_ytdl_format.get_ydl_format(mode="audio", audio_format="mp3", embed_metadata=True)
        pp_keys_a = [p.get("key") for p in pps_a]
        self.assertIn("FFmpegExtractAudio", pp_keys_a)
        self.assertIn("FFmpegMetadata", pp_keys_a)
        self.assertIn("FFmpegThumbnailsConvertor", pp_keys_a)
        self.assertIn("EmbedThumbnail", pp_keys_a)

    def test_tag_audio_metadata_mp3_with_artwork(self):
        from mutagen.id3 import ID3
        mp3_path = os.path.join(self.tmp_dir.name, "sample.mp3")
        cover_path = os.path.join(self.tmp_dir.name, "cover.jpg")
        with open(mp3_path, "wb") as f:
            f.write(b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 40)
        with open(cover_path, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0mock_cover_bytes")

        core_archive.tag_audio_metadata(
            mp3_path,
            title="Complete Exact Song Title Without Any Truncation",
            artist="Renowned Artist",
            album="Masterpiece Collection",
            date="2024-03-15",
            cover_url=cover_path,
            comment="Downloaded via Antigravity Universal Downloader"
        )

        id3 = ID3(mp3_path)
        self.assertEqual(str(id3["TIT2"]), "Complete Exact Song Title Without Any Truncation")
        self.assertEqual(str(id3["TPE1"]), "Renowned Artist")
        self.assertEqual(str(id3["TALB"]), "Masterpiece Collection")
        self.assertEqual(str(id3["TDRC"]), "2024-03-15")
        apics = id3.getall("APIC")
        self.assertEqual(len(apics), 1)
        self.assertEqual(apics[0].data, b"\xff\xd8\xff\xe0mock_cover_bytes")

    def test_tag_audio_metadata_sibling_thumbnail_cleanup(self):
        from mutagen.id3 import ID3
        mp3_path = os.path.join(self.tmp_dir.name, "track.mp3")
        sibling_thumb = os.path.join(self.tmp_dir.name, "track.jpg")
        with open(mp3_path, "wb") as f:
            f.write(b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 40)
        with open(sibling_thumb, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0" + b"X" * 150)

        core_archive.tag_audio_metadata(
            mp3_path,
            title="Sibling Track",
            artist="Artist Name",
            album="Album Name"
        )

        id3 = ID3(mp3_path)
        apics = id3.getall("APIC")
        self.assertEqual(len(apics), 1)
        self.assertFalse(os.path.exists(sibling_thumb))

    def test_find_downloaded_media_file(self):
        item_id = "uniq_item_456"
        target_file = os.path.join(self.tmp_dir.name, f"youtube_channel_{item_id}_Full Exact Title.mp4")
        with open(target_file, "w") as f:
            f.write("mock video content")

        found = core_archive.find_downloaded_media_file(self.tmp_dir.name, item_id)
        self.assertIsNotNone(found)
        self.assertEqual(os.path.abspath(found), os.path.abspath(target_file))

    def test_clear_terminal_safety(self):
        with unittest.mock.patch("sys.stdout.isatty", return_value=False):
            with mock.patch("ui.theme.console.clear") as mock_clear:
                ui_theme.clear_terminal()
                mock_clear.assert_not_called()

        with unittest.mock.patch("sys.stdout.isatty", return_value=True):
            with mock.patch("ui.theme.console.clear") as mock_clear:
                with unittest.mock.patch("sys.stdout.write") as mock_write:
                    with unittest.mock.patch("sys.stdout.flush"):
                        ui_theme.clear_terminal()
                        mock_clear.assert_called_once()
                        mock_write.assert_called_with("\033[3J\033[2J\033[H")
