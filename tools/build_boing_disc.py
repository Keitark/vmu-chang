"""Build a BOING-bootstrap CDI from a user-supplied VMU browser directory.

Example:
  python tools/build_boing_disc.py EXTRACTED_BROWSER candidate.cdi --layout audio-data

Outputs: CDI, ISO, .manifest.json and .build.log. Existing outputs are never
overwritten. Windows builds use Ubuntu WSL by default and create the image in
Linux temporary storage before copying it to Windows. The mkdcdisc source must
be clean and at the audited BOING revision; no source or binaries are fetched.
Flycast and physical Dreamcast boot remain pending until separately tested.
"""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from prepare_browser import (SESSION_LBAS, ToolRunner, add_tool_arguments,
                             prepare_browser, refuse_existing, sha256)

BUILDER_COMMIT = "2b98b0d9480e364e3517355648fbc3b49fb19882"
DEFAULT_BUILDER = "/root/.cache/boing-overdrive/dc/bin/mkdcdisc"
DEFAULT_BUILDER_SOURCE = "/root/.cache/boing-overdrive/dc/mkdcdisc"
EXCLUDED_ROOT_NAMES = {"0.0", "IP.BIN", "1ST_READ.BIN"}


def stage_payload(source, target):
    """Copy relative payload paths, excluding only the original boot files."""
    source, target = Path(source).resolve(), Path(target).resolve()
    target.mkdir()
    files = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if relative.parts[0].upper() in EXCLUDED_ROOT_NAMES:
            continue
        if path.is_symlink():
            raise ValueError(f"Payload symlinks are unsupported: {path}")
        destination = target / relative
        if path.is_dir():
            destination.mkdir(exist_ok=True)
        elif path.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            files.append({"path": relative.as_posix(), "bytes": destination.stat().st_size,
                          "sha256": sha256(destination)})
    return files


def verify_builder(runner, builder, source, layout):
    actual = runner.run(["git", "-C", source, "rev-parse", "HEAD"], capture=True)
    if actual != BUILDER_COMMIT:
        raise ValueError(f"mkdcdisc revision {actual} differs from required {BUILDER_COMMIT}")
    changes = runner.run(["git", "-C", source, "status", "--porcelain", "--untracked-files=no"], capture=True)
    if changes:
        raise ValueError("mkdcdisc source has tracked modifications; rebuild from the pinned clean revision")
    version = runner.run([builder, "--help"], capture=True, include_stderr=True).splitlines()[0]
    session = int(runner.run([builder, "-L", layout, "-M"], capture=True))
    if session != SESSION_LBAS[layout]:
        raise ValueError(f"mkdcdisc reports session LBA {session}; expected {SESSION_LBAS[layout]}")
    binary_sha = runner.run(["sha256sum", builder], capture=True).split()[0]
    return {"source_commit": actual, "source_clean": True, "binary_sha256": binary_sha,
            "version": version, "session_lba": session,
            "provenance": "Source revision and binary hash recorded; binary build provenance is caller-managed"}


def build_disc(args):
    source, output = args.browser_dir.resolve(), args.output.resolve()
    if output.suffix.lower() != ".cdi":
        raise ValueError("Output must end in .cdi")
    if not source.is_dir():
        raise FileNotFoundError(f"Missing extracted browser directory: {source}")
    if output.is_relative_to(source):
        raise ValueError("Place build outputs outside the source browser directory")
    iso = output.with_suffix(".iso")
    manifest_path, log_path = output.with_suffix(".manifest.json"), output.with_suffix(".build.log")
    refuse_existing([output, iso, manifest_path, log_path])
    output.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("x", encoding="utf-8") as log:
        runner = ToolRunner(args.native, args.wsl_distro, args.wsl_user, log)
        builder_info = verify_builder(runner, args.mkdcdisc, args.mkdcdisc_source, args.layout)
        with tempfile.TemporaryDirectory(prefix="vmu-disc-") as directory:
            scratch = Path(directory)
            files = stage_payload(source, scratch / "content")
            adapted = scratch / "adapted.bin"
            adapter_info = prepare_browser(source, adapted, args.layout, args.shim,
                                           runner, args.toolchain_prefix,
                                           hardware_startup=args.hardware_startup)
            # A Linux /tmp output avoids slow sector-by-sector writes through /mnt.
            if runner.use_wsl:
                remote = runner.run(["mktemp", "-d", "-t", "vmu-disc.XXXXXXXX"], capture=True)
                if not remote.startswith("/tmp/vmu-disc.") or "\n" in remote:
                    raise ValueError(f"Unexpected WSL temporary path {remote!r}")
                temporary_image = remote + "/candidate.cdi"
            else:
                remote = None
                temporary_image = str(scratch / "candidate.cdi")
            try:
                command = [args.mkdcdisc, "-b", runner.path(adapted), "-D", runner.path(scratch / "content"),
                           "-L", args.layout, "-n", args.title, "-a", args.author,
                           "-V", args.volume_label, "-r", args.release, "-I", "-o", temporary_image]
                runner.run(command)
                if runner.use_wsl:
                    # Reserve the final names exclusively before Linux copies.
                    with output.open("xb"), iso.open("xb"):
                        pass
                    runner.run(["cp", "--", temporary_image, runner.path(output)])
                    runner.run(["cp", "--", temporary_image[:-4] + ".iso", runner.path(iso)])
                else:
                    for src, dst in ((Path(temporary_image), output),
                                     (Path(temporary_image).with_suffix(".iso"), iso)):
                        with src.open("rb") as read_stream, dst.open("xb") as write_stream:
                            shutil.copyfileobj(read_stream, write_stream)
            finally:
                if remote:
                    # Exact, verified mktemp directory; no computed workspace tree deletion.
                    runner.run(["rm", "-rf", "--", remote])
    manifest = {
        "reference": "BOING // OVERDRIVE", "layout": args.layout,
        "bootstrap": "Pinned mkdcdisc default bootstrap, regenerated metadata",
        "title": args.title, "author": args.author, "release": args.release,
        "volume_label": args.volume_label, "session_lba": SESSION_LBAS[args.layout],
        "pvd_fad": 166 + SESSION_LBAS[args.layout], "builder": builder_info,
        "adapter": {key: value for key, value in adapter_info.items() if key != "output"},
        "source_browser_dir": str(source), "payload_files": files,
        "iso_purpose": "Standalone base-zero inspection dump; boot-session validation must use the CDI",
        "outputs": [{"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
                    for path in (output, iso)],
        "build_log": str(log_path), "flycast_boot": "pending",
        "physical_boot": "pending bench test", "disc_write": "not performed",
    }
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    return {"cdi": str(output), "iso": str(iso), "manifest": str(manifest_path),
            "build_log": str(log_path), "layout": args.layout,
            "sha256": sha256(output), "physical_boot": manifest["physical_boot"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("browser_dir", type=Path, help="User-supplied extracted browser directory")
    parser.add_argument("output", type=Path, help="New .cdi path, outside the source directory")
    parser.add_argument("--layout", choices=SESSION_LBAS, default="audio-data")
    parser.add_argument("--mkdcdisc", default=DEFAULT_BUILDER)
    parser.add_argument("--mkdcdisc-source", default=DEFAULT_BUILDER_SOURCE)
    parser.add_argument("--title", default="VMU STACK-CHAN TRANSFER")
    parser.add_argument("--author", default="VMU Disc Builder")
    parser.add_argument("--volume-label", default="VMUDISC")
    parser.add_argument("--release", default="20261014", help="YYYYMMDD; explicit default keeps builds stable")
    add_tool_arguments(parser)
    args = parser.parse_args()
    try:
        result = build_disc(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Disc build failed: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
