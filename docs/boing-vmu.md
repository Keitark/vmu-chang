# BOING boot loader with the VMU transfer browser

The Audio/Data candidate reaches the VMU Disc Builder browser in Flycast 2.7 using its HLE BIOS. Its disc license code and boot loader match the confirmed-working BOING reference byte for byte. The verified CD-R reaches the Sega screen on the physical Japanese Dreamcast, then freezes before the browser. VMU transfer has not been reached.

## What changed

The original browser expects a GD-ROM drive classification. With BOING's normal `CD-ROM1/1` header, Flycast reports the actual CD class and the unmodified browser stalls at the Sega license screen. A controlled Data/Data diagnostic changed only the header's `C` to `G` and reached the browser. That diagnostic did not regenerate sector checksums and must never be burned.

The candidate keeps BOING's CD header and bootstrap. A small entry adapter wraps only successful GD-ROM drive-status requests. It converts loaded CD-ROM, CD-XA, or CD-i classifications to the GD-ROM class expected by the browser. It preserves error, busy, absent-disc, open-tray, and audio-only responses. The browser then resumes at its original entry offset `0x0C`.

The Audio/Data layout also requires the browser's primary-volume-descriptor FAD to change from `166` to `11868`. This changes one little-endian word at raw executable offset `0x282CF0`. Other constants with value 166 are unchanged: one is a Java opcode, another is an offset within the volume descriptor. mkdcdisc already relocates the actual CDI's ISO extents for session LBA `11702`; its optional standalone ISO dump deliberately has base zero.

The runtime wrapper is copied to `0xAC00B900`, within BOING's consumed MR image source, before entering the browser. This avoids both BIOS-shadow RAM and the browser's BSS clearing range. The bootstrap bytes recorded on disc are unchanged. The browser startup adapter is appended at `0xAC2BD8E4`; it runs before startup clears that region.

This proves the cause of the replacement image's **HLE emulator stall**. The original Data/Data disc's rejection before the Sega logo on the physical console has not been traced. The new candidate uses the BOING Audio/Data boot path to test that separately.

## Reproduce

Python 3.11 or newer, Ubuntu WSL, the SH4 binutils toolchain, and mkdcdisc are required. The scripts accept native Linux execution and custom paths through `--native`, `--toolchain-prefix`, `--mkdcdisc`, and `--mkdcdisc-source`.

Use a local extracted VMU browser directory containing `1ST_READ.BIN`, `DP2.INI`, and the `DP*` directories. The audited raw browser is 2,808,036 bytes with SHA-256 `f43d637858be93cef87da0fd9045e9cf8c1ef9a288bb15b808bee360fb997b1e`. Other browser revisions are rejected. No browser executable, BIOS, or CDI is distributed in this repository.

The mkdcdisc source must be clean at BOING's builder commit `2b98b0d9480e364e3517355648fbc3b49fb19882`. The executable hash is recorded separately; source revision checking does not prove how an arbitrary executable was built.

```powershell
python tools/build_boing_disc.py EXTRACTED_BROWSER NEW_OUTPUT.cdi --layout audio-data
python tools/prepare_browser.py EXTRACTED_BROWSER EXPECTED_RAW.bin --layout audio-data
python tools/validate_boing_disc.py --image NEW_OUTPUT.cdi --boing-reference BOING.cdi --source-dir EXTRACTED_BROWSER --adapted-raw EXPECTED_RAW.bin --report validation.json
python -m unittest discover -s tools/tests -v
```

Outputs must be outside the input directory. Existing images, logs, and manifests are never overwritten. The builder excludes the original `0.0` dummy, `IP.BIN`, and `1ST_READ.BIN`, supplies the adapted raw executable to mkdcdisc for scrambling, and preserves every remaining file and relative path. The resulting image retains mkdcdisc's normal disc padding.

## Evidence

Tested local candidate: `VMU_STACKCHAN_BOING_VMU.cdi`, 740,246,665 bytes, SHA-256 `d4bfb03d97cc4b21ab2fbe13287f1c61978375b810f3bc35215e3fcd8bf337c3`.

| Check | Result |
|---|---|
| BOING license code `IP[0x300:0x3700]` | Identical |
| Japan license slot `IP[0x3700:0x3740]` | Identical; Japan enabled |
| BOING bootstrap `IP[0x3800:0x8000]` | Identical |
| Disc header | `CD-ROM1/1`, `JUE`, `1ST_READ.BIN` |
| Layout | Two sessions; Audio/Data; data starts at LBA11702 |
| Actual CDI path/root extents | 11736 / 11721 |
| Browser PVD FAD | 11868 |
| Recorded main executable | Descrambles to adapted raw SHA-256 `0ede416ea21c3f5314ba8800d37eb607b210158d7cfb95d46494b0560c08e8b0` |
| Browser and payload files | All 85 match the extracted source |
| `STACKCHN.VMS` | Original SHA-256 `a353ad9a1d69ee535c6859672a512fac1c6f2b1286a2816dcf116be0516d36dc` |
| `STACKCHN.VMI` | Original SHA-256 `95a9d009a13be7e7deb955916e0ec767f451a892803421467eca8339fd7f070b` |
| Flycast 2.7 HLE BIOS, Japan, composite | VMU browser reached |
| CD-R write and ImgBurn read-back | Passed at 10x SAO; both sessions match the candidate; zero read errors or mismatches |
| Original BIOS emulator test | Not performed; no BIOS dump supplied |
| Physical Japanese Dreamcast | Failed: Sega screen, then freeze before browser |
| VMU transfer | Not reached |

![Audio/Data candidate browser](evidence/boing-vmu-audiodata-browser.jpg)

The six tool regression tests pass. Complete repository-tool builds pass for both Audio/Data and Data/Data; the Audio/Data result also passes structural validation. The validator rejects the previous unadapted BOING Audio/Data candidate because its executable and PVD FAD do not match the adapter. Data/Data tool-build success alone is not emulator or console acceptance.

## Next investigation

Do not repeat the unchanged candidate's burn. Reaching the Sega screen narrows the failure to the subsequent startup path, but does not prove the browser main entry executed. The user's identification of a modified logo is uncertain.

The current adapter omits the original custom loader's GD-ROM unlock register write, full boot-ROM read, BIOS-shadow patches, and GD-ROM initialization. These hardware steps are being audited before a replacement is tested. Flycast HLE does not model the GD-ROM unlock lock itself, so its successful browser test can hide a hardware dependency. This is a lead, not a proven cause of the console freeze.

## Primary references

- [Flycast v2.7 drive-status implementation](https://github.com/flyinghead/flycast/blob/v2.7/core/reios/gdrom_hle.cpp): the HLE drive type depends on the IP header's GD-ROM classification.
- [Dreamcast system-call documentation](https://mc.pp.se/dc/syscalls.html): GD-ROM status call and output fields.
- [Dreamcast IP.BIN boot documentation](https://mc.pp.se/dc/ip.bin.html): boot/license stages and executable scrambling.

Refs #2.
