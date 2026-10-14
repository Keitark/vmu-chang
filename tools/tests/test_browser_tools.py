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


class HardwareStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = bytearray((i * 17 + 3) % 256 for i in range(prepare_browser.SOURCE_BYTES))
        raw[:12] = b"\x09\x00" * 6
        struct.pack_into("<I", raw, prepare_browser.PVD_OFFSET, 166)
        struct.pack_into("<I", raw, prepare_browser.CACHE_TARGET_OFFSET, prepare_browser.SOURCE_CACHE_TARGET)
        cls.raw = bytes(raw)
        cls.shim = b"\x09\x00" * 8
        cls.address = 0xAC010000 + len(raw)

    def test_hardware_patch_preserves_surrounding_browser_bytes(self):
        for layout, pvd in (("data-data", 166), ("audio-data", 11868)):
            for alias in (self.address + 4, (self.address + 4) & ~0x20000000):
                with self.subTest(layout=layout, alias=hex(alias)), mock.patch.object(prepare_browser, "validate_source"):
                    result, address, actual_pvd = prepare_browser.inject_adapter(
                        self.raw, self.shim, layout, hardware_startup=True, cache_entry=alias)
                    self.assertEqual(address, self.address)
                    self.assertEqual(actual_pvd, pvd)
                    self.assertEqual(struct.unpack_from("<I", result, 8)[0], address)
                    self.assertEqual(struct.unpack_from("<I", result, prepare_browser.CACHE_TARGET_OFFSET)[0], self.address + 4)
                    self.assertEqual(result[len(self.raw):], self.shim)
                    restored = bytearray(result[:len(self.raw)])
                    for offset, size in ((0, 12), (prepare_browser.CACHE_TARGET_OFFSET, 4),
                                         (prepare_browser.PVD_OFFSET, 4)):
                        restored[offset:offset + size] = self.raw[offset:offset + size]
                    self.assertEqual(bytes(restored), self.raw)

    def test_unexpected_cache_target_is_rejected(self):
        changed = bytearray(self.raw)
        struct.pack_into("<I", changed, prepare_browser.CACHE_TARGET_OFFSET, 0x8C1DC364)
        with mock.patch.object(prepare_browser, "validate_source"):
            with self.assertRaisesRegex(ValueError, "cache target differs"):
                prepare_browser.inject_adapter(bytes(changed), self.shim, "audio-data",
                                               hardware_startup=True, cache_entry=self.address + 4)

    def test_cache_entry_outside_appended_shim_is_rejected(self):
        for entry in (self.address - 4, self.address + len(self.shim), 0xAC007000):
            with self.subTest(entry=hex(entry)), mock.patch.object(prepare_browser, "validate_source"):
                with self.assertRaisesRegex(ValueError, "outside the appended shim"):
                    prepare_browser.inject_adapter(self.raw, self.shim, "audio-data",
                                                   hardware_startup=True, cache_entry=entry)

    def test_invalid_cache_entry_alias_is_rejected(self):
        for entry in (self.address + 1, 0xEC2BD8E8, None):
            with self.subTest(entry=entry), mock.patch.object(prepare_browser, "validate_source"):
                with self.assertRaises(ValueError):
                    prepare_browser.inject_adapter(self.raw, self.shim, "audio-data",
                                                   hardware_startup=True, cache_entry=entry)

    def prepare_with_fake_tools(self, folder, hardware_startup, shim=None):
        source, tools = folder / "browser", folder / "tools"
        source.mkdir()
        tools.mkdir()
        (source / "1ST_READ.BIN").write_bytes(self.raw)
        for name in ("boot_shim.S", "boot_shim_hardware.S", "framebuffer_checkpoint.S", "override.S"):
            (tools / name).write_text(f"; fixture {name}\n", encoding="utf-8")
        commands = []

        def run(command, capture=False):
            commands.append(command)
            if command[0].endswith("objcopy"):
                Path(command[-1]).write_bytes(self.shim if shim is None else shim)
            elif command[0].endswith("nm"):
                return f"{self.address + 4:08x} T _shim_cache_entry"
            elif "--version" in command:
                return "GNU assembler fixture"

        runner = mock.Mock()
        runner.path.side_effect = lambda path: str(path)
        runner.run.side_effect = run
        with mock.patch.object(prepare_browser, "__file__", str(tools / "prepare_browser.py")), \
                mock.patch.object(prepare_browser, "validate_source"):
            manifest = prepare_browser.prepare_browser(source, folder / "adapted.bin",
                                                       shim_path=tools / "override.S" if hardware_startup else None,
                                                       runner=runner, toolchain_prefix="sh-elf-",
                                                       hardware_startup=hardware_startup)
        return manifest, commands, tools

    def test_hardware_tools_include_standard_helper_and_guarded_literal_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            manifest, commands, tools = self.prepare_with_fake_tools(folder, True)
            assembler = [command for command in commands if command[0] == "sh-elf-as" and "--version" not in command]
            self.assertEqual(len(assembler), 2)
            self.assertIn("VMU_FULL_GD_SETUP=1", assembler[0])
            self.assertEqual(assembler[0][-1], str(tools / "override.S"))
            self.assertEqual(assembler[1][-1], str(tools / "framebuffer_checkpoint.S"))
            linker = next(command for command in commands if command[0] == "sh-elf-ld")
            self.assertEqual([Path(path).name for path in linker[-2:]], ["shim.o", "checkpoint.o"])
            objcopy = next(command for command in commands if command[0] == "sh-elf-objcopy")
            self.assertEqual(objcopy[1:5], ["-j", ".text", "-O", "binary"])
            self.assertEqual(manifest["startup_mode"], "hardware")
            self.assertEqual(manifest["framebuffer_checkpoint_source_sha256"], prepare_browser.sha256(tools / "framebuffer_checkpoint.S"))
            self.assertEqual(manifest["cache_entry_patch"]["literal_offset"], "0x2c")
            self.assertEqual(manifest["cache_entry_patch"]["original_target"], "0x8c1dc360")
            self.assertEqual(manifest["cache_entry_patch"]["p2_target"], hex(self.address + 4))

    def test_minimal_mode_keeps_cache_literal_and_compiles_only_original_shim(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            manifest, commands, tools = self.prepare_with_fake_tools(folder, False)
            assembler = [command for command in commands if command[0] == "sh-elf-as" and "--version" not in command]
            self.assertEqual(len(assembler), 1)
            self.assertIn("VMU_FULL_GD_SETUP=0", assembler[0])
            self.assertEqual(assembler[0][-1], str(tools / "boot_shim.S"))
            self.assertFalse(any(command[0] == "sh-elf-nm" for command in commands))
            result = (folder / "adapted.bin").read_bytes()
            self.assertEqual(result[prepare_browser.CACHE_TARGET_OFFSET:prepare_browser.CACHE_TARGET_OFFSET + 4],
                             self.raw[prepare_browser.CACHE_TARGET_OFFSET:prepare_browser.CACHE_TARGET_OFFSET + 4])
            self.assertEqual(manifest["startup_mode"], "minimal")
            self.assertIsNone(manifest["cache_entry_patch"])
            self.assertIsNone(manifest["framebuffer_checkpoint_source"])

    def test_oversize_shim_is_rejected_before_binary_read(self):
        original_read = Path.read_bytes

        def read(path):
            if path.name == "shim.bin":
                self.fail("Oversize shim must be rejected before reading it")
            return original_read(path)

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(Path, "read_bytes", read):
            folder = Path(directory)
            with self.assertRaisesRegex(ValueError, "exceeds 8192 bytes"):
                self.prepare_with_fake_tools(folder, True, shim=b"\0" * 8196)
            self.assertFalse((folder / "adapted.bin").exists())
            self.assertFalse((folder / "adapted.manifest.json").exists())

    def test_missing_linked_cache_symbol_is_rejected(self):
        runner = mock.Mock()
        runner.path.side_effect = str
        runner.run.return_value = "ac2bd8e4 T _shim_start"
        with self.assertRaisesRegex(ValueError, "exactly one linked _shim_cache_entry"):
            prepare_browser.linked_symbol(runner, "sh-elf-", Path("shim.elf"), "_shim_cache_entry")


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
