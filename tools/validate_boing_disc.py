#!/usr/bin/env python3
"""Validate a mkdcdisc Audio/Data CDI against BOING and the VMU source files.

Uses only the Python standard library. Reads the actual CDI's session/track
descriptors and ISO payload, never the standalone base-zero ``mkdcdisc -I`` dump.
Structural success does not establish emulator or physical Dreamcast acceptance.
"""

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


CDI_MARKER = bytes.fromhex("000001000000ffffffff")
EXPECTED_VMI_SHA256 = "95a9d009a13be7e7deb955916e0ec767f451a892803421467eca8339fd7f070b"
EXPECTED_VMS_SHA256 = "a353ad9a1d69ee535c6859672a512fac1c6f2b1286a2816dcf116be0516d36dc"
EXCLUDED = {"0.0", "IP.BIN", "1ST_READ.BIN"}


class InvalidImage(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidImage(message)


def u32(data, offset):
    require(offset >= 0 and offset + 4 <= len(data), "Truncated 32-bit field")
    return struct.unpack_from("<I", data, offset)[0]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def descramble(data):
    """Marcus Comstedt's public-domain Dreamcast 32-byte slice permutation.

    Compatible with mkdcdisc's third_party/scramble/scramble.cpp. The generator
    state is seeded once from total byte size and retained across all chunks.
    """
    output = bytearray(len(data))
    source = memoryview(data)
    seed = len(data) & 0xFFFF
    position = 0
    remaining = len(data)
    chunk_size = 2 * 1024 * 1024
    while chunk_size >= 32:
        while remaining >= chunk_size:
            indices = list(range(chunk_size // 32))
            slice_index = 0
            for index in range(len(indices) - 1, -1, -1):
                seed = (seed * 2109 + 9273) & 0x7FFF
                random_value = (seed + 0xC000) & 0xFFFF
                chosen = (random_value * index) >> 16
                indices[index], indices[chosen] = indices[chosen], indices[index]
                destination = position + 32 * indices[index]
                start = position + 32 * slice_index
                output[destination:destination + 32] = source[start:start + 32]
                slice_index += 1
            position += chunk_size
            remaining -= chunk_size
        chunk_size >>= 1
    output[position:] = source[position:]
    return bytes(output)


class CdiImage:
    """Read the CDI v3.5 descriptor layout emitted by mkdcdisc."""

    def __init__(self, path):
        self.path = path
        self.handle = path.open("rb")
        self.size = path.stat().st_size
        require(self.size >= 8, "CDI is too short")
        self.handle.seek(-4, 2)
        descriptor_size = u32(self.handle.read(4), 0)
        require(8 < descriptor_size < min(self.size, 64 * 1024 * 1024),
                "Invalid CDI descriptor size")
        self.descriptor_start = self.size - descriptor_size
        self.handle.seek(self.descriptor_start)
        header = self.handle.read(descriptor_size)
        require(u32(header, len(header) - 8) == 0x80000006,
                "Only mkdcdisc CDI v3.5 (0x80000006) is supported")
        self.session_count = header[0]
        require(1 <= self.session_count <= 99, "Invalid CDI session count")
        self.tracks = []
        position = 1
        physical_offset = 0
        for session in range(self.session_count):
            require(position + 7 <= len(header), "Truncated CDI session")
            count = struct.unpack_from("<H", header, position + 1)[0]
            require(1 <= count <= 99, "Invalid CDI track count")
            position += 7
            for track_index in range(count):
                require(header[position:position + 20] == CDI_MARKER * 2,
                        "Unsupported CDI track marker/header")
                position += 88
                length = 188 if track_index == count - 1 else 180
                require(position + length <= len(header), "Truncated CDI track")
                record = header[position:position + length]
                require(struct.unpack_from("<H", record)[0] == 2,
                        "Unexpected CDI index count")
                track = {name: u32(record, offset) for name, offset in [
                    ("pregap_sectors", 2), ("sector_count", 6),
                    ("mode", 16), ("session", 24), ("track", 28),
                    ("start_lba", 32), ("stored_sectors", 36),
                    ("read_mode", 56), ("control", 60),
                ]}
                require(track["session"] == session and track["track"] == track_index,
                        "CDI session/track numbering mismatch")
                require(track["stored_sectors"] == track["pregap_sectors"] + track["sector_count"],
                        "CDI stored-sector count mismatch")
                require(track["read_mode"] in (0, 1, 2), "Unsupported CDI sector format")
                stride = (2048, 2336, 2352)[track["read_mode"]]
                track.update(raw_sector_bytes=stride, file_offset=physical_offset)
                physical_offset += track["stored_sectors"] * stride
                self.tracks.append(track)
                position += length
        require(position + 7 + 88 + 79 + 4 == len(header),
                "Unexpected CDI trailing descriptor length")
        require(struct.unpack_from("<H", header, position + 1)[0] == 0,
                "Missing CDI terminator session")
        require(physical_offset == self.descriptor_start,
                "CDI physical track sizes disagree with descriptor start")
        data_tracks = [track for track in self.tracks if track["mode"] == 2]
        require(len(data_tracks) == 1, "Expected exactly one Mode2 data track")
        self.data_track = data_tracks[0]
        require(self.data_track["read_mode"] == 1 and self.data_track["control"] == 4,
                "Expected 2336-byte XA data sectors")
        self.msinfo = self.data_track["start_lba"]
        self.payload_offset = (self.data_track["file_offset"] +
                               self.data_track["pregap_sectors"] * 2336 + 8)
        self.ip_bin = self.read_extent(self.msinfo, 32768)
        self.pvd = self.read_extent(self.msinfo + 16, 2048)
        require(self.pvd[:7] == b"\x01CD001\x01", "Missing ISO primary volume descriptor")
        require(struct.unpack_from("<H", self.pvd, 128)[0] == 2048,
                "Unexpected ISO logical block size")
        self.root_extent = u32(self.pvd, 158)
        self.root_size = u32(self.pvd, 166)
        self.path_extent = u32(self.pvd, 140)
        table = self.read_extent(self.path_extent, 10)
        require(table[:2] == b"\x01\x00" and u32(table, 2) == self.root_extent,
                "Absolute ISO path-table/root extents do not match CDI session LBA")

    def close(self):
        self.handle.close()

    def read_extent(self, absolute_lba, size):
        require(size >= 0, "Negative ISO extent size")
        relative = absolute_lba - self.msinfo
        count = (size + 2047) // 2048
        require(relative >= 0 and relative + count <= self.data_track["sector_count"],
                f"ISO extent outside data session: LBA {absolute_lba}, bytes {size}")
        if not size:
            return b""
        self.handle.seek(self.payload_offset - 8 + relative * 2336)
        raw = self.handle.read(count * 2336)
        require(len(raw) == count * 2336, "Truncated CDI data extent")
        require(all(raw[offset:offset + 4] == raw[offset + 4:offset + 8] and
                    raw[offset + 2] & 0x20 == 0
                    for offset in range(0, len(raw), 2336)),
                "XA subheader mismatch or Form2 sector in ISO data extent")
        return b"".join(raw[offset + 8:offset + 2056]
                        for offset in range(0, len(raw), 2336))[:size]

    def files(self):
        files = {}
        visited = set()

        def walk(extent, size, prefix):
            require((extent, size) not in visited, "Cyclic ISO directory")
            visited.add((extent, size))
            directory = self.read_extent(extent, size)
            position = 0
            while position < len(directory):
                length = directory[position]
                if not length:
                    position = (position // 2048 + 1) * 2048
                    continue
                require(length >= 34 and position + length <= len(directory),
                        "Malformed ISO directory record")
                record = directory[position:position + length]
                position += length
                name = record[33:33 + record[32]]
                require(len(name) == record[32], "Truncated ISO filename")
                if name in (b"\x00", b"\x01"):
                    continue
                name = name.decode("ascii").split(";", 1)[0].rstrip(".")
                path = prefix + name
                item_extent, item_size = u32(record, 2), u32(record, 10)
                if record[25] & 2:
                    walk(item_extent, item_size, path + "/")
                elif path.upper() not in EXCLUDED - {"1ST_READ.BIN"}:
                    require(path.upper() not in files, f"Duplicate ISO filename: {path}")
                    files[path.upper()] = {
                        "path": path, "lba": item_extent, "size": item_size,
                    }
        walk(self.root_extent, self.root_size, "")
        return files


def validate(args):
    report = {"status": "failed", "scope": "CDI structure and exact file integrity",
              "emulator_boot": "not assessed", "physical_boot": "not assessed", "checks": {}}
    images = []

    def check(name, passed, **details):
        report["checks"][name] = {"pass": bool(passed), **details}

    try:
        image = CdiImage(args.image)
        images.append(image)
        reference = CdiImage(args.boing_reference)
        images.append(reference)
        report["image"] = {"path": str(args.image.resolve()), "bytes": image.size,
                           "sha256": file_sha256(args.image)}
        report["boing_reference"] = {"path": str(args.boing_reference.resolve()),
                                     "sha256": file_sha256(args.boing_reference)}
        audio = [track for track in image.tracks if track["mode"] == 0]
        layout_ok = (image.session_count == 2 and len(audio) >= 1 and
                     all(track["session"] == 0 for track in audio) and
                     all(track["read_mode"] == 2 and track["control"] == 0 for track in audio) and
                     image.data_track["session"] == 1)
        check("layout", layout_ok, expected="Audio/Data", sessions=image.session_count,
              tracks=image.tracks, data_session_lba=image.msinfo,
              bootstrap_payload_offset=image.payload_offset)
        ip = image.ip_bin
        check("hardware_signature", ip[:16] == b"SEGA SEGAKATANA ", actual=ip[:16].decode("ascii", "replace"))
        check("cd_rom_header", b"CD-ROM" in ip[32:48], actual=ip[32:48].decode("ascii", "replace"))
        check("japan_region", b"J" in ip[48:56], actual=ip[48:56].decode("ascii", "replace"))
        check("boot_filename", ip[96:112].rstrip() == b"1ST_READ.BIN",
              actual=ip[96:112].decode("ascii", "replace"))
        for name, start, end in [("license_code", 0x300, 0x3700),
                                  ("japan_license_slot", 0x3700, 0x3740),
                                  ("bootstrap", 0x3800, 0x8000)]:
            actual, expected = ip[start:end], reference.ip_bin[start:end]
            check(name, actual == expected, ip_start_hex=hex(start), ip_end_hex=hex(end),
                  image_sha256=sha256(actual), boing_sha256=sha256(expected))
        report["pvd"] = {"payload_file_offset": image.payload_offset + 16 * 2336,
                         "absolute_lba": image.msinfo + 16,
                         "fad": image.msinfo + 166,
                         "path_table_extent": image.path_extent,
                         "root_directory_extent": image.root_extent,
                         "root_directory_bytes": image.root_size}
        check("absolute_iso_extents", True, msinfo=image.msinfo,
              path_table_extent=image.path_extent, root_extent=image.root_extent)
        files = image.files()
        require("1ST_READ.BIN" in files, "Missing 1ST_READ.BIN")
        boot_entry = files["1ST_READ.BIN"]
        recorded_boot = image.read_extent(boot_entry["lba"], boot_entry["size"])
        raw_boot = descramble(recorded_boot)
        expected_raw = args.adapted_raw.read_bytes()
        raw_digest = sha256(raw_boot)
        check("adapted_boot_binary", raw_boot == expected_raw,
              raw_bytes=len(raw_boot), raw_sha256=raw_digest,
              expected_raw_sha256=sha256(expected_raw), recorded_sha256=sha256(recorded_boot),
              recorded_bytes=len(recorded_boot))
        if args.expected_raw_sha256:
            check("pinned_raw_boot_hash", raw_digest == args.expected_raw_sha256.lower(),
                  expected=args.expected_raw_sha256.lower(), actual=raw_digest)
        require(args.pvd_fad_offset + 4 <= len(raw_boot), "PVD FAD word outside raw boot binary")
        fad = u32(raw_boot, args.pvd_fad_offset)
        check("browser_pvd_fad", fad == image.msinfo + 166,
              raw_file_offset_hex=hex(args.pvd_fad_offset), actual=fad,
              expected=image.msinfo + 166)
        source = {}
        for path in sorted(args.source_dir.rglob("*")):
            if path.is_file():
                relative = path.relative_to(args.source_dir).as_posix()
                if relative.upper() not in EXCLUDED:
                    require(relative.upper() not in source, "Case-folding collision in source files")
                    source[relative.upper()] = path
        actual_names = set(files) - {"1ST_READ.BIN"}
        check("file_set", actual_names == set(source), files_expected=len(source),
              files_recorded=len(actual_names), missing=sorted(set(source) - actual_names),
              unexpected=sorted(actual_names - set(source)))
        report["files"] = []
        mismatches = []
        for name in sorted(actual_names):
            entry = files[name]
            content = image.read_extent(entry["lba"], entry["size"])
            digest = sha256(content)
            expected_digest = file_sha256(source[name]) if name in source else None
            matches = digest == expected_digest
            if not matches:
                mismatches.append(name)
            report["files"].append({**entry, "sha256": digest,
                                    "expected_sha256": expected_digest, "matches_source": matches})
        check("source_file_integrity", not mismatches, mismatches=mismatches,
              files_compared=len(actual_names))
        for suffix, expected in [("VMI", args.expected_vmi_sha256), ("VMS", args.expected_vms_sha256)]:
            name = f"DPWWW/SAVES/STACKCHN.{suffix}"
            entry = next((entry for entry in report["files"] if entry["path"].upper() == name), None)
            actual_digest = entry["sha256"] if entry else None
            check(f"stackchan_{suffix.lower()}_payload", actual_digest == expected.lower(),
                  path=name, expected_sha256=expected.lower(), actual_sha256=actual_digest)
        if all(item["pass"] for item in report["checks"].values()):
            report["status"] = "passed"
    except (OSError, ValueError, struct.error) as error:
        report["error"] = str(error)
    finally:
        for image in images:
            image.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True, help="Actual Audio/Data CDI to validate")
    parser.add_argument("--boing-reference", type=Path, required=True, help="Known BOING CDI reference")
    parser.add_argument("--source-dir", type=Path, required=True, help="Original browser/payload source directory")
    parser.add_argument("--adapted-raw", type=Path, required=True, help="Expected adapted unscrambled 1ST_READ binary")
    parser.add_argument("--expected-raw-sha256", help="Optional independently pinned adapted-binary SHA-256")
    parser.add_argument("--pvd-fad-offset", type=lambda value: int(value, 0), default=0x282CF0)
    parser.add_argument("--expected-vmi-sha256", default=EXPECTED_VMI_SHA256)
    parser.add_argument("--expected-vms-sha256", default=EXPECTED_VMS_SHA256)
    parser.add_argument("--report", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    report = validate(args)
    result = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(result, encoding="utf-8")
    print(result, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
