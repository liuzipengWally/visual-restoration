import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from evidence import digest, diagnose_v2 as verify


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.write('source', 'control implementation')
        self.write('measure.json', json.dumps({'height': {'value': 36, 'unit': 'dp'}}))
        self.write('render.png', 'synthetic render fixture, not live platform proof')
        self.write('design.png', 'synthetic design fixture')
        cap = dict(id='measure', state='default', kind='measurement',
                   artifact=self.ref('measure.json'), dependencies=[self.ref('source')],
                   code_version='test', viewport={'width': 400, 'height': 800}, scale=2,
                   theme='light', language='en', data_conditions='fixture', method='native-tree fixture')
        render = dict(cap, id='render', kind='render', artifact=self.ref('render.png'))
        self.data = dict(version=2, states=['default'], requirements=[dict(
            id='R-1', element='Call', state='*', property='geometry/height', expected=36,
            unit='dp', source='design:call', comparison=dict(mode='number', tolerance=0))],
            captures=[cap, render], observations=[dict(id='O-1', requirement='R-1', state='default',
                capture='measure', locator='height')], sweeps=[dict(state='default', capture='render',
                baseline=self.ref('design.png'), reviewer='test', regions=['page', 'controls'], findings=[])])

    def write(self, name, text):
        (self.base / name).write_text(text, encoding='utf-8')

    def ref(self, name):
        return dict(path=name, sha256=digest(self.base / name))

    def run_bundle(self):
        if 'elements' not in self.data:
            self.data['elements'] = [dict(id=e, type='control', parent=None,
                mapping={'mode': 'reuse', 'reference': 'test control'}, properties={
                    p: {'na_reason': 'isolated validator fixture, not a screen acceptance'}
                    for p in ('variant', 'visible-bounds', 'interaction-bounds', 'fill', 'border', 'radius', 'layout', 'states')
                }) for e in {r['element'] for r in self.data['requirements']}]
        self.write('design-spec.md', '\n'.join(
            '| ' + ' | '.join([r['id'], r['state'], r['element'], r['property'],
                str(r['expected']) + (' ' + r['unit'] if r['comparison']['mode'] == 'number' else ''), r['source']]) + ' |'
            for r in self.data['requirements']))
        self.data['specification'] = self.ref('design-spec.md')
        for cap in self.data['captures']:
            cap.setdefault('specification_sha256', self.data['specification']['sha256'])
        self.write('evidence.json', json.dumps(self.data))
        return verify(self.base / 'evidence.json')

    def test_complete(self):
        self.assertTrue(self.run_bundle()['complete'])

    def test_36_vs_40_cannot_be_authored_green(self):
        self.write('measure.json', json.dumps({'height': {'value': 40, 'unit': 'dp'}}))
        self.data['captures'][0]['artifact'] = self.ref('measure.json')
        self.data['observations'][0]['verdict'] = 'restored'
        self.assertEqual(self.run_bundle()['counts']['unrestored'], 1)

    def test_stale_source(self):
        self.write('source', 'changed')
        self.assertEqual(self.run_bundle()['counts']['unverified'], 1)

    def test_missing_artifact(self):
        self.data['captures'][0]['artifact']['path'] = 'missing'
        self.assertFalse(self.run_bundle()['complete'])

    def test_wrong_state(self):
        self.data['states'].append('pressed')
        self.assertEqual(self.run_bundle()['counts']['unverified'], 1)

    def test_missing_split_control(self):
        req = copy.deepcopy(self.data['requirements'][0])
        req.update(id='R-2', element='VideoDisclosure', property='visibility/present', expected=True,
                   unit='boolean', comparison={'mode': 'equals'})
        self.data['requirements'].append(req)
        self.assertFalse(self.run_bundle()['complete'])

    def test_source_cannot_prove_geometry(self):
        self.data['captures'][0]['kind'] = 'source'
        self.assertEqual(self.run_bundle()['counts']['unverified'], 1)

    def visual(self):
        self.data['requirements'][0].update(property='shape/silhouette', comparison={'mode': 'visual'},
                                            baseline=self.ref('design.png'))
        self.data['observations'][0].update(capture='render', locator='crop(1,1,20,20)', design_locator='crop(1,1,20,20)',
            review={'reviewer': 'test', 'details': 'different bubble contour', 'match': False})

    def test_icon_semantics_do_not_prove_shape(self):
        self.visual()
        self.assertEqual(self.run_bundle()['counts']['unrestored'], 1)

    def test_source_cannot_prove_visual(self):
        self.visual()
        self.data['captures'][1]['kind'] = 'source'
        self.assertEqual(self.run_bundle()['counts']['unverified'], 1)

    def test_sweep_reopens_pass(self):
        self.data['sweeps'][0]['findings'] = [{'description': 'missing disclosure', 'requirements': ['R-1']}]
        self.assertEqual(self.run_bundle()['counts']['unrestored'], 1)

    def test_unmapped_sweep_blocks(self):
        self.data['sweeps'][0]['findings'] = [{'description': 'missing disclosure', 'requirements': []}]
        self.assertFalse(self.run_bundle()['complete'])

    def test_dynamic_data_constraint(self):
        self.write('measure.json', json.dumps({'height': {'value': '真实联系人', 'unit': 'text'}}))
        self.data['captures'][0]['artifact'] = self.ref('measure.json')
        self.data['requirements'][0].update(property='copy/name', unit='text', expected='nonempty',
                                            comparison={'mode': 'content', 'min_length': 1})
        self.assertTrue(self.run_bundle()['complete'])

    def test_duplicate_observation(self):
        self.data['observations'].append(dict(self.data['observations'][0], id='O-2'))
        self.assertFalse(self.run_bundle()['complete'])

    def test_units_are_not_interchangeable(self):
        self.data['requirements'][0]['unit'] = 'px'
        self.assertFalse(self.run_bundle()['complete'])

    def test_adapter_independent(self):
        for method in ['web-dom fixture', 'native-view-tree fixture', 'desktop-preview fixture']:
            self.data['captures'][0]['method'] = method
            self.assertTrue(self.run_bundle()['complete'])

    def test_unenumerated_control_properties_block(self):
        self.run_bundle()
        self.data['elements'][0]['properties'] = {}
        self.assertFalse(self.run_bundle()['complete'])

    def test_checklist_subset_cannot_pass(self):
        self.run_bundle()
        self.data['requirements'] = []
        self.write('evidence.json', json.dumps(self.data))
        with self.assertRaises(ValueError):
            verify(self.base / 'evidence.json')

    def test_changed_spec_invalidates_capture(self):
        self.run_bundle()
        source = (self.base / 'design-spec.md').read_text(encoding='utf-8')
        self.write('design-spec.md', source + '\nrevised context')
        self.data['specification'] = self.ref('design-spec.md')
        self.write('evidence.json', json.dumps(self.data))
        self.assertEqual(verify(self.base / 'evidence.json')['counts']['unverified'], 1)

    def test_shape_cannot_use_asset_name_equality(self):
        self.data['requirements'][0].update(property='shape/silhouette', comparison={'mode': 'equals'})
        with self.assertRaises(ValueError):
            self.run_bundle()

    def test_nan_tolerance_rejected(self):
        self.data['requirements'][0]['comparison']['tolerance'] = float('nan')
        self.assertEqual(self.run_bundle()['counts']['unverified'], 1)

    def test_incomplete_adaptation_cannot_waive_difference(self):
        self.data['observations'][0]['adaptation'] = {'reason': 'platform'}
        self.assertEqual(self.run_bundle()['counts']['unverified'], 1)

    def test_generic_visual_review_rejected(self):
        self.visual()
        self.data['observations'][0]['review'].update(match=True, details='looks good')
        self.assertEqual(self.run_bundle()['counts']['unverified'], 1)

    def test_visual_requires_concrete_crops(self):
        self.visual()
        self.data['observations'][0]['locator'] = 'runtime screenshot'
        self.assertEqual(self.run_bundle()['counts']['unverified'], 1)

    def test_expected_cannot_be_replaced_with_actual(self):
        self.run_bundle()
        self.data['requirements'][0]['expected'] = 40
        self.write('evidence.json', json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, 'expectation differs'):
            verify(self.base / 'evidence.json')

    def imported_icon(self):
        self.visual()
        self.data['observations'][0]['review']['match'] = True
        self.data['elements'] = [dict(id='Call', type='icon', parent=None,
            mapping={'mode': 'new', 'reference': 'asset.svg'},
            properties={p: {'na_reason': 'isolated integration test'} for p in
                        ('resource', 'silhouette', 'bounds', 'color', 'stroke', 'whitespace')})]

    def test_imported_icon_requires_resource_record(self):
        self.imported_icon()
        report = self.run_bundle()
        self.assertFalse(report['complete'])
        self.assertTrue(report['resource_errors'])

    def test_imported_icon_requires_actual_load_and_visual_match(self):
        from resources import acquire
        self.imported_icon()
        self.write('original.svg', '<svg viewBox="0 0 20 20"><path d="M0 0 L20 20"/></svg>')
        record = acquire(str(self.base / 'original.svg'), self.base / 'asset.svg', self.base / 'resource.json',
                         'design:icon', 'default', 'project/assets')
        record['integration'] = [dict(self.ref('source'), reference='control implementation')]
        record.update(visual_requirements=['R-1'], load_requirements=['R-load'])
        self.write('resource.json', json.dumps(record))
        self.data['elements'][0]['resource_records'] = [self.ref('resource.json')]
        self.data['requirements'].append(dict(id='R-load', element='Call', state='default',
            property='visibility/resource-loaded', expected=True, unit='boolean', source='design:icon',
            comparison={'mode': 'equals'}))
        self.write('measure.json', json.dumps({'loaded': {'value': True, 'unit': 'boolean'}}))
        self.data['captures'][0]['artifact'] = self.ref('measure.json')
        self.data['observations'].append(dict(id='O-load', requirement='R-load', state='default', capture='measure', locator='loaded'))
        self.assertTrue(self.run_bundle()['complete'])
        self.data['observations'][0]['review']['match'] = False
        self.assertFalse(self.run_bundle()['complete'])

    def test_resource_download_alone_is_not_visual_acceptance(self):
        from resources import acquire
        self.imported_icon()
        self.write('original.svg', '<svg viewBox="0 0 20 20"><path d="M0 0 L20 20"/></svg>')
        acquire(str(self.base / 'original.svg'), self.base / 'asset.svg', self.base / 'resource.json',
                'design:icon', 'default', 'project/assets')
        self.data['elements'][0]['resource_records'] = [self.ref('resource.json')]
        self.assertFalse(self.run_bundle()['complete'])
