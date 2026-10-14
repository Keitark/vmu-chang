#!/usr/bin/env python3
"""Bounded artifact and LC86K checks: python face/test_face.py BUILD_DIR.

Reuses the independent legacy interpreter in this process only. Its RAM model
does not emulate real sleep, interrupts, LCD scan timing, or firmware banking;
the sleep and exit tests therefore check machine-code control flow only.
"""

from pathlib import Path
import argparse
import json
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import smoke_test


BUILD_DIR = None
ROM = b""
FRAMES = b""
SYMBOLS = {}
FRAME_BYTES = 192
FRAME = 0x20
P3 = 0x14C
P7 = 0x15C
VCCR = 0x127
PCON = 0x107
EXT = 0x10D
INSTRUCTION_LIMIT = 100000


def configure(build_dir):
    global BUILD_DIR, ROM, FRAMES, SYMBOLS
    BUILD_DIR = Path(build_dir).resolve()
    ROM = (BUILD_DIR / "FACECHAN.VMS").read_bytes()
    FRAMES = (BUILD_DIR / "frames.bin").read_bytes()
    SYMBOLS = json.loads((BUILD_DIR / "symbols.json").read_text())
    # CPU.fetch/ldc resolve their globals in smoke_test, not in this module.
    smoke_test.ROM = ROM
    smoke_test.FRAMES = FRAMES
    smoke_test.SYM = SYMBOLS


class FaceArtifactTests(unittest.TestCase):
    def test_game_layout_has_reset_header_icon_and_entry_at_contract_offsets(self):
        self.assertEqual(len(ROM) % 512, 0)
        self.assertEqual(SYMBOLS["start"], 0x480)
        self.assertEqual(ROM[:3], b"\x21\x04\x80")
        self.assertEqual(ROM[0x200:0x210], b"FACECHAN".ljust(16, b" "))
        self.assertEqual(struct.unpack_from("<H", ROM, 0x240)[0], 1)
        icon = (BUILD_DIR / "icon.bin").read_bytes()
        self.assertEqual(len(icon), 512)
        self.assertEqual(ROM[0x280:0x480], icon)

    def test_vmi_identifies_an_unprotected_game_and_actual_vms_length(self):
        vmi = (BUILD_DIR / "FACECHAN.VMI").read_bytes()
        self.assertEqual(len(vmi), 108)
        self.assertEqual(vmi[0x50:0x58], b"FACECHAN")
        self.assertEqual(struct.unpack_from("<H", vmi, 0x64)[0], 2)
        self.assertEqual(struct.unpack_from("<I", vmi, 0x68)[0], len(ROM))

    def test_two_frame_pointer_entries_address_the_exact_art_bytes(self):
        self.assertEqual(len(FRAMES), 2 * FRAME_BYTES)
        self.assertNotEqual(FRAMES[:FRAME_BYTES], FRAMES[FRAME_BYTES:])
        table = SYMBOLS["frame_table"]
        pointers = struct.unpack_from("<HH", ROM, table)
        self.assertEqual(pointers, (SYMBOLS["frame00"], SYMBOLS["frame01"]))
        for index, address in enumerate(pointers):
            with self.subTest(frame=index):
                self.assertEqual(ROM[address:address + FRAME_BYTES],
                                 FRAMES[index * FRAME_BYTES:(index + 1) * FRAME_BYTES])


class FaceMachineTests(unittest.TestCase):
    def run_to(self, cpu, label, *, step_first=False, budget=INSTRUCTION_LIMIT):
        target = SYMBOLS[label]
        if step_first:
            cpu.step()
        for _ in range(budget):
            if cpu.pc == target:
                return
            cpu.step()
        self.fail(f"Did not reach {label} within {budget} instructions; pc=0x{cpu.pc:04x}")

    def ready_cpu(self):
        cpu = smoke_test.CPU()
        self.run_to(cpu, "main_loop")
        return cpu

    def assert_frame(self, cpu, number):
        selected = 0 if number % 16 < 14 else 1
        self.assertEqual(cpu.r(FRAME), selected,
                         f"wrong selected face at displayed frame {number}")
        self.assertEqual(cpu.lcd(), FRAMES[selected * FRAME_BYTES:(selected + 1) * FRAME_BYTES],
                         f"LCD RAM differs from the complete face at displayed frame {number}")

    def assert_ignored_action(self, key):
        cpu = self.ready_cpu()
        for frame in range(64):
            # Press just before each blink, hold across the blink and wrap, then
            # release. Resetting the blink phase would visibly fail this check.
            cpu.current_key = key if 13 <= frame % 32 < 22 else 0xFF
            self.run_to(cpu, "wait_frame")
            self.assert_frame(cpu, frame)
            self.run_to(cpu, "main_loop", step_first=True)

    def assert_firmware_exit(self, cpu):
        self.run_to(cpu, "goodbye")
        before = cpu.r(EXT)
        cpu.step()
        self.assertEqual(cpu.r(EXT), before ^ 1,
                         "exit must toggle firmware bank control EXT bit 0")

    def test_reset_reaches_the_complete_open_face_before_the_first_delay(self):
        cpu = smoke_test.CPU()
        self.run_to(cpu, "wait_frame")
        self.assert_frame(cpu, 0)
        self.assertEqual(cpu.r(VCCR), 0x80)

    def test_64_displayed_frames_repeat_14_open_then_2_closed(self):
        cpu = self.ready_cpu()
        for frame in range(64):
            self.run_to(cpu, "wait_frame")
            self.assert_frame(cpu, frame)
            self.run_to(cpu, "main_loop", step_first=True)

    def test_a_is_ignored_without_resetting_the_blink(self):
        self.assert_ignored_action(0xEF)

    def test_b_is_ignored_without_resetting_the_blink(self):
        self.assert_ignored_action(0xDF)

    def test_up_is_ignored_without_resetting_the_blink(self):
        self.assert_ignored_action(0xFE)

    def test_down_is_ignored_without_resetting_the_blink(self):
        self.assert_ignored_action(0xFD)

    def test_left_is_ignored_without_resetting_the_blink(self):
        self.assert_ignored_action(0xFB)

    def test_right_is_ignored_without_resetting_the_blink(self):
        self.assert_ignored_action(0xF7)

    def test_all_six_action_keys_are_ignored_together(self):
        self.assert_ignored_action(0xC0)

    def test_mode_active_low_takes_the_firmware_exit_path(self):
        cpu = self.ready_cpu()
        cpu.current_key = 0xBF
        self.assert_firmware_exit(cpu)

    def test_docking_takes_the_firmware_exit_path(self):
        cpu = self.ready_cpu()
        cpu.w(P7, 1)
        self.assert_firmware_exit(cpu)

    def enter_sleep_flow(self):
        cpu = self.ready_cpu()
        cpu.current_key = 0x7F
        self.run_to(cpu, "keys_sleep")
        return cpu

    def test_sleep_flow_waits_for_button_release_before_disabling_the_lcd(self):
        cpu = self.enter_sleep_flow()
        for _ in range(20):
            cpu.step()
            self.assertEqual(cpu.pc, SYMBOLS["keys_sleep"])
            self.assertEqual(cpu.r(VCCR), 0x80)
        cpu.current_key = 0xFF
        self.run_to(cpu, "sleep_more")
        self.assertEqual(cpu.r(VCCR), 0)

    def test_sleep_flow_sets_pcon_and_keeps_the_lcd_off_until_wake_press(self):
        cpu = self.enter_sleep_flow()
        cpu.current_key = 0xFF
        self.run_to(cpu, "sleep_more")
        self.run_to(cpu, "sleep_more", step_first=True, budget=20)
        self.assertEqual(cpu.r(PCON) & 1, 1)
        self.assertEqual(cpu.r(VCCR), 0)

    def test_sleep_flow_restores_the_lcd_and_waits_for_wake_button_release(self):
        cpu = self.enter_sleep_flow()
        cpu.current_key = 0xFF
        self.run_to(cpu, "sleep_more")
        cpu.current_key = 0x7F
        self.run_to(cpu, "sleep_release")
        self.assertEqual(cpu.r(VCCR), 0x80)
        for _ in range(20):
            cpu.step()
            self.assertEqual(cpu.pc, SYMBOLS["sleep_release"])
        cpu.current_key = 0xFF
        self.run_to(cpu, "wait_frame")
        self.assert_frame(cpu, 0)

    def test_docking_during_sleep_flow_takes_the_firmware_exit_path(self):
        cpu = self.enter_sleep_flow()
        cpu.current_key = 0xFF
        self.run_to(cpu, "sleep_more")
        cpu.w(P7, 1)
        self.assert_firmware_exit(cpu)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_dir", type=Path)
    args = parser.parse_args()
    configure(args.build_dir)
    print(f"Testing artifacts in {BUILD_DIR}", flush=True)
    print("Sleep/exit checks cover bounded code flow only; real power, IRQ, firmware "
          "banking and LCD timing are not emulated.", flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
