# Local VMU validation

Run on 2026-10-14 after importing the original source package:

```powershell
python make_art.py
python build_vms.py
python smoke_test.py
```

All commands exited successfully. The smoke test checked 206 machine-executed frames using 1,018,376 LC86K instructions, direct LCD RAM copies, idle animation, blink/glance frames, and six button reactions.

The regenerated `STACKCHN.VMS` (8192 bytes, 16 VMU blocks) and `STACKCHN.VMI` (108 bytes) matched the original package byte for byte. The VMS SHA-256 is:

```text
a353ad9a1d69ee535c6859672a512fac1c6f2b1286a2816dcf116be0516d36dc
```

This test uses a small custom interpreter. It does not validate VMU firmware interrupt handling, MODE/SLEEP behavior, real hardware timing, physical LCD behavior, or Dreamcast disc boot. See [boot-status.md](boot-status.md) for the separate disc investigation.
