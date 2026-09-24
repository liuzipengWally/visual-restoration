"""Synthetic contract fixtures: no screenshot/device truth is claimed here."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from evidence import digest, verify, mapping_fingerprint
from mapping import PROPERTIES, SEMANTICS, check_map
import uir


class BundleFixture:
    def __init__(self, base):
        self.base = base
        self.write('control.code', 'public Action(size, variant); draw fill in artwork')
        self.write('wrapper.code', 'theme and wrapper fixture')
        self.write('design.png', 'synthetic design bytes, not an actual screenshot')
        self.write('render.png', 'synthetic render bytes, not actual platform validation')
        source = dict(kind='screenshot', artifact=self.ref('design.png'), locator='crop(0,0,36,36)')
        self.data = dict(version=3, platform='fixture renderer', states=['default'],
            design_languages=[dict(id='language', status='unknown', name=None,
                reason='Screenshot has no library provenance; observable constraints suffice',
                evidence=[dict(source=source, detail='Outlined control with explicit dimensions')])],
            design_inventory=[dict(id='D-call', source=source, children=[], disposition='build', element='Call')],
            design_review=dict(reviewer='fixture author', inventory_complete=True,
                details='Isolated single control; no other independently styled elements in this fixture'),
            elements=[dict(id='Call', parent=None, type='control', design_language='language', design_refs=['D-call'],
                mapping=dict(mode='reuse', reference='Action', system='fixture components',
                    parameters={'size': 36, 'variant': 'outlined'},
                    rationale='Inspected public API exposes specified shape and size',
                    code_evidence=[dict(self.ref('control.code'), locator='Action', detail='public size and variant API')],
                    style_dependencies=[self.ref('wrapper.code')],
                    render_chain=[dict(role='configuration', reference='Action', effect='size and variant'),
                                  dict(role='theme/wrapper', reference='wrapper.code', effect='color tokens applied'),
                                  dict(role='drawing', reference='artwork', effect='visible fill and border')]),
                properties={})], requirements=[], captures=[], observations=[], sweeps=[],
            implementation=dict(status='complete', dependencies=[self.ref('control.code'), self.ref('wrapper.code')]))
        self.measurements = {}
        for prop, semantic, expected, unit, mode in [
            ('variant', 'component/variant', 'outlined', 'name', 'equals'),
            ('visible-bounds', 'geometry/height', 36, 'dp', 'number'),
            ('interaction-bounds', 'interaction/height', 48, 'dp', 'number'),
            ('fill', 'color/fill', '#ffffff', 'sRGB', 'equals'),
            ('border', 'shape/border-width', 1, 'dp', 'number'),
            ('radius', 'shape/corner-radius', 8, 'dp', 'number'),
            ('layout', 'geometry/alignment', 'center', 'alignment', 'equals'),
            ('states', 'interaction/states', 'default', 'name', 'equals'),
        ]:
            rid = self.add_req(semantic, expected, unit, mode)
            self.data['elements'][0]['properties'][prop] = {'requirements': [rid]}
        self.refresh_measurements()
        self.write('build.json', json.dumps(dict(id='built-1', method='synthetic build association',
                                               dependencies=self.data['implementation']['dependencies'])))
        cap = dict(id='measure', state='default', kind='measurement', artifact=self.ref('measure.json'),
            dependencies=copy.deepcopy(self.data['implementation']['dependencies']),
            code_version='fixture revision with dependency hashes', viewport={'width': 100, 'height': 100, 'unit': 'dp'},
            scale=2, theme='light', language='en', data_conditions={}, method='fixture captured drawing measurements',
            build_id='built-1', build=self.ref('build.json'))
        self.data['captures'] = [cap, dict(cap, id='render', kind='render', artifact=self.ref('render.png'))]
        self.data['sweeps'] = [dict(state='default', capture='render', baseline=self.ref('design.png'),
            reviewer='fixture author', regions=['page', 'controls'], findings=[])]

    def write(self, name, content):
        (self.base / name).write_text(content, encoding='utf-8')

    def ref(self, name):
        return dict(path=name, sha256=digest(self.base / name))

    def add_req(self, prop, expected, unit, mode='equals', element='Call', design='D-call', conditions=None):
        rid = 'R-' + str(len(self.data['requirements']) + 1).zfill(3)
        comparison = dict(mode=mode)
        if mode == 'number':
            comparison['tolerance'] = 0
        req = dict(id=rid, element=element, state='*', property=prop, expected=expected, unit=unit,
                   source='screenshot design.png crop(0,0,36,36)', design_ref=design,
                   applies_when=conditions or {}, comparison=comparison)
        self.data['requirements'].append(req)
        self.measurements[rid] = dict(value=expected, unit=unit, element=element, property=prop, surface='fixture artwork')
        self.data['observations'].append(dict(id='O-' + rid, requirement=rid, state='default', capture='measure', locator=rid))
        return rid

    def refresh_measurements(self):
        self.write('measure.json', json.dumps(self.measurements))
        for cap in self.data['captures']:
            if cap['id'] == 'measure':
                cap['artifact'] = self.ref('measure.json')

    def save(self):
        self.write('design-spec.md', '\n'.join('| ' + ' | '.join([
            r['id'], r['state'], r['element'], r['property'],
            str(r['expected']) + (' ' + r['unit'] if r['comparison']['mode'] == 'number' else ''), r['source']]) + ' |'
            for r in self.data['requirements']))
        self.data['specification'] = self.ref('design-spec.md')
        for cap in self.data['captures']:
            cap.setdefault('specification_sha256', self.data['specification']['sha256'])
            cap.setdefault('mapping_sha256', mapping_fingerprint(self.data))
        self.write('evidence.json', json.dumps(self.data))
        return self.base / 'evidence.json'


class V3Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.fx = BundleFixture(Path(tmp.name))
        self.data = self.fx.data

    def mapping(self):
        return check_map(self.fx.save())

    def report(self):
        return verify(self.fx.save())

    def test_complete_synthetic_bundle(self):
        report = self.report()
        self.assertTrue(report['complete'], report)
        self.assertTrue(report['mapping_complete'])
        self.assertTrue(report['implementation_complete'])
        self.assertTrue(report['visually_verified'])

    def test_preimplementation_does_not_require_runtime(self):
        self.data.update(captures=[], observations=[], sweeps=[], implementation={'status': 'pending'})
        self.assertTrue(self.mapping()['mapping_complete'])
        report = self.report()
        self.assertFalse(report['implementation_complete'])
        self.assertFalse(report['visually_verified'])

    def test_height_cannot_cover_fill_border_radius(self):
        for prop in ('fill', 'border', 'radius'):
            with self.subTest(prop=prop):
                properties = self.data['elements'][0]['properties']
                old = properties[prop]
                properties[prop] = {'requirements': ['R-002']}
                report = self.mapping()
                self.assertFalse(report['mapping_complete'])
                self.assertIn('incompatible requirement', str(report))
                properties[prop] = old

    def test_legacy_false_positive_now_requires_migration_and_fails_v3(self):
        for prop in ('fill', 'border', 'radius'):
            self.data['elements'][0]['properties'][prop] = {'requirements': ['R-002']}
        self.data['version'] = 2
        for cap in self.data['captures']:
            cap['data_conditions'] = 'historical fixture'
        historical = self.report()
        self.assertTrue(historical['legacy_diagnostic']['complete'])
        self.assertFalse(historical['complete'])
        self.data['version'] = 3
        self.assertFalse(self.mapping()['mapping_complete'])

    def test_geometry_cannot_cover_interaction_size(self):
        self.data['elements'][0]['properties']['interaction-bounds']['requirements'] = ['R-002']
        self.assertFalse(self.mapping()['mapping_complete'])

    def test_pending_expected_cannot_pass_mapping(self):
        self.data['requirements'][0]['expected'] = 'TBD: exact variant unavailable'
        self.assertIn('unresolved design expectation', str(self.mapping()))

    def test_property_cannot_be_both_covered_and_not_applicable(self):
        self.data['elements'][0]['properties']['fill']['na_reason'] = 'not measured'
        self.assertFalse(self.mapping()['mapping_complete'])

    def test_properties_cannot_silently_omit_a_defined_state(self):
        self.data['states'].append('pressed')
        self.data['requirements'][0]['state'] = 'default'
        self.assertFalse(self.mapping()['mapping_complete'])

    def test_mapping_to_not_yet_created_target_supported(self):
        self.data['elements'][0]['mapping'].update(mode='new', reference='proposed/new-control',
            rationale='Inspected API and project convention support a scoped new control')
        self.data.update(implementation={'status': 'pending'}, captures=[], observations=[], sweeps=[])
        self.assertTrue(self.mapping()['mapping_complete'])
        self.assertFalse(self.report()['implementation_complete'])

    def test_compound_child_missing_from_elements(self):
        self.data['design_inventory'][0]['children'] = ['D-disclosure']
        self.data['design_inventory'].append(dict(self.data['design_inventory'][0], id='D-disclosure',
                                                 children=[], element='Disclosure'))
        self.assertFalse(self.mapping()['mapping_complete'])

    def test_contacts_coarse_action_region_mapping_rejected(self):
        # Replays the failure shape: only parent width/height/gap mapped, despite
        # the design inventory containing normal/split controls and artwork.
        root = self.data['elements'][0]
        root.update(id='ContactActions', type='container')
        root['properties'] = {p: {'na_reason': 'isolated coarse-mapping replay'} for p in PROPERTIES['container']}
        height = self.data['requirements'][1]
        height.update(element='ContactActions')
        self.data['requirements'] = [height]
        root['properties']['bounds'] = {'requirements': ['R-002']}
        self.data['design_inventory'][0]['element'] = 'ContactActions'
        self.data.update(captures=[], observations=[], sweeps=[])
        for name in ('Message', 'MeetingSplit', 'Call', 'Fax'):
            iid = 'D-' + name
            self.data['design_inventory'][0]['children'].append(iid)
            self.data['design_inventory'].append(dict(id=iid,
                source=self.data['design_inventory'][0]['source'], children=[], disposition='build', element=name))
        report = self.mapping()
        self.assertFalse(report['mapping_complete'])
        self.assertIn('compound child not independently mapped', str(report))
        self.assertIn('no reciprocal element mapping', str(report))

    def test_compound_child_not_even_in_inventory(self):
        self.data['design_inventory'][0]['children'] = ['D-disclosure']
        self.assertIn('missing/duplicate compound design child', str(self.mapping()))

    def test_inventory_cycle_rejected(self):
        self.data['design_inventory'][0]['children'] = ['D-call']
        self.assertFalse(self.mapping()['mapping_complete'])

    def child(self):
        child = copy.deepcopy(self.data['elements'][0])
        child.update(id='Child', parent='Call', design_refs=['D-child'])
        child['properties'] = {prop: {'na_reason': 'isolated hierarchy fixture'} for prop in PROPERTIES['control']}
        self.data['elements'].append(child)
        self.data['design_inventory'][0]['children'] = ['D-child']
        self.data['design_inventory'].append(dict(self.data['design_inventory'][0], id='D-child', children=[], element='Child'))

    def test_declared_child_requires_presence_row(self):
        self.child()
        self.assertIn('visibility/present', str(self.mapping()))
        self.fx.add_req('visibility/present', True, 'boolean', element='Child', design='D-child')
        self.assertTrue(self.mapping()['mapping_complete'])

    def test_child_cannot_borrow_parent_requirements(self):
        self.child()
        self.data['elements'][1]['properties']['fill'] = {'requirements': ['R-004']}
        self.assertIn('incompatible requirement', str(self.mapping()))

    def test_missing_observation_is_not_implementation_failure(self):
        self.data['observations'].pop()
        report = self.report()
        self.assertTrue(report['mapping_complete'])
        self.assertTrue(report['implementation_complete'])
        self.assertFalse(report['visually_verified'])
        self.assertEqual(report['counts']['unverified'], 1)

    def test_same_library_wrong_variant_is_unrestored(self):
        self.fx.measurements['R-001']['value'] = 'filled'
        self.fx.refresh_measurements()
        self.assertEqual(self.report()['counts']['unrestored'], 1)

    def test_cross_system_identity_does_not_fail_visual_match(self):
        self.data['design_languages'][0].update(status='inferred', name='Visual language A')
        self.data['elements'][0]['mapping']['system'] = 'Component system B'
        self.assertTrue(self.report()['complete'])

    def test_unknown_language_valid_with_screenshot_evidence(self):
        self.assertTrue(self.mapping()['mapping_complete'])

    def test_language_cannot_be_asserted_without_evidence(self):
        self.data['design_languages'][0]['evidence'] = []
        self.assertFalse(self.mapping()['mapping_complete'])

    def test_node_design_source_supported(self):
        source = dict(kind='node', document='local-design-document', locator='component:42')
        self.data['design_inventory'][0]['source'] = source
        self.data['design_languages'][0]['evidence'][0]['source'] = source
        self.assertTrue(self.mapping()['mapping_complete'])

    def test_candidate_parameters_and_code_inspection_required(self):
        mapping = self.data['elements'][0]['mapping']
        for key in ('parameters', 'code_evidence', 'render_chain', 'style_dependencies'):
            with self.subTest(key=key):
                old = mapping.pop(key)
                self.assertFalse(self.mapping()['mapping_complete'])
                mapping[key] = old

    def test_changed_wrapper_reopens_mapping_and_implementation(self):
        self.fx.write('wrapper.code', 'changed wrapper fill')
        report = self.report()
        self.assertFalse(report['mapping_complete'])
        self.assertFalse(report['implementation_complete'])
        self.assertGreater(report['counts']['unverified'], 0)

    def test_current_source_cannot_refresh_old_build(self):
        manifest = json.loads((self.fx.base / 'build.json').read_text(encoding='utf-8'))
        manifest['dependencies'][0]['sha256'] = '0' * 64
        self.fx.write('build.json', json.dumps(manifest))
        for cap in self.data['captures']:
            cap['build'] = self.fx.ref('build.json')
        self.assertIn('stale build', str(self.report()))
        self.assertFalse(self.report()['complete'])

    def test_running_build_id_mismatch(self):
        self.data['captures'][0]['build_id'] = 'previous-build'
        self.assertIn('running build identity', str(self.report()))

    def test_build_missing_does_not_stop_mapping_but_leaves_unverified(self):
        for cap in self.data['captures']:
            del cap['build']
        self.assertTrue(self.mapping()['mapping_complete'])
        self.assertFalse(self.report()['complete'])

    def test_implementation_cannot_omit_declared_wrapper(self):
        self.data['implementation']['dependencies'].pop()
        self.assertFalse(self.report()['implementation_complete'])

    def test_wrong_or_missing_data_keeps_designed_control_unverified(self):
        self.data['requirements'][1]['applies_when'] = {'meetingAvailable': True}
        for facts in ({}, {'meetingAvailable': False}, {'meetingAvailable': 1}):
            with self.subTest(facts=facts):
                self.data['captures'][0]['data_conditions'] = facts
                report = self.report()
                self.assertEqual(report['counts']['unverified'], 1)
        self.data['captures'][0]['data_conditions'] = {'meetingAvailable': True}
        self.assertTrue(self.report()['complete'])

    def test_conditions_must_be_declared_before_implementation(self):
        del self.data['requirements'][0]['applies_when']
        self.assertFalse(self.mapping()['mapping_complete'])

    def test_conditions_changed_after_capture_reopens_evidence(self):
        self.fx.save()
        self.data['requirements'][0]['applies_when'] = {'account': 'changed'}
        self.data['captures'][0]['data_conditions'] = {'account': 'changed'}
        self.assertIn('different mapping/condition revision', str(self.report()))

    def test_render_scale_must_be_real_and_positive(self):
        for value in (0, -1, True, float('nan')):
            self.data['captures'][0]['scale'] = value
            self.assertFalse(self.report()['complete'])

    def test_source_identity_cannot_prove_rendered_fill(self):
        self.data['captures'][0]['kind'] = 'source'
        self.assertGreater(self.report()['counts']['unverified'], 0)

    def test_measurement_cannot_borrow_host_or_another_property(self):
        self.fx.measurements['R-004']['property'] = 'geometry/height'
        self.fx.refresh_measurements()
        self.assertIn('element/property/surface', str(self.report()))

    def test_measurement_surface_is_required(self):
        del self.fx.measurements['R-004']['surface']
        self.fx.refresh_measurements()
        self.assertFalse(self.report()['complete'])

    def test_icon_silhouette_cannot_be_resource_name_equality(self):
        req = self.data['requirements'][0]
        req.update(property='shape/silhouette', baseline=self.fx.ref('design.png'))
        with self.assertRaisesRegex(ValueError, 'visual comparison'):
            self.mapping()

    def visual(self):
        self.data['requirements'][5].update(property='shape/contour', expected='rounded contour', unit='visual',
            comparison={'mode': 'visual'}, baseline=self.fx.ref('design.png'))
        self.data['observations'][5].update(capture='render', locator='crop(0,0,36,36)',
            design_locator='crop(0,0,36,36)', review=dict(reviewer='fixture',
                details='Compared four corner contours and edge curvature in synthetic case', match=True))

    def test_visual_contour_comparison_uses_render(self):
        self.visual()
        self.assertTrue(self.report()['complete'])
        self.data['observations'][5]['review']['match'] = False
        self.assertEqual(self.report()['counts']['unrestored'], 1)

    def test_visual_review_missing_is_unverified(self):
        self.visual()
        del self.data['observations'][5]['review']
        self.assertFalse(self.report()['complete'])

    def test_visual_measurement_cannot_use_source_capture(self):
        self.visual()
        self.data['captures'][1]['kind'] = 'source'
        self.assertFalse(self.report()['complete'])

    def test_visual_adaptation_requires_approved_baseline_and_observation(self):
        self.visual()
        self.data['adaptations'] = [dict(id='A-contour', requirement='R-006', property='shape/contour',
            states=['default'], reason='fixture approved contour replacement', authority='fixture approval 3',
            replacement=dict(baseline=self.fx.ref('design.png'), locator='crop(0,0,36,36)'),
            remaining_requirements=['R-004'])]
        obs = self.data['observations'][5]
        obs.update(adaptation='A-contour', adaptation_design_locator='crop(0,0,36,36)',
            adaptation_review=dict(reviewer='fixture', details='Approved contour corners and edges compared', match=True))
        self.assertTrue(self.report()['complete'])
        obs['adaptation_review']['match'] = False
        self.assertEqual(self.report()['counts']['unrestored'], 1)

    def adaptation(self):
        self.data['adaptations'] = [dict(id='A-height', requirement='R-002', property='geometry/height',
            states=['default'], reason='Explicitly approved alternate visual height in fixture',
            authority='fixture approval paragraph 2', replacement=dict(expected=40, unit='dp', tolerance=0),
            remaining_requirements=['R-004'])]
        self.data['observations'][1]['adaptation'] = 'A-height'
        self.fx.measurements['R-002']['value'] = 40
        self.fx.refresh_measurements()

    def test_specific_approved_replacement_observed(self):
        self.adaptation()
        report = self.report()
        self.assertTrue(report['complete'], report)
        self.assertEqual(report['counts']['adapted'], 1)

    def test_adaptation_for_unrelated_property_rejected(self):
        self.adaptation()
        self.data['adaptations'][0]['property'] = 'color/fill'
        self.assertFalse(self.report()['complete'])
        self.assertFalse(self.mapping()['mapping_complete'])

    def test_adaptation_does_not_ignore_replacement_difference(self):
        self.adaptation()
        self.fx.measurements['R-002']['value'] = 44
        self.fx.refresh_measurements()
        self.assertEqual(self.report()['counts']['unrestored'], 1)

    def test_adaptation_preserved_rows_must_pass(self):
        self.adaptation()
        self.data['observations'].pop(3)
        report = self.report()
        self.assertEqual(report['counts']['adapted'], 0)
        self.assertFalse(report['complete'])

    def test_adaptation_cannot_preserve_itself(self):
        self.adaptation()
        self.data['adaptations'][0]['remaining_requirements'] = ['R-002']
        self.assertFalse(self.mapping()['mapping_complete'])

    def test_unrelated_observation_cannot_use_adaptation(self):
        self.adaptation()
        self.data['observations'][3]['adaptation'] = 'A-height'
        self.assertGreater(self.report()['counts']['unverified'], 0)

    def test_missing_observation_cannot_be_adapted(self):
        self.adaptation()
        self.data['observations'].pop(1)
        report = self.report()
        self.assertEqual(report['counts']['adapted'], 0)
        self.assertFalse(report['complete'])

    def test_sweep_reopens_adapted_row(self):
        self.adaptation()
        self.data['sweeps'][0]['findings'] = [dict(description='approved height still differs', requirements=['R-002'])]
        self.assertEqual(self.report()['counts']['unrestored'], 1)

    def test_v2_never_gets_new_acceptance(self):
        self.data['version'] = 2
        for cap in self.data['captures']:
            cap['data_conditions'] = 'historical fixture'
        report = self.report()
        self.assertTrue(report['migration_required'])
        self.assertTrue(report['legacy_diagnostic']['complete'])
        self.assertFalse(report['complete'])
        self.assertFalse(self.mapping()['mapping_complete'])

    def test_status_and_verify_same_json_and_exit(self):
        path = self.fx.save()
        self.fx.write('restoration.md', 'old prose with entirely different verdicts')
        for missing in (False, True):
            if missing:
                self.data['observations'].pop()
                self.fx.save()
            outputs = []
            for cmd, target in [('verify', path), ('status', self.fx.base / 'restoration.md'), ('status', self.fx.base)]:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    code = uir.main([cmd, str(target)])
                outputs.append((code, json.loads(stream.getvalue())))
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(outputs[0], outputs[2])

    def test_cli_findings_stable_across_process_hash_order(self):
        self.data['elements'][0]['properties'] = {}
        path = self.fx.save()
        self.fx.write('restoration.md', 'prose does not override current evidence')
        cli = Path(__file__).resolve().parents[1] / 'scripts/uir.py'
        reports = []
        for command, seed in [('verify', '1'), ('status', '97')]:
            env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE='1')
            target = path if command == 'verify' else self.fx.base / 'restoration.md'
            run = subprocess.run([sys.executable, str(cli), command, str(target)],
                                 capture_output=True, text=True, encoding='utf-8', env=env, check=False)
            reports.append((run.returncode, json.loads(run.stdout)))
        self.assertEqual(reports[0], reports[1])

    def test_check_map_cli_does_not_require_capture(self):
        self.data.update(captures=[], observations=[], sweeps=[])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, uir.main(['check-map', str(self.fx.save())]))

    def test_core_semantics_documented_and_nonempty(self):
        doc = (Path(__file__).resolve().parents[1] / 'references/evidence-contract.md').read_text(encoding='utf-8')
        for props in PROPERTIES.values():
            for prop in props:
                self.assertTrue(SEMANTICS[prop])
                for semantic in SEMANTICS[prop]:
                    self.assertIn(semantic, doc)


if __name__ == '__main__':
    unittest.main()
