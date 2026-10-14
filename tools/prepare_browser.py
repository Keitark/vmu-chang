"""Adapt a user-supplied VMU Disc Builder browser for the BOING bootstrap.

Example (Windows with Ubuntu WSL and the existing pinned SH toolchain):
  python tools/prepare_browser.py EXTRACTED_BROWSER adapted.bin --layout audio-data

No third-party browser binary is distributed here. This tool accepts only the
audited raw executable, injects boot_shim.S, and records hashes. It does not burn
a CD or establish physical Dreamcast compatibility.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

SOURCE_SHA256 = "f43d637858be93cef87da0fd9045e9cf8c1ef9a288bb15b808bee360fb997b1e"
SOURCE_BYTES = 2808036
PVD_OFFSET = 0x282CF0
SOURCE_PVD_FAD = 166
SESSION_LBAS = {"audio-data": 11702, "data-data": 0}
DEFAULT_TOOLCHAIN = "/root/.cache/boing-overdrive/dc/sdk-gcc15.1.0-kos2.2.1/sh-elf/bin/sh-elf-"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def refuse_existing(paths):
    for path in paths:
        if Path(path).exists():
            raise FileExistsError(f"Refusing to overwrite {path}")


class ToolRunner:
    """Run native or WSL tools using argument arrays, without shell evaluation."""

    def __init__(self, native=False, distro="Ubuntu", user="root", log=None):
        self.use_wsl = os.name == "nt" and not native
        self.prefix = ["wsl.exe", "-d", distro, "-u", user, "--"] if self.use_wsl else []
        self.log = log

    def path(self, path):
        path = Path(path).resolve()
        if not self.use_wsl:
            return str(path)
        # All local build inputs must be drive paths accessible through /mnt.
        if len(path.drive) != 2 or path.drive[1] != ":":
            raise ValueError(f"WSL path conversion requires a local drive path: {path}")
        return "/mnt/" + path.drive[0].lower() + "/" + path.as_posix()[3:]

    def run(self, args, capture=False, include_stderr=False):
        command = self.prefix + [str(arg) for arg in args]
        if self.log:
            self.log.write(subprocess.list2cmdline(command) + "\n")
            self.log.flush()
        if capture:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            if self.log:
                self.log.write(result.stdout + result.stderr)
                self.log.flush()
            return ((result.stderr if include_stderr else "") + result.stdout).strip()
        subprocess.run(command, check=True, stdout=self.log,
                       stderr=subprocess.STDOUT if self.log else None)


def validate_source(raw):
    actual = hashlib.sha256(raw).hexdigest()
    if len(raw) != SOURCE_BYTES or actual != SOURCE_SHA256:
        raise ValueError("Unsupported browser executable: expected the audited raw "
                         f"1ST_READ.BIN ({SOURCE_BYTES} bytes, SHA-256 {SOURCE_SHA256}); "
                         f"got {len(raw)} bytes, SHA-256 {actual}")
    if raw[:12] != b"\x09\x00" * 6:
        raise ValueError("Browser entry does not contain the expected six NOPs")
    if struct.unpack_from("<I", raw, PVD_OFFSET)[0] != SOURCE_PVD_FAD:
        raise ValueError("Browser PVD address differs from the audited original")


def inject_adapter(raw, shim, layout):
    """Patch the audited executable, preserving every byte outside two patches."""
    validate_source(raw)
    if not shim or len(shim) % 4:
        raise ValueError("The assembled shim must be nonempty and 4-byte aligned")
    if layout not in SESSION_LBAS:
        raise ValueError(f"Unsupported layout {layout}")
    result = bytearray(raw)
    address = 0xAC010000 + len(raw)
    result[:12] = bytes.fromhex("01d02b4009000900") + struct.pack("<I", address)
    pvd_fad = SOURCE_PVD_FAD + SESSION_LBAS[layout]
    if layout == "audio-data":
        struct.pack_into("<I", result, PVD_OFFSET, pvd_fad)
    result.extend(shim)
    return bytes(result), address, pvd_fad


def prepare_browser(browser_dir, output, layout="audio-data", shim_path=None,
                    runner=None, toolchain_prefix=DEFAULT_TOOLCHAIN):
    browser_dir, output = Path(browser_dir).resolve(), Path(output).resolve()
    source = browser_dir / "1ST_READ.BIN"
    shim_path = Path(shim_path or Path(__file__).with_name("boot_shim.S")).resolve()
    manifest_path = output.with_suffix(".manifest.json")
    refuse_existing([output, manifest_path])
    raw = source.read_bytes()
    validate_source(raw)
    if not shim_path.is_file():
        raise FileNotFoundError(f"Missing shim source: {shim_path}")
    runner = runner or ToolRunner()
    address = 0xAC010000 + len(raw)
    with tempfile.TemporaryDirectory(prefix="vmu-browser-") as directory:
        scratch = Path(directory)
        obj, elf, binary = (scratch / name for name in ("shim.o", "shim.elf", "shim.bin"))
        runner.run([toolchain_prefix + "as", "-little", "-isa=sh4", "--defsym",
                    "VMU_FULL_GD_SETUP=0", "-o", runner.path(obj), runner.path(shim_path)])
        runner.run([toolchain_prefix + "ld", "-EL", "-Ttext", hex(address),
                    "-e", "_shim_start", "-o", runner.path(elf), runner.path(obj)])
        runner.run([toolchain_prefix + "objcopy", "-O", "binary", "-j", ".text",
                    runner.path(elf), runner.path(binary)])
        shim = binary.read_bytes()
    adapted, address, pvd_fad = inject_adapter(raw, shim, layout)
    manifest = {
        "source": str(source), "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_bytes": len(raw), "layout": layout,
        "session_lba": SESSION_LBAS[layout], "pvd_fad": pvd_fad,
        "pvd_patch_offset": hex(PVD_OFFSET), "entry_patch_bytes": adapted[:12].hex(),
        "shim_source": str(shim_path), "shim_source_sha256": sha256(shim_path),
        "shim_address": hex(address), "shim_bytes": len(shim),
        "shim_sha256": hashlib.sha256(shim).hexdigest(),
        "toolchain_prefix": toolchain_prefix,
        "toolchain_version": runner.run([toolchain_prefix + "as", "--version"], capture=True).splitlines()[0],
        "output": str(output), "output_bytes": len(adapted),
        "output_sha256": hashlib.sha256(adapted).hexdigest(),
        "flycast_boot": "pending", "physical_boot": "pending bench test",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(adapted)
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    return manifest


def add_tool_arguments(parser):
    parser.add_argument("--toolchain-prefix", default=DEFAULT_TOOLCHAIN)
    parser.add_argument("--shim", type=Path, help="Override tools/boot_shim.S")
    parser.add_argument("--native", action="store_true", help="Use native tools instead of WSL on Windows")
    parser.add_argument("--wsl-distro", default="Ubuntu")
    parser.add_argument("--wsl-user", default="root")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("browser_dir", type=Path, help="Extracted browser files, including raw 1ST_READ.BIN")
    parser.add_argument("output", type=Path, help="New adapted raw .bin file; existing files are preserved")
    parser.add_argument("--layout", choices=SESSION_LBAS, default="audio-data")
    add_tool_arguments(parser)
    args = parser.parse_args()
    try:
        manifest = prepare_browser(args.browser_dir, args.output, args.layout, args.shim,
                                   ToolRunner(args.native, args.wsl_distro, args.wsl_user),
                                   args.toolchain_prefix)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Preparation failed: {error}\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
