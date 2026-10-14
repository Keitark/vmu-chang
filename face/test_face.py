#!/usr/bin/env python3
"""Bounded artifact and LC86K checks: python face/test_face.py BUILD_DIR.

Reuses the independent legacy interpreter in this process only. Its RAM model
does not emulate real sleep, interrupts, LCD scan timing, or firmware banking;
the sleep and exit tests therefore check machine-code control flow only.
"""

from pathlib import Path
import argparse
import hashlib
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
ANIMATION = {}
FRAME_BYTES = 192
FRAME = 0x20
PHASE = 0x21
P3 = 0x14C
P7 = 0x15C
VCCR = 0x127
PCON = 0x107
EXT = 0x10D
INSTRUCTION_LIMIT = 100000
EXPRESSIONS = ("neutral", "happy", "angry", "sad", "sleepy", "doubt")
POSE_SCHEDULE = (("rest", 8), ("blink", 2), ("lookleft", 4),
                 ("lookright", 4), ("mouthquarter", 2), ("mouthhalf", 2),
                 ("mouthfull", 2), ("mouthhalf", 2), ("mouthquarter", 2),
                 ("rest", 4))


def configure(build_dir):
    global BUILD_DIR, ROM, FRAMES, SYMBOLS, ANIMATION
    BUILD_DIR = Path(build_dir).resolve()
    ROM = (BUILD_DIR / "FACECHAN.VMS").read_bytes()
    FRAMES = (BUILD_DIR / "frames.bin").read_bytes()
    SYMBOLS = json.loads((BUILD_DIR / "symbols.json").read_text())
    ANIMATION = json.loads((BUILD_DIR / "animation.json").read_text())
    # CPU.fetch/ldc resolve their globals in smoke_test, not in this module.
    smoke_test.ROM = ROM
    smoke_test.FRAMES = FRAMES
    smoke_test.SYM = SYMBOLS


def sprite_bytes(index):
    return FRAMES[index * FRAME_BYTES:(index + 1) * FRAME_BYTES]


def pose_frame(expression, pose):
    matches = [sprite["id"] for sprite in ANIMATION["sprites"]
               if any(item["expression"] == expression and item["pose"] == pose
                      for item in sprite["poses"])]
    if len(matches) != 1:
        raise AssertionError(f"Expected one sprite for {expression}/{pose}; found {matches}")
    return sprite_bytes(matches[0])


def mouth_size(frame):
    # The lower LCD half contains the mouth; eyes occupy the upper half.
    # A zero bit is a clear feature on the dark field. Measure the resulting
    # bitmap, without reproducing the procedural art's shape calculations.
    pixels = [(x, y) for y in range(16, 32) for x in range(48)
              if not frame[y * 6 + x // 8] & (0x80 >> (x % 8))]
    if not pixels:
        raise AssertionError("Mouth has no visible pixels")
    xs, ys = zip(*pixels)
    return max(xs) - min(xs) + 1, max(ys) - min(ys) + 1


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

    def test_dynamic_frame_pointers_address_every_complete_art_sprite(self):
        self.assertEqual(len(FRAMES) % FRAME_BYTES, 0)
        count = len(FRAMES) // FRAME_BYTES
        self.assertGreater(count, 1)
        self.assertLessEqual(count, 127)
        table = SYMBOLS["frame_table"]
        pointers = struct.unpack_from(f"<{count}H", ROM, table)
        for index, address in enumerate(pointers):
            with self.subTest(frame=index):
                self.assertEqual(address, SYMBOLS[f"frame{index:02}"])
                self.assertEqual(ROM[address:address + FRAME_BYTES],
                                 sprite_bytes(index))

    def test_timeline_has_six_expressions_in_order_for_32_ticks_each(self):
        self.assertEqual(ANIMATION["expressions"], list(EXPRESSIONS))
        self.assertEqual(ANIMATION["ticks_per_expression"], 32)
        self.assertEqual(ANIMATION["expression_labels"],
                         [expression for expression in EXPRESSIONS for _ in range(32)])

    def test_each_expression_uses_the_required_pose_durations(self):
        self.assertEqual([(item["pose"], item["ticks"]) for item in ANIMATION["segments"]],
                         list(POSE_SCHEDULE))
        poses = [pose for pose, ticks in POSE_SCHEDULE for _ in range(ticks)]
        self.assertEqual(ANIMATION["phase_states"], poses * len(EXPRESSIONS))

    def test_rom_timeline_matches_192_valid_declared_frame_ids(self):
        timeline = ANIMATION["frame_ids"]
        self.assertEqual(len(timeline), 192)
        count = len(FRAMES) // FRAME_BYTES
        self.assertTrue(all(type(index) is int and 0 <= index < count for index in timeline))
        address = SYMBOLS["animation_table"]
        self.assertEqual(ROM[address:address + 192], bytes(timeline))

    def test_sprite_metadata_binds_each_timeline_pose_to_its_actual_bitmap(self):
        sprites = ANIMATION["sprites"]
        count = len(FRAMES) // FRAME_BYTES
        self.assertEqual([sprite["id"] for sprite in sprites], list(range(count)))
        for sprite in sprites:
            with self.subTest(sprite=sprite["id"]):
                self.assertEqual(hashlib.sha256(sprite_bytes(sprite["id"])).hexdigest(),
                                 sprite["sha256"])
        for tick, frame_id in enumerate(ANIMATION["frame_ids"]):
            with self.subTest(tick=tick):
                self.assertEqual(pose_frame(ANIMATION["expression_labels"][tick],
                                            ANIMATION["phase_states"][tick]),
                                 sprite_bytes(frame_id))

    def test_happy_angry_sad_and_sleepy_are_distinct_at_the_same_rest_pose(self):
        faces = [pose_frame(expression, "rest") for expression in EXPRESSIONS[:5]]
        self.assertEqual(len(set(faces)), 5)

    def test_doubt_matches_neutral_for_all_poses_and_documents_the_source_alias(self):
        self.assertEqual(ANIMATION["expression_aliases"]["doubt"], "neutral")
        for pose in {pose for pose, _ in POSE_SCHEDULE}:
            with self.subTest(pose=pose):
                self.assertEqual(pose_frame("doubt", pose), pose_frame("neutral", pose))

    def test_full_open_mouth_is_narrower_and_taller_than_the_closed_mouth(self):
        rest_width, rest_height = mouth_size(pose_frame("neutral", "rest"))
        open_width, open_height = mouth_size(pose_frame("neutral", "mouthfull"))
        self.assertLess(open_width, rest_width)
        self.assertGreater(open_height, rest_height)


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
        phase = number % 192
        selected = ANIMATION["frame_ids"][phase]
        self.assertEqual(cpu.r(PHASE), phase,
                         f"wrong animation phase at displayed frame {number}")
        self.assertEqual(cpu.r(FRAME), selected,
                         f"wrong selected face at displayed frame {number}")
        self.assertEqual(cpu.lcd(), sprite_bytes(selected),
                         f"LCD RAM differs from the complete face at displayed frame {number}")

    def assert_firmware_exit(self, cpu):
        self.run_to(cpu, "goodbye")
        before = cpu.r(EXT)
        cpu.step()
        self.assertEqual(cpu.r(EXT), before ^ 1,
                         "exit must toggle firmware bank control EXT bit 0")

    def test_reset_reaches_the_complete_neutral_rest_face_before_the_first_delay(self):
        cpu = smoke_test.CPU()
        self.run_to(cpu, "wait_frame")
        self.assert_frame(cpu, 0)
        self.assertEqual(cpu.r(VCCR), 0x80)

    def test_two_full_cycles_and_wrap_render_every_pose_despite_varied_action_keys(self):
        cpu = self.ready_cpu()
        actions = (0xFF, 0xEF, 0xDF, 0xFE, 0xFD, 0xFB, 0xF7, 0xC0)
        seen_actions = set()
        seen_poses = set()
        # First cycle has no input; the second presses, holds and releases all
        # six action keys and their combination across pose and expression edges.
        for frame in range(385):
            key = 0xFF if frame < 192 else actions[(frame // 5) % len(actions)]
            cpu.current_key = key
            seen_actions.add(key)
            self.run_to(cpu, "wait_frame")
            self.assert_frame(cpu, frame)
            phase = frame % 192
            seen_poses.add((ANIMATION["expression_labels"][phase],
                            ANIMATION["phase_states"][phase]))
            self.run_to(cpu, "main_loop", step_first=True)
        self.assertEqual(seen_actions, set(actions))
        self.assertEqual(seen_poses,
                         {(expression, pose) for expression in EXPRESSIONS
                          for pose, _ in POSE_SCHEDULE})

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
