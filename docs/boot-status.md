# Dreamcast boot investigation

Evidence collected on 2026-10-14.

## Observations

| Image | PC verification | Flycast 2.7 HLE BIOS, Japan region | Physical Japanese Dreamcast |
| --- | --- | --- | --- |
| Original upstream VMU Disc Builder Data/Data | Passed | Sega license screen → VMU Disc Builder browser | Dreamcast startup swirl → system menu, no Sega license screen |
| Experimental Audio/Data remaster | Passed | Stalls at Sega license screen, reproduced | Sega license screen, then stalls |
| BOING // OVERDRIVE Audio/Data reference | Not retested in this investigation | Reaches animated game title | Not established by this comparison |

The user reports that other burned discs boot on the same Dreamcast and that the console supports MIL-CD.

Flycast tests used its HLE BIOS replacement. No test with an original Dreamcast BIOS dump was performed. Reaching the browser is not VMU installation or VMU program acceptance.

## Image checks

The original image has two Mode 2 Form 1 data sessions: the first starts at LBA 0, and the second bootstrap track starts at LBA 293240. The recorded disc's table of contents matches this structure. Its SHA-256 is:

```text
737cc46e632521cb6adbba3f8033d9c8b1ade84f61d24b8e1143b4d977e435b0
```

The Audio/Data experiment rebased the filesystem to LBA 11702 while preserving all 88 extracted files, including the custom browser executable and IP.BIN. File-content equality did not establish boot-loader compatibility. The experiment failed and is not distributed here.

All compared headers allow Japan (`JUE`). The original VMU image's Sega license-code bytes at IP.BIN offsets 0x0300–0x36FF and Japan region slot match the BOING reference byte for byte. The VMU image's first- and second-session IP.BIN contents also match.

## Interpretation and next checks

The exact cause of the original physical-console failure is unresolved. Candidate explanations include real-BIOS handling/loading of the Data/Data boot session and Dreamcast-specific readability of this CD-R. HLE success and PC verification cannot distinguish them.

The Audio/Data experiment likely broke an assumption in the custom browser/bootstrap pairing by moving the filesystem. No specific hardcoded sector constant has been proven. The custom bootstrap means a blanket “scramble the binary” correction is not justified.

Useful next checks are an original-BIOS emulator test using the owner's BIOS dump, tracing the custom bootstrap's disc reads, and a controlled comparison with a CD-R known to boot on the console. Another physical burn should follow a validated candidate, not an untested layout conversion.

## References

- [Marcus Comstedt: IP.BIN and 1ST_READ.BIN](https://mc.pp.se/dc/ip.bin.html)
- [VMU Disc Builder source](https://github.com/DerekPascarella/VMU-Disc-Builder)
- [Flycast v2.7 HLE boot implementation](https://github.com/flyinghead/flycast/blob/v2.7/core/reios/reios.cpp)
