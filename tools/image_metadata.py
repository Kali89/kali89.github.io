#!/usr/bin/env python3
"""Check or strip privacy-sensitive metadata in images.

    python3 tools/image_metadata.py check --staged   # what the pre-commit hook runs
    python3 tools/image_metadata.py check FILE...
    python3 tools/image_metadata.py strip FILE...

Blocks on GPS coordinates, EXIF blocks, and data trailing a JPEG's end marker
(Pixel/iPhone "Motion Photo" files hide a whole video there). Stdlib only, so
the hook cannot break when a virtualenv is not active.
"""
import os
import struct
import subprocess
import sys

JPEG_EXT = {'.jpg', '.jpeg'}
PNG_EXT = {'.png'}
EXTS = JPEG_EXT | PNG_EXT
NOLEN = {0xD8, 0xD9, 0x01} | set(range(0xD0, 0xD8))


def _tiff_gps(tiff):
    """Decode GPS lat/lon from a TIFF/EXIF block. Returns (lat, lon) or None."""
    try:
        bo = '>' if tiff[:2] == b'MM' else '<'
        off = struct.unpack(bo + 'I', tiff[4:8])[0]

        def ifd(o):
            n = struct.unpack(bo + 'H', tiff[o:o + 2])[0]
            return {struct.unpack(bo + 'HHI', tiff[o + 2 + k * 12:o + 10 + k * 12])[0]:
                    (struct.unpack(bo + 'HHI', tiff[o + 2 + k * 12:o + 10 + k * 12])[1:],
                     tiff[o + 10 + k * 12:o + 14 + k * 12]) for k in range(n)}

        m = ifd(off)
        if 0x8825 not in m:
            return None
        g = ifd(struct.unpack(bo + 'I', m[0x8825][1])[0])
        if 2 not in g or 4 not in g:
            return None

        def rat(tag):
            (_, cnt), v = g[tag]
            o = struct.unpack(bo + 'I', v)[0]
            out = []
            for j in range(cnt):
                num, den = struct.unpack(bo + 'II', tiff[o + j * 8:o + j * 8 + 8])
                out.append(num / den if den else 0)
            return out

        ref = lambda t, d: (g[t][1][:1].decode('latin1') if t in g else d)
        la, lo = rat(2), rat(4)
        dec = lambda v, r: (v[0] + v[1] / 60 + v[2] / 3600) * (-1 if r in 'SW' else 1)
        lat, lon = dec(la, ref(1, 'N')), dec(lo, ref(3, 'E'))
        if lat == 0 and lon == 0:
            return None
        return round(lat, 6), round(lon, 6)
    except Exception:
        return None


def scan_jpeg(d):
    """Return (issues, keep_segments_end) for a JPEG byte string."""
    issues = []
    i = 2
    while i < len(d) - 1:
        if d[i] != 0xFF:
            issues.append('malformed JPEG structure')
            return issues
        m = d[i + 1]
        if m in NOLEN:
            i += 2
            continue
        L = struct.unpack('>H', d[i + 2:i + 4])[0]
        payload = d[i + 4:i + 2 + L]
        if m == 0xE1 and payload.startswith(b'Exif\x00\x00'):
            gps = _tiff_gps(payload[6:])
            if gps:
                issues.append(f'GPS coordinates in EXIF: {gps[0]}, {gps[1]}')
            else:
                issues.append(f'EXIF block ({L + 2} bytes)')
        elif m == 0xE1 and b'ns.adobe.com' in payload[:32]:
            issues.append(f'XMP block ({L + 2} bytes)')
        elif m == 0xEB:
            issues.append(f'JUMBF/C2PA provenance block ({L + 2} bytes)')
        i += 2 + L
        if m == 0xDA:
            while i < len(d) - 1:
                if d[i] == 0xFF and d[i + 1] != 0x00 and not (0xD0 <= d[i + 1] <= 0xD7):
                    break
                i += 1
            trailer = len(d) - (i + 2)
            if trailer > 0:
                extra = ''
                if b'ftyp' in d[i:i + trailer + 2][:200000]:
                    extra = ' — contains an embedded video (Motion Photo)'
                issues.append(f'{trailer:,} bytes trailing the end-of-image marker{extra}')
            break
    return issues


def scan_png(d):
    issues = []
    i = 8
    while i + 8 <= len(d):
        ln = struct.unpack('>I', d[i:i + 4])[0]
        typ = d[i + 4:i + 8]
        body = d[i + 8:i + 8 + ln]
        if typ == b'eXIf':
            gps = _tiff_gps(body)
            issues.append(f'GPS coordinates in PNG eXIf: {gps[0]}, {gps[1]}' if gps
                          else f'PNG eXIf block ({ln} bytes)')
        elif typ in (b'tEXt', b'iTXt', b'zTXt') and b'GPS' in body:
            issues.append(f'GPS text in PNG {typ.decode()} chunk')
        if typ == b'IEND':
            if len(d) - (i + 12) > 0:
                issues.append(f'{len(d) - (i + 12):,} bytes trailing PNG IEND')
            break
        i += 12 + ln
    return issues


def scan(data, path):
    ext = os.path.splitext(path)[1].lower()
    if ext in JPEG_EXT and data[:2] == b'\xff\xd8':
        return scan_jpeg(data)
    if ext in PNG_EXT and data[:8] == b'\x89PNG\r\n\x1a\n':
        return scan_png(data)
    return []


def strip_jpeg(d):
    """Rebuild a JPEG keeping only JFIF + ICC. No re-encode: the entropy-coded
    scan is copied byte-for-byte, so pixels are unchanged."""
    out = bytearray(b'\xff\xd8')
    i = 2
    while i < len(d) - 1:
        if d[i] != 0xFF:
            raise ValueError('malformed JPEG')
        m = d[i + 1]
        if m in NOLEN:
            i += 2
            continue
        L = struct.unpack('>H', d[i + 2:i + 4])[0]
        payload = d[i + 4:i + 2 + L]
        keep = not (0xE0 <= m <= 0xEF or m == 0xFE)
        if m == 0xE0 and payload.startswith(b'JFIF\x00'):
            keep = True
        elif m == 0xE2 and payload.startswith(b'ICC_PROFILE\x00'):
            keep = True
        if keep:
            out += d[i:i + 2 + L]
        i += 2 + L
        if m == 0xDA:
            start = i
            while i < len(d) - 1:
                if d[i] == 0xFF and d[i + 1] != 0x00 and not (0xD0 <= d[i + 1] <= 0xD7):
                    break
                i += 1
            out += d[start:i] + b'\xff\xd9'
            return bytes(out)
    return bytes(out)


def strip_png(d):
    out = bytearray(d[:8])
    i = 8
    drop = {b'eXIf', b'tEXt', b'iTXt', b'zTXt', b'tIME'}
    while i + 8 <= len(d):
        ln = struct.unpack('>I', d[i:i + 4])[0]
        typ = d[i + 4:i + 8]
        if typ not in drop:
            out += d[i:i + 12 + ln]
        i += 12 + ln
        if typ == b'IEND':
            break
    return bytes(out)


def staged_images():
    out = subprocess.run(['git', 'diff', '--cached', '--name-only', '--diff-filter=ACM', '-z'],
                         capture_output=True, text=True).stdout
    return [p for p in out.split('\0')
            if p and os.path.splitext(p)[1].lower() in EXTS]


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('check', 'strip'):
        print(__doc__)
        return 2
    mode, rest = sys.argv[1], sys.argv[2:]

    if mode == 'check':
        if rest == ['--staged']:
            paths = staged_images()
            # read the staged blob, not the working tree
            read = lambda p: subprocess.run(['git', 'show', f':{p}'],
                                            capture_output=True).stdout
        else:
            paths = rest
            read = lambda p: open(p, 'rb').read()
        bad = {}
        for p in paths:
            try:
                issues = scan(read(p), p)
            except Exception as e:
                issues = [f'could not parse: {e}']
            if issues:
                bad[p] = issues
        if not bad:
            return 0
        print('\nBlocked: image metadata found in files being committed.\n')
        for p, issues in bad.items():
            print(f'  {p}')
            for it in issues:
                print(f'      - {it}')
        print('\nThis repo is published at dogdogfish.com, so anything above ships')
        print('with the image. Strip it with:\n')
        print(f'  python3 tools/image_metadata.py strip {" ".join(bad)}')
        print('  git add ' + ' '.join(bad) + '\n')
        print('To commit anyway (rarely right): git commit --no-verify\n')
        return 1

    changed = False
    for p in rest:
        d = open(p, 'rb').read()
        ext = os.path.splitext(p)[1].lower()
        new = strip_jpeg(d) if ext in JPEG_EXT else strip_png(d) if ext in PNG_EXT else d
        if new != d:
            open(p, 'wb').write(new)
            pct = 100 * (len(d) - len(new)) / len(d)
            print(f'{p}: {len(d):,} -> {len(new):,} bytes ({pct:.1f}% smaller)')
            changed = True
        else:
            print(f'{p}: already clean')
    if changed:
        print('\nPixels are unchanged — only metadata was removed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
