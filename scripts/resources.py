"""Acquire and install design assets with provenance; never declares visual fidelity."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from cli_output import configure_utf8_output

LIMIT = 32 * 1024 * 1024
ANDROID = 'http://schemas.android.com/apk/res/android'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_source(source):
    parsed = urllib.parse.urlsplit(source)
    if parsed.scheme in ('http', 'https'):
        if parsed.username or parsed.password:
            raise ValueError('use a locally exported file for authenticated assets')
        with urllib.request.urlopen(source, timeout=30) as response:
            if urllib.parse.urlsplit(response.url).scheme not in ('http', 'https'):
                raise ValueError('unsupported redirect scheme')
            data = response.read(LIMIT + 1)
        # Signed query strings and fragments must not enter the provenance record.
        origin = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))
    else:
        path = Path(source).expanduser().resolve()
        if path.stat().st_size > LIMIT:
            raise ValueError('asset exceeds 32 MiB limit')
        data = path.read_bytes()
        origin = str(path)
    if not data or len(data) > LIMIT:
        raise ValueError('empty asset or asset exceeds 32 MiB limit')
    return data, origin


def xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('external entities and document types are not supported')
    return ET.fromstring(data)


def identify(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    for signature, kind in ((b'wOFF', 'woff'), (b'wOF2', 'woff2'), (b'OTTO', 'otf'), (b'\x00\x01\x00\x00', 'ttf')):
        if data.startswith(signature):
            return kind
    if data.startswith(b'%PDF-'):
        return 'pdf'
    if data[4:8] == b'ftyp' and data[8:12] in (b'avif', b'avis'):
        return 'avif'
    try:
        root = xml(data)
    except ET.ParseError as exc:
        raise ValueError('unrecognized asset; do not save an HTML/login response as an image') from exc
    tag = root.tag.split('}')[-1]
    if tag == 'vector':
        return 'vectordrawable'
    if tag == 'svg':
        for el in root.iter():
            if el.tag.split('}')[-1] not in ('svg', 'path', 'g', 'defs', 'linearGradient', 'radialGradient', 'stop', 'clipPath', 'mask', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'title', 'desc'):
                raise ValueError('unsupported/active SVG element')
            for key, value in el.attrib.items():
                if key.lower().startswith('on') or key.split('}')[-1] == 'href' or re.search(r'url\(\s*["\x27]?(?!#)', value, re.I):
                    raise ValueError('active or external SVG reference')
        return 'svg'
    raise ValueError('unsupported XML asset')


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError('expected positive finite dimension')
    return number


def svg_to_vector(data):
    """Conservative subset only: origin-zero viewBox and solid filled paths."""
    root = xml(data)
    if identify(data) != 'svg':
        raise ValueError('VectorDrawable conversion requires SVG')
    if set(root.attrib) - {'viewBox', 'width', 'height'}:
        raise ValueError('SVG root styling/transforms require an external converter')
    box = root.get('viewBox', '').replace(',', ' ').split()
    if len(box) != 4 or float(box[0]) != 0 or float(box[1]) != 0:
        raise ValueError('requires origin-zero viewBox')
    vw, vh = positive(box[2]), positive(box[3])
    width, height = positive(root.get('width', vw)), positive(root.get('height', vh))
    if not math.isclose(width / height, vw / vh):
        raise ValueError('aspect ratio changes require an external converter')
    ET.register_namespace('android', ANDROID)
    a = lambda key: '{' + ANDROID + '}' + key
    vector = ET.Element('vector', {a('width'): f'{width:g}dp', a('height'): f'{height:g}dp',
                                  a('viewportWidth'): f'{vw:g}', a('viewportHeight'): f'{vh:g}'})
    for child in root:
        if child.tag.split('}')[-1] in ('title', 'desc'):
            continue
        if child.tag.split('}')[-1] != 'path' or set(child.attrib) - {'d', 'fill', 'fill-rule'} or len(child):
            raise ValueError('only solid paths supported; preserve original and use project converter')
        fill = child.get('fill', '#000000')
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', fill):
            raise ValueError('requires explicit solid RGB fill (no themes/gradients/transparency)')
        if child.get('fill-rule', 'nonzero') not in ('nonzero', 'evenodd') or not child.get('d'):
            raise ValueError('invalid path/fill rule')
        ET.SubElement(vector, 'path', {a('pathData'): child.get('d'), a('fillColor'): fill,
                                     a('fillType'): 'evenOdd' if child.get('fill-rule') == 'evenodd' else 'nonZero'})
    if not len(vector):
        raise ValueError('empty vector')
    return ET.tostring(vector, encoding='utf-8', xml_declaration=True)


def persist(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Idempotent same-byte reruns, never silently replace a different resource.
    if path.exists():
        if not path.is_file() or path.read_bytes() != data:
            raise ValueError('refusing to overwrite: ' + str(path))
    else:
        with path.open('xb') as output:
            output.write(data)


def file_ref(path):
    return {'path': str(path.resolve()), 'sha256': sha(path.read_bytes())}


def record_path(path, base):
    """Same-anchor references move with their directory tree, including on Windows."""
    try:
        return Path(os.path.relpath(path, base)).as_posix()
    except ValueError:
        # Different Windows drives cannot share a relative path. Preserve that
        # explicit external dependency; never pretend it is self-contained.
        return str(path)


def acquire(source, target, record, design_source, variant, rule, convert='copy', glyph_map=None, converted=None, converter_description=None):
    target, record = Path(target).resolve(), Path(record).resolve()
    if not all((design_source, variant, rule)):
        raise ValueError('design source, variant and project asset rule are required')
    raw, origin = read_source(source)
    kind = identify(raw)
    if convert not in ('copy', 'svg-to-vector'):
        raise ValueError('unknown conversion')
    output = svg_to_vector(raw) if convert == 'svg-to-vector' else raw
    out_kind = 'vectordrawable' if convert == 'svg-to-vector' else kind
    if converted:
        if convert != 'copy' or not converter_description or urllib.parse.urlsplit(str(converted)).scheme in ('http', 'https'):
            raise ValueError('external conversion requires local output and tool/version/arguments')
        output, _ = read_source(str(converted))
        out_kind = identify(output)
    extensions = {'jpeg': {'.jpg', '.jpeg'}, 'vectordrawable': {'.xml'}}
    if target.suffix.lower() not in extensions.get(out_kind, {'.' + out_kind}):
        raise ValueError('target suffix does not match actual bytes')
    mapping = None
    mapping_destination = None
    if glyph_map:
        if kind not in ('ttf', 'otf', 'woff', 'woff2'):
            raise ValueError('glyph mapping only applies to fonts')
        glyph_path = Path(glyph_map).resolve()
        glyph_bytes = glyph_path.read_bytes()
        glyphs = json.loads(glyph_bytes.decode('utf-8'))
        if not glyphs or not isinstance(glyphs, dict) or any(not isinstance(k, str) or not re.fullmatch(r'U\+[0-9A-Fa-f]{4,6}', str(v)) or int(v[2:], 16) > 0x10ffff for k, v in glyphs.items()):
            raise ValueError('glyph map must map names to Unicode U+XXXX values')
        saved_map = record.parent / 'originals' / (sha(glyph_bytes) + '.glyph-map.json')
        mapping = {'path': record_path(saved_map, record.parent), 'sha256': sha(glyph_bytes)}
        mapping_destination = (saved_map, glyph_bytes)
    original = record.parent / 'originals' / (sha(raw) + '.' + kind)
    payload = {'version': 1, 'design_source': design_source, 'origin': origin, 'variant': variant,
               'asset_rule': rule, 'original': {'path': record_path(original, record.parent), 'sha256': sha(raw)},
               'output': {'path': record_path(target, record.parent), 'sha256': sha(output)}, 'format': out_kind,
               'conversion': {'tool': converter_description if converted else 'resources.py/v1', 'operation': 'external' if converted else convert},
               'glyph_map': mapping, 'integration': [], 'visual_requirements': [], 'load_requirements': []}
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    # Preflight all destinations before any files are written.
    destinations = [(original, raw), (target, output), (record, encoded)]
    if mapping_destination:
        destinations.append(mapping_destination)
    if len({p for p, _ in destinations}) != len(destinations):
        raise ValueError('original, output and record must use distinct paths')
    for path, data in destinations:
        if path.exists() and (not path.is_file() or path.read_bytes() != data):
            raise ValueError('refusing to overwrite: ' + str(path))
    for path, data in destinations:
        persist(path, data)
    return payload


def audit(record):
    path = Path(record)
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('resource record must be an object')
    errors = []
    if data.get('version') != 1:
        errors.append('unsupported resource record version')
    for field in ('design_source', 'variant', 'asset_rule', 'conversion'):
        if not data.get(field):
            errors.append('missing ' + field)
    for field in ('integration', 'visual_requirements', 'load_requirements'):
        if not isinstance(data.get(field), list):
            raise ValueError('resource record field must be a list: ' + field)
    for field in ('original', 'output'):
        try:
            ref = data[field]
            file = (path.parent / ref['path']).resolve()
            if file_ref(file)['sha256'] != ref['sha256']:
                errors.append('changed ' + field)
            if field == 'output' and identify(file.read_bytes()) != data.get('format'):
                errors.append('output format differs from record')
        except (KeyError, OSError, TypeError, ValueError, ET.ParseError):
            errors.append('missing ' + field)
    for ref in data.get('integration', []):
        try:
            file = (path.parent / ref['path']).resolve()
            if file_ref(file)['sha256'] != ref['sha256'] or not ref.get('reference') or ref['reference'] not in file.read_text(encoding='utf-8'):
                errors.append('integration reference missing or stale')
        except (OSError, KeyError, TypeError, UnicodeError):
            errors.append('integration file unavailable')
    if not data.get('integration'):
        errors.append('not integrated into project')
    if not data.get('visual_requirements') or not data.get('load_requirements'):
        errors.append('missing visual/load verification requirements')
    if data.get('format') in ('ttf', 'otf', 'woff', 'woff2'):
        ref = data.get('glyph_map')
        try:
            if not ref or file_ref((path.parent / ref['path']).resolve())['sha256'] != ref['sha256']:
                errors.append('iconfont mapping missing or stale')
        except (KeyError, OSError):
            errors.append('iconfont mapping unavailable')
    return {'ready_for_verification': not errors, 'errors': errors, 'record': data}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    get = sub.add_parser('acquire')
    for field in ('source', 'target', 'record', 'design-source', 'variant', 'rule'):
        get.add_argument('--' + field, required=True)
    get.add_argument('--convert', choices=['copy', 'svg-to-vector'], default='copy')
    get.add_argument('--glyph-map')
    get.add_argument('--converted', help='local output from an existing project converter')
    get.add_argument('--converter-description', help='converter version and exact arguments')
    check = sub.add_parser('audit')
    check.add_argument('record')
    args = parser.parse_args()
    try:
        if args.command == 'audit':
            result = audit(args.record)
            code = 0 if result['ready_for_verification'] else 1
        else:
            result = acquire(args.source, args.target, args.record, args.design_source, args.variant, args.rule, args.convert, args.glyph_map, args.converted, args.converter_description)
            code = 0
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return code
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError):
        # Do not echo signed URLs, HTTP error bodies or credentials into logs.
        print('Asset operation failed; check format, input access, destination conflicts and required metadata.')
        return 2


if __name__ == '__main__':
    configure_utf8_output()
    raise SystemExit(main())
