"""Structured form contract, recovery and receipt checks with synthetic answers only."""
from __future__ import annotations

import copy
import itertools
import json
import subprocess
import zipfile

import pytest

from linkrag_eval.retrieval.learning_to_rank.review_handoff import (
    disagreement_material,
    read_rows,
    receive_submission,
    validate_submission,
)
from linkrag_eval.retrieval.learning_to_rank.review_persistence import durable_html
from linkrag_eval.retrieval.learning_to_rank.review_schema import (
    CONTRACT,
    PAIR_REASON_CODES,
    REASON_LOGIC_JS,
    REASON_TYPES,
    VALIDATION_POLICY_VERSION,
    structured_errors,
    structured_missing,
)
from linkrag_eval.retrieval.learning_to_rank.review_structured import (
    FILES,
    structured_html,
    upgrade_structured,
)
from linkrag_eval.retrieval.learning_to_rank.review_tutorial import PRACTICES, tutorial_html

from .review_page_qa import describe, run
from .test_review_handoff import packets  # noqa: F401 -- shared synthetic fixture

CASES = [{'case_id':'qa-1','query':'QA only?', 'paragraphs':[{'display_id':s,'content':'A😀 Bob did not submit it.'} for s in ('X','Y')]},
         {'case_id':'qa-2','query':'QA only two?', 'paragraphs':[{'display_id':s,'content':'No other evidence.'} for s in ('X','Y')]}]


def inp(id_,value):
    return {'kind':'input','id':id_,'value':value}


def check(id_,value=True):
    return {'kind':'check','id':id_,'checked':value}


def click(id_):
    return {'kind':'click','id':id_}


def answer_actions(case, mode=0, prefix=''):
    """Exercise actual UI conditions; these choices make no claim about supplied case text."""
    paircodes=list(PAIR_REASON_CODES)
    patterns=[('支持所问条件','相关但证据不足'),('支持所问条件','明确不满足必要条件'),
              ('支持所问条件','支持所问条件'),('相关但证据不足','相关但证据不足'),
              ('明确不满足必要条件','明确不满足必要条件'),('支持所问条件','支持所问条件'),
              ('无法裁定','无法裁定'),('相关但证据不足','相关但证据不足')]
    mode%=8
    preference='X' if mode in (0,1,5) else 'undetermined' if mode in (6,7) else 'tie'
    actions=[inp(prefix+'ambiguity','yes' if mode==6 else 'no'),inp(prefix+'preference',preference),
             inp(prefix+'pair-reason-code',paircodes[mode]),inp(prefix+'pair-reason','QA ONLY uncertainty' if mode>=5 else ''),
             inp(prefix+'status','争议保留' if mode==6 else '独立复核')]
    for side,app in zip(('X','Y'),patterns[mode],strict=True):
        kinds=['entity','action_relation','polarity'] if app in ('支持所问条件','明确不满足必要条件') else ['missing_information','time_quantity_comparison']
        if mode==6:
            kinds=['entity','ambiguity_conflict']
        if mode==7:
            kinds=['other_unclear','missing_information']
        actions += [inp(prefix+side+'-app',app),inp(prefix+side+'-reason','QA ONLY specific missing/ambiguity' if mode>=6 else '')]
        actions += [check(prefix+side+'-basis-'+k,k in kinds) for k in REASON_TYPES]
        if app in ('支持所问条件','明确不满足必要条件'):
            text=next(p['content'] for p in case['paragraphs'] if p['display_id']==side)
            actions += [{'kind':'capture','side':prefix+side,'start':0,'end':len(text)}]
        else:
            actions += [inp(prefix+side+'-evidence',''),inp(prefix+side+'-start',''),inp(prefix+side+'-end','')]
    return actions


def exported(page, actions, **kwargs):
    result=run(page,actions=[*actions,click('download')],**kwargs)
    return result,result['downloads'][-1]['value']


def test_normal_clear_cases_allow_empty_notes_and_roundtrip_all_fields():
    page=structured_html('reviewer_1',CASES)
    actions=[inp('reviewer','QA ONLY'),inp('reviewer-type','human'),*answer_actions(CASES[0]),click('next'),*answer_actions(CASES[1],3)]
    first,payload=exported(page,actions)
    assert payload['schema_version']==2 and payload['completion']['complete_cases']==2
    assert validate_submission(payload,CASES,'reviewer_1',expected_schema_version=2)['complete']
    refreshed=run(page,storage=first['storage'],actions=[click('backup')])
    backup=refreshed['downloads'][-1]['value']
    restored,again=exported(page,[{'kind':'import','value':backup}])
    assert again['answers']==payload['answers']
    assert restored['nodes']['Y-basis-missing_information']['checked']
    assert payload['answers'][0]['pair_reason']==''
    assert payload['answers'][0]['paragraphs'][0]['evidence_spans'][0]['quote']=='A😀 Bob did not submit it.'
    assert payload['answers'][0]['paragraphs'][0]['evidence_spans'][0]['end']==len('A😀 Bob did not submit it.')


@pytest.mark.parametrize('mode',range(8))
def test_every_pair_reason_and_paragraph_branch_receives_without_inferred_preference(mode):
    page=structured_html('reviewer_1',CASES[:1])
    _,payload=exported(page,[inp('reviewer','QA ONLY'),inp('reviewer-type','human'),*answer_actions(CASES[0],mode)])
    assert validate_submission(payload,CASES[:1],'reviewer_1')['complete']
    original=payload['answers'][0]['pair_preference']
    result=run(page,actions=[{'kind':'import','value':payload},inp('pair-reason-code','both_fail')])
    assert result['nodes']['preference']['value']==original


def test_missing_rules_are_identical_in_python_form_and_tutorial_js():
    rows=[]
    for app,kind,has_evidence,note,code,pref,ambiguity in itertools.product(
            ['支持所问条件','明确不满足必要条件','相关但证据不足','无法裁定'],
            [[],['entity'],['missing_information'],['other_unclear']], [False,True],['','specific'],
            PAIR_REASON_CODES,['X','tie','undetermined'],['no','yes','uncertain',None]):
        rows.append({'answer_schema_version':2,'query_ambiguity':ambiguity,'pair_preference':pref,'pair_reason_code':code,'pair_reason':note,
                     'paragraphs':[{'display_id':s,'applicability':app,'reason_types':kind,'reason':note,'evidence_spans':[{'quote':'x','start':0,'end':1}] if has_evidence else []} for s in ('X','Y')]})
    code='const reasonContract='+json.dumps(CONTRACT)+';'+REASON_LOGIC_JS+';process.stdout.write(JSON.stringify(JSON.parse(require("fs").readFileSync(0,"utf8")).map(structuredMissing)));'
    result=subprocess.run(['node','-e',code],input=json.dumps(rows),capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)==[structured_missing(a) for a in rows]
    assert REASON_LOGIC_JS in structured_html('reviewer_1',CASES) and REASON_LOGIC_JS in tutorial_html()
    a=rows[0]
    assert 'X.reason_types' in structured_missing(a) and 'X.evidence' in structured_missing(a)


def ambiguity_export():
    page=structured_html('reviewer_1',CASES[:1])
    actions=[inp('reviewer','QA ONLY'),inp('reviewer-type','human'),*answer_actions(CASES[0],6)]
    actions += [check(side+'-basis-'+kind,False) for side in ('X','Y') for kind in REASON_TYPES]
    _,payload=exported(page,actions)
    # Mutations below target answers; omit redundant raw drafts so imports use those answers.
    payload.pop('drafts')
    return page,payload


@pytest.mark.parametrize('ambiguity',['yes','uncertain'])
def test_ambiguity_abstention_accepts_old_export_without_filling_categories(ambiguity):
    page,payload=ambiguity_export()
    payload.pop('validation_policy_version')
    payload['completion']['complete_cases']=0  # Historical page used stricter completeness rules.
    payload['answers'][0]['query_ambiguity']=ambiguity
    for claimed in (None,'untrusted_future_policy'):
        old=copy.deepcopy(payload)
        if claimed is not None:
            old['validation_policy_version']=claimed
        result=validate_submission(old,CASES[:1],'reviewer_1',expected_schema_version=2)
        assert result['complete'] and not result['errors']
        assert result['validation_policy_version']==VALIDATION_POLICY_VERSION
        _,again=exported(page,[{'kind':'import','value':old}])
        assert again['answers']==old['answers']
        assert again['completion']['complete_cases']==1
        assert all(p['reason_types']==[] and p['evidence_spans']==[] for p in again['answers'][0]['paragraphs'])


@pytest.mark.parametrize('mutation,missing',[
    ('not_ambiguous','X.reason_types'),('no_ambiguity_answer','query_ambiguity'),
    ('blank_note','X.specific_uncertainty'),('missing_pair_note','pair_specific_note'),
    ('missing_pair_code','pair_reason_code'),('other_paragraph','Y.reason_types'),
    ('supports','X.evidence'),('fails','X.evidence'),
])
def test_ambiguity_exception_does_not_remove_other_requirements(mutation,missing):
    page,payload=ambiguity_export()
    a=payload['answers'][0]
    p=a['paragraphs'][0]
    if mutation=='not_ambiguous': a['query_ambiguity']='no'
    elif mutation=='no_ambiguity_answer': a['query_ambiguity']=None
    elif mutation=='blank_note': p['reason']=' \t '
    elif mutation=='missing_pair_note': a['pair_reason']=''
    elif mutation=='missing_pair_code': a['pair_reason_code']=None
    elif mutation=='other_paragraph': a['paragraphs'][1]['applicability']='相关但证据不足'
    else: p['applicability']='支持所问条件' if mutation=='supports' else '明确不满足必要条件'
    result=validate_submission(payload,CASES[:1],'reviewer_1')
    assert not result['complete'] and not result['errors']
    assert missing in result['normalized'][0]['missing']
    _,again=exported(page,[{'kind':'import','value':payload}])
    assert again['completion']['complete_cases']==0


@pytest.mark.parametrize('mutation',['missing_types','null_types','unknown_types','duplicate_types','unicode'])
def test_ambiguity_abstention_still_rejects_invalid_fields(mutation):
    page,payload=ambiguity_export()
    p=payload['answers'][0]['paragraphs'][0]
    if mutation=='missing_types': p.pop('reason_types')
    elif mutation=='null_types': p['reason_types']=None
    elif mutation=='unknown_types': p['reason_types']=['invented']
    elif mutation=='duplicate_types': p['reason_types']=['entity','entity']
    else: p['evidence_spans']=[{'quote':'😀','start':1,'end':3}]  # Codepoint end must be 2.
    result=validate_submission(payload,CASES[:1],'reviewer_1')
    assert result['errors'] and not result['complete']
    form=run(page,actions=[{'kind':'import','value':payload}])
    assert '导入失败' in form['nodes']['notice']['text']


def test_tutorial_ambiguity_exception_keeps_empty_categories_and_requires_own_note():
    actions=[]
    for i,c in enumerate(PRACTICES):
        actions+=answer_actions(c,[0,2,6][i],prefix=f'p{i+1}-')
    actions += [check('p3-'+side+'-basis-'+kind,False) for side in ('X','Y') for kind in REASON_TYPES]
    page=tutorial_html()
    result=run(page,actions=[*actions,click('reveal')])
    assert not result['nodes']['references']['hidden']
    for side in ('X','Y'):
        assert all(not result['nodes']['p3-'+side+'-basis-'+kind]['checked'] for kind in REASON_TYPES)
    broken=run(page,storage=result['storage'],actions=[inp('p3-Y-reason',' '),click('reveal')])
    assert broken['nodes']['references']['hidden']


@pytest.mark.parametrize('kind',['unknown',['entity','entity'],[{}]])
def test_invalid_reason_types_are_errors(kind):
    p={'answer_schema_version':2,'pair_reason_code':'both_support','paragraphs':[{'display_id':'X','reason_types':kind}]}
    assert structured_errors(p)


def test_legacy_import_retains_text_and_old_key_and_can_backup_before_new_fields_completed():
    oldpage=durable_html('reviewer_1',CASES)
    old,payload=exported(oldpage,[inp('reviewer','QA ONLY'),inp('reviewer-type','human'),inp('X-reason','Original unmodified X/Y prose'),
                                inp('pair-reason','Original comparison'),click('next'),inp('Y-reason','Second raw prose')])
    newpage=structured_html('reviewer_1',CASES)
    current,payload2=exported(newpage,[],storage=old['storage'])
    oldkey=describe(oldpage)['payload']['storage_key']
    assert current['storage'][oldkey]==old['storage'][oldkey]
    assert '旧格式' in current['nodes']['migration-notice']['text']
    assert all(p['reason_types']==[] for a in payload2['answers'] for p in a['paragraphs'])
    assert payload2['answers'][0]['paragraphs'][0]['reason']=='Original unmodified X/Y prose'
    assert payload2['answers'][1]['paragraphs'][1]['reason']=='Second raw prose'
    assert not validate_submission(payload2,CASES,'reviewer_1')['complete']
    restored=run(newpage,actions=[{'kind':'import','value':payload2}])
    assert '导入成功' in restored['nodes']['notice']['text']
    viafile=run(newpage,actions=[{'kind':'import','value':payload},click('backup')])
    again=run(newpage,actions=[{'kind':'import','value':viafile['downloads'][-1]['value']}])
    assert '导入成功' in again['nodes']['notice']['text']


@pytest.mark.parametrize('mutation',['packet','body','version','reason_version','unknown_type','unknown_code','duplicate','unicode'])
def test_incompatible_import_keeps_current_draft_and_backend_refuses(mutation):
    page=structured_html('reviewer_1',CASES[:1])
    _,p=exported(page,[inp('reviewer','QA ONLY'),inp('reviewer-type','human'),*answer_actions(CASES[0])])
    bad=copy.deepcopy(p)
    if mutation=='packet': bad['packet']='reviewer_2'
    elif mutation=='body': bad['storage_key']='other-body'
    elif mutation=='version': bad['schema_version']=9
    elif mutation=='reason_version': bad['reason_schema_version']='unknown'
    elif mutation=='unknown_type': bad['answers'][0]['paragraphs'][0]['reason_types']=['invented']
    elif mutation=='unknown_code': bad['answers'][0]['pair_reason_code']='invented'
    elif mutation=='duplicate': bad['answers'][0]['paragraphs'][0]['reason_types']=['entity','entity']
    else: bad['answers'][0]['paragraphs'][0]['evidence_spans'][0]['end']+=1
    assert validate_submission(bad,CASES[:1],'reviewer_1')['errors']
    result=run(page,actions=[inp('reviewer','Keep me'),{'kind':'import','value':bad}])
    assert '导入失败' in result['nodes']['notice']['text'] and result['nodes']['reviewer']['value']=='Keep me'


@pytest.mark.parametrize('denial',[{'denyWrite':True},{'denyRead':True}])
def test_storage_failure_still_exports_recoverable_structured_backup(denial):
    page=structured_html('reviewer_1',CASES[:1])
    result=run(page,actions=[inp('reviewer','QA ONLY'),inp('reviewer-type','human'),*answer_actions(CASES[0]),click('backup')],**denial)
    backup=result['downloads'][-1]['value']
    restored,payload=exported(page,[{'kind':'import','value':backup}])
    assert payload['completion']['complete_cases']==1
    assert restored['nodes']['X-basis-polarity']['checked']


def test_tutorial_gate_enforces_actual_fields_and_references_only_after_three_complete():
    page=tutorial_html()
    assert run(page)['nodes']['references']['hidden']
    actions=[]
    for i,c in enumerate(PRACTICES):
        actions+=answer_actions(c,[0,2,6][i],prefix=f'p{i+1}-')
    result=run(page,actions=[*actions,click('reveal')])
    assert not result['nodes']['references']['hidden'] and not result['nodes']['reveal']['disabled']
    assert all('已齐全' in result['nodes'][f'p{i}-missing']['text'] for i in (1,2,3))
    restored=run(page,storage=result['storage'],actions=[click('reveal')])
    assert not restored['nodes']['references']['hidden']
    for action in [inp('p1-X-evidence',''),check('p1-Y-basis-time_quantity_comparison',False),inp('p3-X-reason',''),inp('p3-pair-reason',''),check('p2-X-basis-other_unclear'),inp('p2-X-app','invented')]:
        broken=run(page,storage=result['storage'],actions=[action,click('reveal')])
        assert broken['nodes']['references']['hidden'] and broken['nodes']['reveal']['disabled']
    reset=run(page,storage=result['storage'],actions=[click('reset')])
    assert reset['nodes']['references']['hidden'] and not reset['nodes']['p1-X-basis-entity']['checked']
    assert list(result['storage'])==['linkrag-authored-tutorial-structured-v2']


def test_new_zip_blank_and_actual_receiver_mapping(packets,tmp_path):  # noqa: F811 -- pytest fixture
    *_,source=packets
    out=tmp_path/'structured'
    m=upgrade_structured(source/'handoff-manifest.json',out)
    intakes=[]
    for i in (1,2):
        reviewer=f'reviewer_{i}'
        with zipfile.ZipFile(m['packages'][reviewer]['zip_path']) as z:
            assert set(z.namelist())=={f'{reviewer}/{f}' for f in FILES}
            assert z.read(f'{reviewer}/cases.jsonl')==(source/reviewer/'cases.jsonl').read_bytes()
            page=z.read(f'{reviewer}/review.html').decode()
            assert b'PRIVATE-' not in b''.join(z.read(n) for n in z.namelist())
        blank=read_rows(out/reviewer/'blank-answers.jsonl')
        assert all(a['answer_schema_version']==2 and a['pair_reason_code'] is None for a in blank)
        cases=read_rows(out/reviewer/'cases.jsonl')
        actions=[inp('reviewer',f'QA ONLY {i}'),inp('reviewer-type','human')]
        for n,c in enumerate(cases):
            actions+=answer_actions(c,3)
            if i==2:
                actions += [check('X-basis-entity')]
            if n<len(cases)-1: actions+=[click('next')]
        _,payload=exported(page,actions)
        file=tmp_path/f'QA-{i}.json';file.write_text(json.dumps(payload))
        intake=tmp_path/f'QA-intake-{i}'
        receipt=receive_submission(file,out/'handoff-manifest.json',reviewer,intake)
        assert receipt['complete'] and not receipt['errors']
        assert receipt['reason_selection_counts']['pairs']['both_insufficient']==4
        intakes.append(intake)
    aligned=tmp_path/'QA-aligned'
    result=disagreement_material(out/'handoff-manifest.json',*intakes,aligned)
    assert result['aligned_cases']==4 and not result['human_judgments_locked']
    assert all('human_reason_categories_differ' in r['mechanical_flags'] for r in json.loads((aligned/'disagreements.json').read_text()))
    with pytest.raises(ValueError,match='overwrite'):
        upgrade_structured(source/'handoff-manifest.json',out)
