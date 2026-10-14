"""Packaging regression checks; no proprietary browser fixture is stored."""

from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_browser
import build_boing_disc


class BrowserPatchTests(unittest.TestCase):
    def test_unknown_binary_is_rejected_before_tools_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "1ST_READ.BIN").write_bytes(b"unreviewed browser")
            runner = mock.Mock()
            with self.assertRaisesRegex(ValueError, "Unsupported browser executable"):
                prepare_browser.prepare_browser(folder, folder / "adapted.bin", runner=runner)
            runner.run.assert_not_called()
            self.assertFalse((folder / "adapted.bin").exists())

    def test_layout_patch_preserves_payload_and_appends_shim(self):
        # Synthetic bytes verify preservation without distributing the real app.
        raw = bytearray((i * 17 + 3) % 256 for i in range(prepare_browser.SOURCE_BYTES))
        raw[:12] = b"\x09\x00" * 6
        struct.pack_into("<I", raw, prepare_browser.PVD_OFFSET, 166)
        raw = bytes(raw)
        shim = b"\x09\x00" * 8
        for layout, pvd in (("data-data", 166), ("audio-data", 11868)):
            with self.subTest(layout=layout), mock.patch.object(prepare_browser, "validate_source") as validate:
                result, address, actual_pvd = prepare_browser.inject_adapter(raw, shim, layout)
                validate.assert_called_once_with(raw)
                self.assertEqual(address, 0xAC010000 + len(raw))
                self.assertEqual(struct.unpack_from("<I", result, 8)[0], address)
                self.assertEqual(actual_pvd, pvd)
                self.assertEqual(struct.unpack_from("<I", result, prepare_browser.PVD_OFFSET)[0], pvd)
                self.assertEqual(result[len(raw):], shim)
                restored = bytearray(result[:len(raw)])
                restored[:12] = raw[:12]
                restored[prepare_browser.PVD_OFFSET:prepare_browser.PVD_OFFSET + 4] = raw[prepare_browser.PVD_OFFSET:prepare_browser.PVD_OFFSET + 4]
                self.assertEqual(bytes(restored), raw)

    def test_existing_output_remains_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate.cdi"
            output.write_bytes(b"previous accepted candidate")
            with self.assertRaises(FileExistsError):
                prepare_browser.refuse_existing([output])
            self.assertEqual(output.read_bytes(), b"previous accepted candidate")


class PackagingTests(unittest.TestCase):
    def test_relative_payload_and_empty_directory_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source, staging = folder / "source", folder / "staged"
            source.mkdir()
            for name in ("IP.BIN", "1ST_READ.BIN", "0.0"):
                (source / name).write_bytes(b"old bootstrap")
            (source / "VMU Games" / "Empty").mkdir(parents=True)
            (source / "VMU Games" / "STACKCHN.VMS").write_bytes(b"payload-vms")
            (source / "VMU Games" / "STACKCHN.VMI").write_bytes(b"payload-vmi")
            files = build_boing_disc.stage_payload(source, staging)
            self.assertEqual({item["path"] for item in files},
                             {"VMU Games/STACKCHN.VMS", "VMU Games/STACKCHN.VMI"})
            self.assertTrue((staging / "VMU Games" / "Empty").is_dir())
            self.assertEqual((staging / "VMU Games" / "STACKCHN.VMS").read_bytes(), b"payload-vms")
            self.assertFalse((staging / "IP.BIN").exists())

    def test_wrong_builder_revision_is_rejected(self):
        runner = mock.Mock()
        runner.run.return_value = "0" * 40
        with self.assertRaisesRegex(ValueError, "differs from required"):
            build_boing_disc.verify_builder(runner, "mkdcdisc", "source", "audio-data")
        self.assertEqual(runner.run.call_count, 1)

    def test_changed_session_address_is_rejected(self):
        runner = mock.Mock()
        runner.run.side_effect = [build_boing_disc.BUILDER_COMMIT, "", "mkdcdisc v0.0.4", "11703"]
        with self.assertRaisesRegex(ValueError, "expected 11702"):
            build_boing_disc.verify_builder(runner, "mkdcdisc", "source", "audio-data")


if __name__ == "__main__":
    unittest.main()
