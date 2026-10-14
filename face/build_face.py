#!/usr/bin/env python3
"""Build the isolated FACECHAN variant without rewriting legacy artifacts.

Usage: python face/build_face.py OUTPUT_DIR
The original build_vms module supplies assemble() only. Its asset/source
generation entry points are never called. The date is fixed for reproducible
VMI metadata; all generated target names must be absent before building.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from art import generate

GENERATED_FILES = (
    "FACECHAN.VMS", "FACECHAN.VMI", "face.s", "frames.bin", "icon.bin",
    "icon.png", "symbols.json", "manifest.json", "face.png", "preview.gif",
    "neutral.png", "blink.png",
)


def make_vmi(vms: bytes) -> bytes:
    """Make an unprotected game VMI for resource and VMU filename FACECHAN."""
    resource = b"FACECHAN"
    result = bytearray(108)
    result[0:4] = bytes(a & b for a, b in zip(resource[:4], b"SEGA"))
    result[4:36] = b"Face-only VMU companion".ljust(32, b"\0")
    result[36:68] = b"ebazchan / M5Stack-Avatar face".ljust(32, b"\0")
    date = datetime.datetime(2026, 10, 15)
    struct.pack_into("<HBBBBBB", result, 0x44, date.year, date.month, date.day,
                     0, 0, 0, (date.weekday()+1) % 7)
    struct.pack_into("<HH", result, 0x4c, 0, 1)
    result[0x50:0x58] = resource
    result[0x58:0x64] = resource.ljust(12, b"\0")
    struct.pack_into("<H", result, 0x64, 2)
    struct.pack_into("<I", result, 0x68, len(vms))
    return bytes(result)


def _byte_lines(data: bytes) -> str:
    return "\n".join("    .byte " + ", ".join(f"${b:02X}" for b in data[i:i+16])
                     for i in range(0, len(data), 16))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(output_dir: Path | str) -> dict:
    output_dir = Path(output_dir).resolve()
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(f"Output is not a directory: {output_dir}")
    collisions = [name for name in GENERATED_FILES if (output_dir/name).exists()]
    if collisions:
        raise FileExistsError("Refusing to overwrite generated targets: " + ", ".join(collisions))
    # Import for assemble() and its register map only. Neither legacy generation
    # function is called, so legacy files remain untouched.
    spec = importlib.util.spec_from_file_location("face_parent_assembler", ROOT/"build_vms.py")
    assembler = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(assembler)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="facechan-", dir=output_dir.parent) as temporary:
        staging = Path(temporary)
        art = generate(staging)
        frames = (staging/"frames.bin").read_bytes()
        icon = (staging/"icon.bin").read_bytes()
        if len(frames) != 384 or len(icon) != 512:
            raise ValueError("Face assets have unexpected dimensions")
        palette = b"".join(struct.pack("<H", colour)
                           for colour in [0xf000, 0xffff] + [0xf000]*14)
        substitutions = {
            "@REGS@": "\n".join(f"{name} = ${address:03X}"
                                  for name, address in sorted(assembler.SFR.items())),
            "@PALETTE@": _byte_lines(palette),
            "@ICON@": _byte_lines(icon),
            "@POINTERS@": "    .word frame00,frame01",
            "@FRAMES@": "\n\n".join(
                f"frame{i:02}:\n" + _byte_lines(frames[i*192:(i+1)*192])
                for i in range(2)),
        }
        source = (HERE/"face.s.in").read_text(encoding="utf-8")
        for marker, content in substitutions.items():
            if source.count(marker) != 1:
                raise ValueError(f"Expected exactly one template marker: {marker}")
            source = source.replace(marker, content)
        binary, symbols = assembler.assemble(source)
        if not (len(binary) % 512 == 0 and symbols["start"] == 0x480
                and binary[:3] == bytes((0x21, 0x04, 0x80))
                and binary[0x200:0x210].startswith(b"FACECHAN")
                and binary[0x280:0x480] == icon
                and binary[symbols["frame00"]:symbols["frame00"]+384] == frames
                and symbols["frame01"] == symbols["frame00"]+192):
            raise ValueError("Assembled game layout failed its build invariants")
        (staging/"FACECHAN.VMS").write_bytes(binary)
        (staging/"FACECHAN.VMI").write_bytes(make_vmi(binary))
        (staging/"face.s").write_text(source, encoding="utf-8", newline="\n")
        (staging/"symbols.json").write_text(json.dumps(symbols, indent=2, sort_keys=True)+"\n",
                                            encoding="utf-8", newline="\n")
        manifest = {
            "variant": "FACECHAN", "build_date": "2026-10-15",
            "format": "Standalone LC86K VMU game, not a Dreamcast executable",
            "resource_name": "FACECHAN", "vmu_filename": "FACECHAN",
            "game_flag": 2, "vms_bytes": len(binary), "vmu_blocks": len(binary)//512,
            "layout": {"vectors": 0, "header": 0x200, "icon": 0x280, "start": 0x480},
            "runtime": {"phase_count": 16, "open_phases": list(range(14)),
                        "closed_phases": [14, 15], "controls": "MODE/SLEEP/dock exit retained; A/B/D-pad ignored",
                        "delay": "original wait_frame instructions unchanged; elapsed timing unmeasured"},
            "art": art,
            "provenance": {
                "reference": "ebazchan procedural neutral face",
                "upstream": "https://github.com/stack-chan/m5stack-avatar",
                "copyright": "Copyright (c) 2018 Shinya Ishikawa",
                "license": "MIT; see distributed THIRD_PARTY_NOTICES.txt",
                "low_level_runtime": "Existing console-tested VMU variant; Serpent/VMUPet methods retained",
            },
            "source_sha256": {name: _sha(path.read_bytes()) for name, path in (
                ("face.s.in", HERE/"face.s.in"), ("art.py", HERE/"art.py"),
                ("build_face.py", HERE/"build_face.py"), ("parent_build_vms.py", ROOT/"build_vms.py"))},
            "files": {name: {"bytes": (staging/name).stat().st_size,
                             "sha256": _sha((staging/name).read_bytes())}
                      for name in GENERATED_FILES if name != "manifest.json"},
            "hardware_validation": "pending; legacy variant has booted on user hardware",
        }
        (staging/"manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n",
                                             encoding="utf-8", newline="\n")
        output_dir.mkdir(parents=True, exist_ok=True)
        for name in GENERATED_FILES:
            with (output_dir/name).open("xb") as target:
                target.write((staging/name).read_bytes())
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    arguments = parser.parse_args(argv)
    try:
        manifest = build(arguments.output_dir)
    except (OSError, ValueError) as error:
        parser.exit(1, f"FACECHAN build failed: {error}\n")
    print(json.dumps({"output_dir": str(arguments.output_dir.resolve()),
                      "vms_bytes": manifest["vms_bytes"],
                      "sha256": manifest["files"]["FACECHAN.VMS"]["sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
