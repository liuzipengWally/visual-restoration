"""Preimplementation v3 mapping checks. No platform driver or image inference."""
import json
from pathlib import Path

from evidence import PROPERTIES, artifact, crop_valid, indexed, numeric, validate_spec, mapping_fingerprint

# Explicit semantic correspondences, never prefix-only or author-declared aliases.
# New properties may remain standalone requirements. To discharge a core property,
# use its canonical name below (see evidence-contract.md), not an arbitrary alias.
SEMANTICS = {
    'bounds': {'geometry/bounds', 'geometry/width', 'geometry/height', 'geometry/constraints'},
    'visible-bounds': {'geometry/visible-bounds', 'geometry/width', 'geometry/height', 'geometry/constraints'},
    'interaction-bounds': {'interaction/bounds', 'interaction/width', 'interaction/height'},
    'layout': {'geometry/layout', 'geometry/alignment', 'spacing/internal'},
    'spacing': {'spacing/gap', 'spacing/padding', 'spacing/margin'},
    'background': {'color/background'},
    'boundary': {'shape/boundary', 'shape/border', 'shape/border-width', 'color/border'},
    'scrolling': {'interaction/scrolling'},
    'variant': {'component/variant'},
    'fill': {'color/fill'},
    'border': {'shape/border', 'shape/border-width', 'color/border'},
    'radius': {'shape/corner-radius', 'shape/radius', 'shape/contour'},
    'states': {'interaction/states'},
    'resource': {'asset/resource', 'asset/variant'},
    'silhouette': {'shape/silhouette'},
    'color': {'color/foreground', 'color/tint'},
    'stroke': {'shape/stroke', 'shape/stroke-width'},
    'whitespace': {'spacing/whitespace'},
    'content': {'copy/content', 'copy/name', 'copy/label'},
    'font': {'typography/font'},
    'size': {'typography/size'},
    'weight': {'typography/weight'},
    'line-height': {'typography/line-height'},
    'tracking': {'typography/tracking'},
    'wrap': {'typography/wrap', 'typography/truncation'},
}


def source_valid(base, source):
    if source['kind'] == 'node':
        if not source.get('document') or not source.get('locator'):
            raise ValueError('node source needs document and locator')
    elif source['kind'] == 'screenshot':
        artifact(base, source['artifact'])
        if not crop_valid(source.get('locator')):
            raise ValueError('screenshot source needs a concrete crop')
    else:
        raise ValueError('design source must be node or screenshot')


def facts_valid(facts):
    return isinstance(facts, dict) and all(
        isinstance(k, str) and bool(k.strip()) and
        (isinstance(v, (str, bool)) or numeric(v)) for k, v in facts.items())


def code_evidence_valid(base, refs):
    if not refs:
        raise ValueError('no inspected code evidence')
    for ref in refs:
        artifact(base, ref)
        if not ref.get('locator') or not ref.get('detail'):
            raise ValueError('code evidence needs locator and relevant fact')


def check_map(path):
    path = Path(path)
    return check_mapping_data(json.loads(path.read_text(encoding='utf-8')), path.parent)


def check_mapping_data(data, base):
    if data['version'] == 2:
        return dict(version=2, mapping_complete=False, complete=False, migration_required=True,
                    mapping_errors=['v2 needs migration; design/code decisions must be inspected, not auto-filled'])
    if data['version'] != 3:
        raise ValueError('unsupported evidence version')
    requirements = validate_spec(data, base)
    elements = indexed(data['elements'])
    states = data['states']
    if not states or any(not isinstance(s, str) or not s for s in states) or len(set(states)) != len(states):
        raise ValueError('empty/invalid/duplicate states')
    languages = indexed(data.get('design_languages', []))
    inventory = indexed(data.get('design_inventory', []))
    errors = []

    def check(label, action):
        try:
            action()
        except (KeyError, ValueError, TypeError, OSError) as exc:
            errors.append(label + ': ' + str(exc))

    def profile(profile):
        if profile['status'] not in ('known', 'inferred', 'unknown'):
            raise ValueError('invalid design-language confidence')
        if profile['status'] != 'unknown' and not profile.get('name'):
            raise ValueError('known/inferred language needs a name')
        if not profile.get('reason') or not profile.get('evidence'):
            raise ValueError('language finding needs design evidence and reasoning')
        for ev in profile['evidence']:
            source_valid(base, ev['source'])
            if not ev.get('detail'):
                raise ValueError('missing observed design fact')

    for lid, p in languages.items():
        check(lid, lambda p=p: profile(p))
    if not data.get('platform'):
        errors.append('technical platform missing (not a design-language name)')
    review = data.get('design_review', {})
    if not review.get('reviewer') or review.get('inventory_complete') is not True or not review.get('details'):
        errors.append('design inventory needs explicit page/control omission review')
    if not inventory:
        errors.append('design inventory empty')

    def design_item(item):
        source_valid(base, item['source'])
        children = item['children']
        if len(set(children)) != len(children) or not set(children).issubset(inventory):
            raise ValueError('missing/duplicate compound design child')
        if item['disposition'] == 'excluded':
            if not item.get('reason') or not item.get('authority') or item.get('element'):
                raise ValueError('exclusion needs scope authority/reason and no implementation element')
        elif item['disposition'] == 'build':
            eid = item['element']
            if eid not in elements or item['id'] not in elements[eid].get('design_refs', []):
                raise ValueError('design item has no reciprocal element mapping')
            for cid in children:
                child = inventory[cid]
                if child['disposition'] == 'build' and elements.get(child.get('element'), {}).get('parent') != eid:
                    raise ValueError('compound child not independently mapped under its parent: ' + cid)
        else:
            raise ValueError('design disposition must be build or excluded')

    for iid, item in inventory.items():
        check(iid, lambda item=item: design_item(item))
    # Inventory must itself be a tree/forest, not a mutually recursive assertion.
    def visit(iid, ancestors):
        if iid in ancestors:
            raise ValueError('cyclic design inventory')
        for cid in inventory[iid].get('children', []):
            if cid in inventory:
                visit(cid, ancestors | {iid})
    check('inventory', lambda: [visit(i, set()) for i in inventory])
    parents = [c for item in inventory.values() for c in item.get('children', [])]
    if len(parents) != len(set(parents)):
        errors.append('design child has multiple parents')

    def requirement(rid, req):
        if req.get('expected') is None or (isinstance(req['expected'], str) and req['expected'].strip().startswith(('TBD', 'TODO'))):
            raise ValueError('unresolved design expectation')
        if req['element'] not in elements or req['state'] not in ['*'] + states:
            raise ValueError('unknown requirement element/state')
        if req['design_ref'] not in elements[req['element']].get('design_refs', []):
            raise ValueError('requirement lacks same-element design provenance')
        if not facts_valid(req['applies_when']):
            raise ValueError('applies_when must be explicit scalar data facts ({} means unconditional)')
        mode = req['comparison']['mode']
        if mode not in ('number', 'equals', 'visual', 'content'):
            raise ValueError('unknown comparison mode')
        if mode == 'number' and (not numeric(req['expected']) or not numeric(req['comparison'].get('tolerance')) or req['comparison']['tolerance'] < 0):
            raise ValueError('numeric comparison needs finite expectation and tolerance')
        if mode == 'content' and (not req['property'].startswith('copy/') or type(req['comparison'].get('min_length')) is not int or req['comparison']['min_length'] < 0):
            raise ValueError('content mode is a text minimum-length constraint only')
        if not req.get('unit'):
            raise ValueError('missing unit')
        if mode == 'visual':
            artifact(base, req['baseline'])
        if req['property'] in ('shape/contour', 'shape/silhouette', 'shape/appearance') and mode != 'visual':
            raise ValueError('contour/silhouette/appearance requires visual comparison')

    for rid, req in requirements.items():
        check(rid, lambda rid=rid, req=req: requirement(rid, req))

    def element(eid, el):
        applicable_states = el.get('states', states)
        if not applicable_states or not set(applicable_states).issubset(states):
            raise ValueError('invalid element states')
        if el.get('design_language') not in languages:
            raise ValueError('missing region/control design-language finding')
        if not el.get('design_refs') or any(i not in inventory or inventory[i].get('element') != eid for i in el['design_refs']):
            raise ValueError('missing reciprocal design inventory reference')
        ancestor, seen = el.get('parent'), {eid}
        while ancestor:
            if ancestor in seen or ancestor not in elements:
                raise ValueError('unknown/cyclic element parent')
            seen.add(ancestor)
            ancestor = elements[ancestor].get('parent')
        mapping = el['mapping']
        if mapping['mode'] not in ('reuse', 'adjust', 'new') or not mapping.get('reference'):
            raise ValueError('implementation mapping pending or invalid')
        if not mapping.get('system') or not isinstance(mapping.get('parameters'), dict) or not mapping.get('rationale'):
            raise ValueError('mapping needs component system, explicit parameters and rationale')
        code_evidence_valid(base, mapping['code_evidence'])
        if not isinstance(mapping['style_dependencies'], list):
            raise ValueError('style_dependencies must be a list')
        for ref in mapping['style_dependencies']:
            artifact(base, ref)
        chain = mapping['render_chain']
        if not chain or any(not all(step.get(k) for k in ('role', 'reference', 'effect')) for step in chain):
            raise ValueError('trace component configuration, wrappers/theme and final drawing surface')
        for candidate in mapping.get('alternatives', []):
            if not candidate.get('reference') or not candidate.get('reason'):
                raise ValueError('competing candidate lacks exclusion reason')
        for prop in sorted(PROPERTIES[el['type']]):
            entry = el.get('properties', {}).get(prop, {})
            refs = entry.get('requirements', [])
            if entry.get('na_reason'):
                if refs:
                    raise ValueError(prop + ': both N/A and requirements')
                continue
            if not refs:
                raise ValueError(prop + ': uncovered')
            if len(set(refs)) != len(refs):
                raise ValueError(prop + ': duplicate requirements')
            for rid in refs:
                req = requirements.get(rid, {})
                if req.get('element') != eid or req.get('property') not in SEMANTICS[prop]:
                    raise ValueError(prop + ': incompatible requirement ' + rid + ' (' + req.get('property', 'missing') + ')')
            # A property declared applicable cannot be covered in just an arbitrary state.
            covered = {s for r in refs for s in (states if requirements[r]['state'] == '*' else [requirements[r]['state']])}
            if set(applicable_states) - covered:
                raise ValueError(prop + ': missing state coverage; split elements/requirements or record N/A explicitly')
        # Declared independently styled children must have their own presence requirement.
        if el.get('parent') and not any(r['element'] == eid and r['property'] == 'visibility/present' and r['expected'] is True for r in requirements.values()):
            raise ValueError('independent child needs visibility/present requirement')

    for eid, el in elements.items():
        check(eid, lambda eid=eid, el=el: element(eid, el))

    adaptations = indexed(data.get('adaptations', []))
    targets = []
    def adaptation(a):
        rid = a['requirement']
        req = requirements[rid]
        if a['property'] != req['property'] or not a.get('reason') or not a.get('authority'):
            raise ValueError('adaptation must identify the exact requirement/property and approval authority')
        if not a.get('states') or not set(a['states']).issubset(states) or (req['state'] != '*' and a['states'] != [req['state']]):
            raise ValueError('invalid adaptation states')
        keep = a['remaining_requirements']
        if not keep or rid in keep or not set(keep).issubset(requirements):
            raise ValueError('adaptation remaining requirements must exist and cannot include itself')
        replacement = a['replacement']
        mode = req['comparison']['mode']
        if mode == 'visual':
            artifact(base, replacement['baseline'])
            if not crop_valid(replacement.get('locator')):
                raise ValueError('adapted visual requirement needs approved design region')
        elif mode == 'number':
            if not numeric(replacement['expected']) or not numeric(replacement['tolerance']) or replacement['tolerance'] < 0 or replacement['unit'] != req['unit']:
                raise ValueError('invalid adaptation numeric expectation/unit/tolerance')
        elif mode == 'equals':
            if 'expected' not in replacement or replacement['unit'] != req['unit']:
                raise ValueError('invalid adaptation expectation/unit')
        else:
            raise ValueError('content constraints cannot be waived')
        targets.extend((rid, s) for s in a['states'])
    for aid, a in adaptations.items():
        check(aid, lambda a=a: adaptation(a))
    adapted_ids = {a.get('requirement') for a in adaptations.values()}
    if any(adapted_ids.intersection(a.get('remaining_requirements', [])) for a in adaptations.values()):
        errors.append('adaptation cannot rely on another adapted requirement (including cycles)')
    if len(set(targets)) != len(targets):
        errors.append('duplicate adaptation for requirement/state')
    return dict(version=3, mapping_errors=errors, mapping_complete=not errors, complete=not errors,
                mapping_sha256=mapping_fingerprint(data),
                note='declared coverage checked; reviewer owns omitted pixels, candidate suitability and evidence truth')
