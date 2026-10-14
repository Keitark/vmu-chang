# Stack-chan Face for VMU

A separate, face-only version: round eyes, a straight mouth and an occasional binary blink. The LCD contains no robot body, text, border or speech bubbles. A/B and the directional pad leave the face alone; MODE returns to the VMU menu, and SLEEP uses the existing sleep path.

The original `STACKCHN.VMS` program stays unchanged. This variant is `FACECHAN.VMS` with matching `FACECHAN.VMI` download metadata. It reuses the original program's now-confirmed startup, interrupt trampoline, LCD copying and system-button handling. New physical acceptance is recorded separately.

![Enlarged native-pixel face preview; animation timing is illustrative](preview.gif)

The generated program is 2,048 bytes (4 VMU blocks). Its current VMS SHA-256 is `0cff3d44bf0d156181773a1713cec817f23066cd57b4a47ef049681e5459709f`. All 18 bounded program checks pass, including complete LCD frame writes, action-key invariance, blink selection and limited MODE/SLEEP/dock control flow. Two fresh builds produce identical files. New physical VMU acceptance remains pending.

## Face reference

The artwork comes from the procedural look of the ebazchan `samples/stackchang_face` demo, based on [m5stack-avatar](https://github.com/meganetaaan/m5stack-avatar) (MIT, Copyright 2018 Shinya Ishikawa). That reference uses two circles and a rectangular mouth, rather than a bitmap asset. The neutral 240×240 scene has eye centers (50,93)/(190,96), radius 8, and a 90×4 mouth centered at (123,148). Closed eyes become 16×4 bars.

This version scales uniformly by one fifth and crops unused top/bottom margins, taking source rows 40–199. It fits the 48×32 LCD without stretching the face. Thin strokes remain at least one pixel. LCD dark pixels form the background and clear pixels form the face. The upstream notice and the runtime's third-party notices are in [THIRD_PARTY_NOTICES.txt](../THIRD_PARTY_NOTICES.txt).

## Build and validate

Python 3.11+ and Pillow are required. From the repository root:

```powershell
python face/build_face.py NEW_FACE_OUTPUT_DIR
python face/test_face.py NEW_FACE_OUTPUT_DIR
```

The output directory contains the VMS/VMI, generated assembly and frame bytes, symbol table, manifest, save icon and actual-pixel previews. Existing generated files are preserved. This command does not rebuild or overwrite the original program.

The bounded interpreter checks actual LC86K execution and LCD writes. It does not emulate the VMU BIOS, interrupts, real display timing or physical power consumption. The blink is selected for two frames in every sixteen; the physical interval depends on the hardware. MODE, docking and sleep tests check control flow only.

## Transfer disc

Use the same original extracted browser directory and BOING reference used for the confirmed working transfer image:

```powershell
python face/build_disc.py NEW_FACE_OUTPUT_DIR EXTRACTED_BROWSER NEW_FACE_DISC.cdi --boing-reference BOING.cdi
```

This wrapper stages a temporary browser tree, adds FACECHAN, and makes its download the home-page link. It preserves the original Stack-chan payload under the original P–S page. The disc uses the confirmed Audio/Data hardware-startup path. It validates the actual CDI against the expected executable, bootstrap and all staged files before recording success. The accompanying base-zero ISO is an inspection artifact; burn the CDI.

Select **Download face to VMU**, choose a VMU and wait for save completion. Remove the VMU from the controller, press SLEEP, choose Game using MODE, then press A. Standalone operation requires working VMU batteries.

The original program has user-confirmed physical boot and transfer. A successful build, interpreter test or Flycast browser test does not establish physical acceptance of this new variant.
