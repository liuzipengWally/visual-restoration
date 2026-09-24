import io
import json
import ntpath
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from resources import acquire, audit, file_ref, identify, read_source, record_path, sha, svg_to_vector

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path fill="#000000" d="M2 2 L18 2 L18 18 Z"/></svg>'


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='asset space ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / '设计.svg'
        self.source.write_bytes(SVG)
        self.target = self.root / 'project' / 'icon.svg'
        self.record = self.root / 'evidence' / 'resource.json'

    def acquire(self, **kwargs):
        return acquire(str(self.source), self.target, self.record,
                       'design:node-123', 'default/20/light', 'assets/*.svg; e.g. existing.svg', **kwargs)

    def test_copy_retains_original_and_hashes(self):
        result = self.acquire()
        self.assertEqual(SVG, self.target.read_bytes())
        self.assertEqual(SVG, (self.record.parent / result['original']['path']).read_bytes())
        self.assertEqual(sha(SVG), result['output']['sha256'])
        self.assertFalse(audit(self.record)['ready_for_verification'])

    def test_identical_rerun_is_idempotent(self):
        self.assertEqual(self.acquire(), self.acquire())

    def integrate(self, result):
        entry = self.target.parent / 'entry.txt'
        entry.write_text(self.target.name, encoding='utf-8')
        result['integration'] = [dict(file_ref(entry),
            path=record_path(entry, self.record.parent), reference=self.target.name)]
        result.update(visual_requirements=['R-contour'], load_requirements=['R-loaded'])
        self.record.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')

    def test_new_references_are_relative_to_record(self):
        result = self.acquire()
        for key in ('original', 'output'):
            ref = result[key]
            self.assertFalse(Path(ref['path']).is_absolute())
            self.assertNotIn('\\', ref['path'])
            self.assertEqual(ref['sha256'], sha((self.record.parent / ref['path']).read_bytes()))

    def test_project_move_preserves_ready_record_bytes_and_hash(self):
        project = self.root / 'before'
        self.target = project / 'assets' / '图标.svg'
        self.record = project / 'specs' / 'task' / 'resources' / 'icon.json'
        self.integrate(self.acquire())
        before = self.record.read_bytes()
        self.assertTrue(audit(self.record)['ready_for_verification'])
        moved = self.root / 'after'
        project.rename(moved)
        relocated = moved / self.record.relative_to(project)
        self.assertEqual(before, relocated.read_bytes())
        self.assertEqual(sha(before), file_ref(relocated)['sha256'])
        self.assertTrue(audit(relocated)['ready_for_verification'])

    def test_legacy_absolute_record_is_read_without_rewriting(self):
        result = self.acquire()
        self.integrate(result)
        for ref in [result['original'], result['output'], *result['integration']]:
            ref['path'] = str((self.record.parent / ref['path']).resolve())
        self.record.write_text(json.dumps(result), encoding='utf-8')
        before = self.record.read_bytes()
        self.assertTrue(audit(self.record)['ready_for_verification'])
        self.assertEqual(before, self.record.read_bytes())

    def test_external_glyph_map_is_preserved_and_moves_with_record(self):
        project = self.root / 'font-project'
        self.source.write_bytes(b'wOF2' + b'synthetic font bytes')
        self.target = project / 'assets' / 'icons.woff2'
        self.record = project / 'specs' / 'resources' / 'font.json'
        mapping = self.root / 'exported-map.json'
        raw = b'{"call":"U+E001"}'
        mapping.write_bytes(raw)
        result = self.acquire(glyph_map=str(mapping))
        self.assertEqual(result, self.acquire(glyph_map=str(mapping)))
        saved = self.record.parent / result['glyph_map']['path']
        self.assertEqual(raw, saved.read_bytes())
        self.assertNotEqual(saved.resolve(), mapping.resolve())
        self.integrate(result)
        mapping.unlink()  # Disposable export; only the archived bytes are needed.
        moved = self.root / 'moved-font-project'
        project.rename(moved)
        self.assertTrue(audit(moved / self.record.relative_to(project))['ready_for_verification'])

    def test_glyph_map_conflict_is_checked_before_writing_other_files(self):
        self.source.write_bytes(b'wOF2' + b'synthetic font bytes')
        self.target = self.target.with_suffix('.woff2')
        mapping = self.root / 'exported-map.json'
        raw = b'{"call":"U+E001"}'
        mapping.write_bytes(raw)
        conflict = self.record.parent / 'originals' / (sha(raw) + '.glyph-map.json')
        conflict.parent.mkdir(parents=True)
        conflict.write_bytes(b'other data')
        with self.assertRaisesRegex(ValueError, 'refusing to overwrite'):
            self.acquire(glyph_map=str(mapping))
        self.assertFalse(self.target.exists())
        self.assertFalse(self.record.exists())
        self.assertEqual(b'other data', conflict.read_bytes())

    def test_cross_drive_reference_stays_explicitly_external(self):
        # Pure Windows path semantics, not a claim of Windows device execution.
        with patch('resources.os.path.relpath', side_effect=ntpath.relpath):
            self.assertEqual('D:/assets/icon.svg', record_path('D:/assets/icon.svg', 'C:/specs'))

    def test_existing_different_asset_preserved(self):
        self.target.parent.mkdir()
        self.target.write_bytes(b'existing')
        with self.assertRaises(ValueError):
            self.acquire()
        self.assertEqual(b'existing', self.target.read_bytes())
        self.assertFalse(self.record.exists())

    def test_record_conflict_preflight(self):
        self.record.parent.mkdir()
        self.record.write_text('existing', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.acquire()
        self.assertFalse(self.target.exists())

    def test_html_response_rejected(self):
        self.source.write_bytes(b'<html>login required</html>')
        with self.assertRaises(ValueError):
            self.acquire()

    def test_suffix_not_renamed_blindly(self):
        self.target = self.target.with_suffix('.png')
        with self.assertRaises(ValueError):
            self.acquire()

    def test_vector_conversion_preserves_path_and_viewport(self):
        root = ET.fromstring(svg_to_vector(SVG))
        ns = '{http://schemas.android.com/apk/res/android}'
        self.assertEqual('20', root.get(ns + 'viewportWidth'))
        self.assertEqual('20dp', root.get(ns + 'width'))
        self.assertEqual('M2 2 L18 2 L18 18 Z', root[0].get(ns + 'pathData'))

    def test_vector_install(self):
        self.target = self.target.with_suffix('.xml')
        self.assertEqual('vectordrawable', self.acquire(convert='svg-to-vector')['format'])

    def test_unsupported_conversion_features_fail(self):
        for attr in (b'transform="scale(2)"', b'stroke="#ff0000"', b'opacity="0.5"'):
            with self.subTest(attr=attr), self.assertRaises(ValueError):
                svg_to_vector(SVG.replace(b'<path ', b'<path ' + attr + b' '))

    def test_nonzero_viewbox_rejected(self):
        with self.assertRaises(ValueError):
            svg_to_vector(SVG.replace(b'0 0 20 20', b'2 2 20 20'))

    def test_active_svg_rejected(self):
        for data in (b'<svg><script>bad()</script></svg>', b'<svg onload="bad()"/>', b'<!DOCTYPE svg><svg/>', b'<svg><path fill="url(https://example.com/a)"/></svg>'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                identify(data)

    def test_signed_url_not_persisted(self):
        response = io.BytesIO(SVG)
        response.url = 'https://assets.example.invalid/icon.svg?temporary=redacted'
        with patch('resources.urllib.request.urlopen', return_value=response):
            data, origin = read_source(response.url)
        self.assertEqual(SVG, data)
        self.assertEqual('https://assets.example.invalid/icon.svg', origin)

    def test_basic_auth_url_rejected(self):
        auth_url = 'https://' + 'user' + ':' + 'password' + '@example.invalid/icon.svg'
        with self.assertRaises(ValueError):
            read_source(auth_url)

    def test_download_size_limit(self):
        response = io.BytesIO(SVG)
        response.url = 'https://example.com/icon.svg'
        with patch('resources.LIMIT', 10), patch('resources.urllib.request.urlopen', return_value=response), self.assertRaises(ValueError):
            read_source(response.url)

    def test_external_conversion_requires_provenance(self):
        with self.assertRaises(ValueError):
            self.acquire(converted=self.source)
        result = self.acquire(converted=self.source, converter_description='project converter v1 --preserve-paths input.svg output.svg')
        self.assertEqual('external', result['conversion']['operation'])

    def test_stale_integration_fails(self):
        result = self.acquire()
        integration = self.root / 'entry.txt'
        integration.write_text('icon.svg', encoding='utf-8')
        result['integration'] = [{'path': str(integration), 'sha256': sha(integration.read_bytes()), 'reference': 'icon.svg'}]
        result.update(visual_requirements=['R-1'], load_requirements=['R-2'])
        self.record.write_text(json.dumps(result), encoding='utf-8')
        self.assertTrue(audit(self.record)['ready_for_verification'])
        integration.write_text('different.svg', encoding='utf-8')
        self.assertFalse(audit(self.record)['ready_for_verification'])

    def test_iconfont_without_mapping_is_not_ready(self):
        self.source.write_bytes(b'wOF2' + b'font fixture')
        self.target = self.target.with_suffix('.woff2')
        self.acquire()
        self.assertIn('iconfont mapping missing or stale', audit(self.record)['errors'])

    def test_invalid_glyph_mapping_rejected(self):
        self.source.write_bytes(b'wOF2' + b'font fixture')
        self.target = self.target.with_suffix('.woff2')
        mapping = self.root / 'map.json'
        mapping.write_text('{"call":"guessed"}', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.acquire(glyph_map=str(mapping))

    def test_changed_output_invalidates_record(self):
        self.acquire()
        self.target.write_bytes(SVG.replace(b'20', b'24'))
        self.assertIn('changed output', audit(self.record)['errors'])

    def test_aspect_ratio_conversion_rejected(self):
        with self.assertRaises(ValueError):
            svg_to_vector(SVG.replace(b'viewBox=', b'width="40" height="20" viewBox='))

    def test_malformed_resource_record_rejected(self):
        self.record.parent.mkdir()
        self.record.write_text('[]', encoding='utf-8')
        with self.assertRaises(ValueError):
            audit(self.record)
