#!/usr/bin/env python3
"""Build and validate a face installer using the confirmed BOING startup path."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / 'tools'
HOME = '''<!doctype html>
<html><head><title>Stack-chan Face</title></head>
<body bgcolor="#ffffff" text="#000000" link="#0066ff">
<center><h1>Stack-chan Face</h1>
<p><a href="SAVES/FACECHAN.VMI"><img src="SAVES/FACECHAN.GIF" width="96" height="96" border="0"></a></p>
<h2><a href="SAVES/FACECHAN.VMI">Download face to VMU</a></h2>
<p>Select your VMU and confirm the download.</p>
<p>When saving is complete, remove the VMU from the controller.<br>
Press SLEEP, select Game with MODE, then press A.</p>
<p><a href="PS.HTM">Original Stack-chan version</a></p>
</center></body></html>
'''


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(tool, *arguments):
    result = subprocess.run([sys.executable, str(TOOLS / tool), *map(str, arguments)],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def build(args):
    source = args.browser_dir.resolve()
    face = args.face_dir.resolve()
    output = args.output.resolve()
    if output.suffix.lower() != '.cdi':
        raise ValueError('The output must be a new .cdi image')
    if output.is_relative_to(source) or output.is_relative_to(face):
        raise ValueError('Disc outputs must be outside both input directories')
    report = output.with_suffix('.validation.json')
    installer = output.with_suffix('.installer.json')
    if report.exists() or installer.exists():
        raise FileExistsError('Preserve existing validation/installer evidence')
    vms, vmi = face / 'FACECHAN.VMS', face / 'FACECHAN.VMI'
    metadata = vmi.read_bytes()
    if len(metadata) != 108 or metadata[0x50:0x58] != b'FACECHAN':
        raise ValueError('Unexpected face VMI resource name or size')
    if metadata[0x58:0x64].rstrip(b'\0') != b'FACECHAN':
        raise ValueError('Unexpected VMU filename')
    if struct.unpack_from('<H', metadata, 0x64)[0] != 2:
        raise ValueError('The face package must be an unprotected VMU game')
    if struct.unpack_from('<I', metadata, 0x68)[0] != vms.stat().st_size:
        raise ValueError('The VMI size does not match the VMS')
    if not (source / '1ST_READ.BIN').is_file():
        raise FileNotFoundError('Expected extracted browser 1ST_READ.BIN')
    with tempfile.TemporaryDirectory(prefix='vmu-face-installer-') as directory:
        scratch = Path(directory)
        staged = scratch / 'browser'
        staged.mkdir()
        for original in source.rglob('*'):
            if original.is_file():
                relative = original.relative_to(source)
                if relative.as_posix() == '0.0':
                    continue
                target = staged / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
        saves = staged / 'DPWWW/SAVES'
        if not (staged / 'DPWWW/PS.HTM').is_file() or not saves.is_dir():
            raise ValueError('Expected VMU Disc Builder browser directories')
        for name in ('FACECHAN.VMS', 'FACECHAN.VMI', 'FACECHAN.GIF'):
            if (saves / name).exists():
                raise FileExistsError('Input browser already has a face package')
        shutil.copyfile(vms, saves / vms.name)
        shutil.copyfile(vmi, saves / vmi.name)
        from PIL import Image
        with Image.open(face / 'icon.png') as icon:
            icon.convert('RGB').save(saves / 'FACECHAN.GIF', format='GIF')
        (staged / 'DPWWW/INDEX.HTM').write_text(HOME, encoding='ascii')
        expected = scratch / 'expected.bin'
        common = ['--layout', 'audio-data', '--hardware-startup']
        if args.native:
            common += ['--native']
        prepared = run('prepare_browser.py', staged, expected, *common)
        built = run('build_boing_disc.py', staged, output, *common,
                    '--title', 'VMU STACK-CHAN FACE', '--volume-label', 'VMUFACE',
                    '--release', '20261015')
        validation = run('validate_boing_disc.py', '--image', output,
                         '--boing-reference', args.boing_reference.resolve(),
                         '--source-dir', staged, '--adapted-raw', expected,
                         '--expected-raw-sha256', prepared['output_sha256'], '--report', report)
        if validation['status'] != 'passed':
            raise ValueError('Actual CDI validation failed')
        face_files = [{'path': name, 'sha256': sha(saves / name),
                       'bytes': (saves / name).stat().st_size}
                      for name in ('FACECHAN.VMS', 'FACECHAN.VMI', 'FACECHAN.GIF')]
        record = {'image': str(output), 'image_sha256': built['sha256'],
                  'source_browser_dir': str(source), 'face_build_dir': str(face),
                  'startup_mode': 'hardware', 'layout': 'audio-data',
                  'adapted_browser_sha256': prepared['output_sha256'],
                  'installer_home_sha256': sha(staged / 'DPWWW/INDEX.HTM'),
                  'face_files': face_files, 'original_stackchan_payload': 'preserved',
                  'validation': str(report), 'validation_status': 'passed',
                  'flycast_boot': 'pending', 'physical_boot': 'pending',
                  'physical_vmu_transfer_and_execution': 'pending', 'disc_write': 'not performed'}
    with installer.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
    print(json.dumps(record, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('face_dir', type=Path, help='Output from build_face.py')
    parser.add_argument('browser_dir', type=Path, help='Original extracted browser files')
    parser.add_argument('output', type=Path, help='New Audio/Data .cdi path')
    parser.add_argument('--boing-reference', type=Path, required=True)
    parser.add_argument('--native', action='store_true')
    args = parser.parse_args()
    try:
        build(args)
    except subprocess.CalledProcessError as error:
        parser.exit(1, 'Disc tool failed:\n' + (error.stderr or error.stdout or str(error)))
    except (OSError, ValueError) as error:
        parser.exit(1, f'Face disc build failed: {error}\n')


if __name__ == '__main__':
    main()
