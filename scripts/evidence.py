"""Platform-independent, fail-closed evidence verification (standard library only)."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

PROPERTIES = {
    'container': {'bounds', 'layout', 'spacing', 'background', 'boundary', 'scrolling'},
    'control': {'variant', 'visible-bounds', 'interaction-bounds', 'fill', 'border', 'radius', 'layout', 'states'},
    'icon': {'resource', 'silhouette', 'bounds', 'color', 'stroke', 'whitespace'},
    'image': {'resource', 'silhouette', 'bounds', 'color', 'stroke', 'whitespace'},
    'text': {'content', 'font', 'size', 'weight', 'line-height', 'tracking', 'wrap'},
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def indexed(rows):
    result = {}
    for row in rows:
        key = row['id']
        if not isinstance(key, str) or not key or key in result:
            raise ValueError('missing or duplicate id')
        result[key] = row
    return result


def artifact(base, ref):
    path = (base / ref['path']).resolve()
    if not path.is_file() or digest(path) != ref['sha256']:
        raise ValueError('missing or changed artifact: ' + str(path))
    return path


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)


def mapping_fingerprint(data):
    """Bind machine-only decisions/conditions as well as the Markdown specification."""
    keys = ('version', 'platform', 'states', 'design_languages', 'design_inventory',
            'design_review', 'elements', 'requirements', 'adaptations')
    projection = {key: data.get(key) for key in keys}
    return hashlib.sha256(json.dumps(projection, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode('utf-8')).hexdigest()


def crop_valid(value):
    match = re.fullmatch(r'crop\((\d+),(\d+),(\d+),(\d+)\)', str(value).replace(' ', ''))
    return bool(match and int(match[3]) > 0 and int(match[4]) > 0)


def validate_spec(data, base):
    """The human checklist and machine expectations must describe the same rows."""
    requirements = indexed(data['requirements'])
    if not requirements:
        raise ValueError('empty requirements')
    spec_path = artifact(base, data['specification'])
    spec_rows = {}
    for line in spec_path.read_text(encoding='utf-8').splitlines():
        if re.match(r'^\|\s*R-[\w-]+\s*\|', line):
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if len(cells) < 6 or cells[0] in spec_rows:
                raise ValueError('malformed or duplicate specification row')
            spec_rows[cells[0]] = cells
    spec_ids = set(spec_rows)
    if spec_ids != set(requirements):
        raise ValueError('bundle requirements must cover exactly the specification checklist')
    for rid, req in requirements.items():
        row = spec_rows[rid]
        if [req['state'], req['element'], req['property']] != row[1:4]:
            raise ValueError('requirement identity differs from specification: ' + rid)
        if data['version'] == 3 and req.get('source') != row[5]:
            raise ValueError('requirement source differs from specification: ' + rid)
        if req['comparison']['mode'] == 'number':
            match = re.fullmatch(r'([-+]?\d+(?:\.\d+)?)\s*(\S+)', row[4])
            if not match or float(match[1]) != req['expected'] or match[2] != req['unit']:
                raise ValueError('numeric expectation differs from specification: ' + rid)
        elif str(req['expected']).lower() != row[4].lower():
            raise ValueError('expectation differs from specification: ' + rid)
        if req.get('property', '').split('/')[-1] in ('silhouette', 'appearance') and req.get('comparison', {}).get('mode') != 'visual':
            raise ValueError('silhouette/appearance requires visual comparison: ' + rid)
        if req.get('comparison', {}).get('mode') == 'visual' and not req.get('baseline'):
            raise ValueError('visual requirement lacks baseline: ' + rid)
    return requirements


def diagnose_v2(path):
    """Historical diagnostics only; not the public acceptance entry point."""
    path = Path(path)
    data = json.loads(path.read_text(encoding='utf-8'))
    if data['version'] != 2:
        raise ValueError('expected historical v2 evidence')
    return _verify(data, path)


def verify(path):
    """Return computed v3 acceptance, never accept a legacy or authored verdict."""
    from mapping import check_mapping_data
    path = Path(path)
    data = json.loads(path.read_text(encoding='utf-8'))
    if data['version'] == 2:
        report = dict(version=2, complete=False, migration_required=True,
                      mapping_complete=False, implementation_complete=False, visually_verified=False,
                      reason='v2 is diagnostic only; gather missing v3 mapping/evidence without inventing it')
        try:
            report['legacy_diagnostic'] = _verify(data, path)
        except (KeyError, ValueError, TypeError, OSError) as exc:
            report['legacy_error'] = str(exc)
        return report
    mapping = check_mapping_data(data, path.parent)
    report = _verify(data, path, v3=True)
    report['version'] = 3
    report['mapping_complete'] = mapping['mapping_complete']
    report['mapping_errors'] = mapping['mapping_errors']
    report['implementation_complete'], report['implementation_errors'] = implementation_status(data, path.parent)
    report['visually_verified'] = report['complete'] and mapping['mapping_complete'] and report['implementation_complete']
    report['complete'] = report['visually_verified']
    return report


def implementation_status(data, base):
    try:
        impl = data['implementation']
        if impl['status'] != 'complete' or not impl.get('dependencies'):
            raise ValueError('implementation pending or dependency scope missing')
        expected = {(r['path'], r['sha256']) for r in impl['dependencies']}
        for ref in impl['dependencies']:
            artifact(base, ref)
        for element in data['elements']:
            for ref in element['mapping'].get('style_dependencies', []):
                if (ref['path'], ref['sha256']) not in expected:
                    raise ValueError('implementation omits style dependency: ' + ref['path'])
        return True, []
    except (KeyError, ValueError, TypeError, OSError) as exc:
        return False, [str(exc)]


def validate_v3_capture(data, base, cap):
    """Check declared running-build linkage, not just a current source revision."""
    if cap.get('mapping_sha256') != mapping_fingerprint(data):
        raise ValueError('capture belongs to a different mapping/condition revision')
    if not isinstance(cap.get('data_conditions'), dict):
        raise ValueError('v3 data_conditions must be explicit facts')
    if not numeric(cap['scale']) or cap['scale'] <= 0:
        raise ValueError('capture scale must be positive and finite')
    if cap['kind'] == 'source':
        return
    manifest = json.loads(artifact(base, cap['build']).read_text(encoding='utf-8'))
    if not manifest.get('id') or cap.get('build_id') != manifest['id'] or not manifest.get('method'):
        raise ValueError('missing/mismatched running build identity')
    expected = {(r['path'], r['sha256']) for r in data['implementation']['dependencies']}
    built = {(r['path'], r['sha256']) for r in manifest['dependencies']}
    captured = {(r['path'], r['sha256']) for r in cap['dependencies']}
    if not expected or not expected.issubset(built) or not expected.issubset(captured):
        raise ValueError('stale build or incomplete captured dependency scope')


def _verify(data, path, v3=False):
    base = path.parent
    requirements = validate_spec(data, base)
    captures = indexed(data['captures'])
    observations = indexed(data['observations'])
    states = data['states']
    if not states or len(set(states)) != len(states):
        raise ValueError('empty or duplicate states')
    elements = indexed(data['elements'])
    coverage_errors = []
    for eid, element in elements.items():
        if element.get('parent') and element['parent'] not in elements:
            raise ValueError('unknown element parent')
        ancestors, parent = {eid}, element.get('parent')
        while parent:
            if parent in ancestors:
                raise ValueError('cyclic element hierarchy')
            ancestors.add(parent)
            parent = elements[parent].get('parent')
        if element.get('mapping', {}).get('mode') not in ('reuse', 'adjust', 'adapt', 'new', 'pending'):
            raise ValueError('missing component mapping')
        if not element['mapping'].get('reference') or element['mapping']['mode'] == 'pending':
            coverage_errors.append(eid + ': mapping pending')
        for prop in sorted(PROPERTIES[element['type']]):
            entry = element.get('properties', {}).get(prop, {})
            refs = entry.get('requirements', [])
            if entry.get('na_reason'):
                continue
            if not refs or not set(refs).issubset(requirements):
                coverage_errors.append(eid + '/' + prop + ': uncovered')
            elif any(requirements[r]['element'] != eid for r in refs):
                coverage_errors.append(eid + '/' + prop + ': belongs to another element')
    if any(req['element'] not in elements for req in requirements.values()):
        raise ValueError('unknown requirement element')
    results = []
    known = set(requirements)
    for obs in observations.values():
        if obs['requirement'] not in known or obs['state'] not in states:
            raise ValueError('unknown observation target/state')

    def capture_valid(cap, state):
        if cap['state'] != state:
            raise ValueError('wrong captured state')
        if cap.get('specification_sha256') != data['specification']['sha256']:
            raise ValueError('capture belongs to a different specification')
        if cap['kind'] not in ('source', 'measurement', 'render'):
            raise ValueError('unknown capture kind')
        for key in ('code_version', 'viewport', 'scale', 'theme', 'language', 'data_conditions', 'method'):
            if v3 and key == 'data_conditions' and cap.get(key) == {}:
                continue
            if cap.get(key) in (None, '', [], {}):
                raise ValueError('missing capture context: ' + key)
        # Include dirty files and transitive style/theme dependencies, not HEAD alone.
        if not cap.get('dependencies'):
            raise ValueError('missing code dependency fingerprints')
        for ref in cap['dependencies']:
            artifact(base, ref)
        if v3:
            validate_v3_capture(data, base, cap)
        return artifact(base, cap['artifact'])

    for rid, req in requirements.items():
        if not req.get('element') or not req.get('property') or not req.get('source'):
            raise ValueError('incomplete requirement: ' + rid)
        for state in states if req['state'] == '*' else [req['state']]:
            if state not in states:
                raise ValueError('unknown requirement state')
            verdict, reason = 'unverified', 'no observation'
            actual = None
            matches = [o for o in observations.values() if o['requirement'] == rid and o['state'] == state]
            if len(matches) > 1:
                reason = 'conflicting/duplicate observations; resolve in a new evidence bundle'
            elif matches:
                obs = matches[0]
                try:
                    cap = captures[obs['capture']]
                    captured = capture_valid(cap, state)
                    if v3:
                        conditions = cap.get('data_conditions', {})
                        if not isinstance(conditions, dict) or any(
                            k not in conditions or type(conditions[k]) is not type(v) or conditions[k] != v
                            for k, v in req.get('applies_when', {}).items()
                        ):
                            raise ValueError('required data conditions not observed; control remains unverified')
                    if not obs.get('locator'):
                        raise ValueError('missing concrete locator/crop')
                    mode = req['comparison']['mode']
                    if mode == 'visual':
                        if cap['kind'] != 'render' or not crop_valid(obs.get('design_locator')) or not crop_valid(obs['locator']):
                            raise ValueError('visual match requires render and design crop')
                        artifact(base, req['baseline'])
                        review = obs['review']
                        if not review.get('reviewer') or not review.get('details'):
                            raise ValueError('missing explicit visual review')
                        if review['details'].strip().lower() in ('looks good', 'match', 'matches', 'implemented', 'same', '通过', '一致'):
                            raise ValueError('generic visual evidence; describe the compared properties')
                        if type(review['match']) is not bool:
                            raise ValueError('visual match must be boolean')
                        actual = review['details']
                        passed = review['match']
                    else:
                        if req['property'].split('/')[0] not in ('token', 'component', 'copy', 'asset') and cap['kind'] == 'source':
                            raise ValueError('source cannot establish rendered value')
                        # Actual comes from a hashed measurement artifact, never the expected column.
                        measurement = json.loads(captured.read_text(encoding='utf-8'))[obs['locator']]
                        if v3 and (measurement.get('element') != req['element'] or
                                   measurement.get('property') != req['property'] or not measurement.get('surface')):
                            raise ValueError('measurement element/property/surface does not match requirement')
                        actual = measurement['value']
                        if measurement['unit'] != req['unit']:
                            raise ValueError('unit mismatch')
                        expected = req['expected']
                        if mode == 'number':
                            tolerance = req['comparison']['tolerance']
                            if not all(numeric(v) for v in (actual, expected, tolerance)) or tolerance < 0:
                                raise ValueError('invalid numeric comparison')
                            passed = abs(actual - expected) <= tolerance
                        elif mode == 'equals':
                            passed = type(actual) is type(expected) and actual == expected
                        elif mode == 'content':
                            # Compare dynamic text against a stated constraint, never sample copy.
                            minimum = req['comparison']['min_length']
                            if type(minimum) is not int or minimum < 0:
                                raise ValueError('invalid content constraint')
                            passed = isinstance(actual, str) and len(actual.strip()) >= minimum
                        else:
                            raise ValueError('unknown comparison mode')
                    verdict = 'restored' if passed else 'unrestored'
                    reason = 'matches' if passed else 'observed difference'
                    if v3 and obs.get('adaptation'):
                        a = indexed(data.get('adaptations', []))[obs['adaptation']]
                        if a['requirement'] != rid or obs['state'] not in a['states']:
                            raise ValueError('adaptation belongs to a different requirement/state')
                        # An approved replacement is observed, not a blanket waiver.
                        replacement = a['replacement']
                        if mode == 'visual':
                            artifact(base, replacement['baseline'])
                            if obs.get('adaptation_design_locator') != replacement['locator']:
                                raise ValueError('adaptation requires comparison against approved baseline region')
                            review = obs['adaptation_review']
                            if not review.get('reviewer') or len(review.get('details', '').strip()) < 20 or type(review.get('match')) is not bool:
                                raise ValueError('missing adaptation visual comparison')
                            accepted = review['match']
                        elif mode == 'number':
                            accepted = abs(actual - replacement['expected']) <= replacement['tolerance']
                        elif mode == 'equals':
                            accepted = type(actual) is type(replacement['expected']) and actual == replacement['expected']
                        else:
                            raise ValueError('content constraints must not be waived by adaptation')
                        verdict = 'adapted' if accepted else 'unrestored'
                        reason = a['reason'] if accepted else 'approved adaptation also differs'
                    elif obs.get('adaptation'):
                        a = obs['adaptation']
                        if not all(a.get(k) for k in ('reason', 'authority', 'remaining_requirements')):
                            raise ValueError('incomplete adaptation')
                        if not set(a['remaining_requirements']).issubset(known):
                            raise ValueError('unknown remaining adaptation requirements')
                        verdict, reason = 'adapted', a['reason']
                except (KeyError, ValueError, TypeError, OSError) as exc:
                    verdict, reason = 'unverified', str(exc)
            results.append(dict(id=rid, state=state, verdict=verdict, actual=actual, reason=reason))

    sweep_errors = []
    for state in states:
        sweeps = [s for s in data.get('sweeps', []) if s.get('state') == state]
        if len(sweeps) != 1:
            sweep_errors.append(state + ': missing/duplicate sweep')
            continue
        sweep = sweeps[0]
        try:
            cap = captures[sweep['capture']]
            capture_valid(cap, state)
            if cap['kind'] != 'render':
                raise ValueError('sweep needs render')
            artifact(base, sweep['baseline'])
            if not sweep.get('reviewer') or not sweep.get('regions'):
                raise ValueError('sweep needs reviewer and full-page plus control regions')
            if 'page' not in sweep['regions'] or 'controls' not in sweep['regions']:
                raise ValueError('sweep must cover page and controls')
            for finding in sweep['findings']:
                refs = finding.get('requirements', [])
                if not finding.get('description') or not refs or not set(refs).issubset(known):
                    raise ValueError('unmapped sweep difference')
                for result in results:
                    if result['id'] in refs and result['state'] == state and result['verdict'] in ('restored', 'adapted'):
                        result.update(verdict='unrestored', reason='sweep contradicts pass: ' + finding['description'])
        except (KeyError, ValueError, TypeError, OSError) as exc:
            sweep_errors.append(state + ': ' + str(exc))
    if v3:
        for a in data.get('adaptations', []):
            remaining = a.get('remaining_requirements', [])
            if any(r['id'] in remaining and r['verdict'] != 'restored' for r in results):
                for result in results:
                    if result['id'] == a.get('requirement') and result['state'] in a.get('states', []) and result['verdict'] == 'adapted':
                        result.update(verdict='unverified', reason='adaptation preserved requirements not verified')
    counts = {v: sum(r['verdict'] == v for r in results) for v in ('restored', 'unrestored', 'unverified', 'adapted')}
    # Imported resources need provenance, integration, actual loading and visual
    # review. A successful download or component-name match is insufficient.
    from resources import audit
    resource_errors = []
    for eid, element in elements.items():
        records = element.get('resource_records', [])
        if element['type'] in ('icon', 'image') and element['mapping']['mode'] == 'new' and not records:
            resource_errors.append(eid + ': newly imported resource has no record')
        for ref in records:
            try:
                resource = audit(artifact(base, ref))
                if resource['errors']:
                    resource_errors.extend(eid + ': ' + error for error in resource['errors'])
                for key, visual in (('visual_requirements', True), ('load_requirements', False)):
                    for rid in resource['record'].get(key, []):
                        req = requirements.get(rid)
                        if not req or req['element'] != eid:
                            raise ValueError('resource requirement belongs to a missing/different element')
                        if visual and req['comparison']['mode'] != 'visual':
                            raise ValueError('resource silhouette requires rendered comparison')
                        if not visual and (req['property'] != 'visibility/resource-loaded' or req['expected'] is not True):
                            raise ValueError('resource loading requires an explicit true observation')
                        if any(r['verdict'] != 'restored' for r in results if r['id'] == rid):
                            raise ValueError('resource verification incomplete: ' + rid)
            except (KeyError, ValueError, OSError, TypeError) as exc:
                resource_errors.append(eid + ': ' + str(exc))
    return dict(version=2, counts=counts, results=results, sweep_errors=sweep_errors,
                coverage_errors=coverage_errors, resource_errors=resource_errors,
                complete=not (counts['unrestored'] or counts['unverified'] or sweep_errors or coverage_errors or resource_errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    try:
        report = verify(args.bundle)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({'complete': False, 'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
