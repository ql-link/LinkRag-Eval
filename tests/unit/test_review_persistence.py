"""Execute distributed JavaScript against explicit browser/storage failure scenarios."""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from linkrag_eval.retrieval.learning_to_rank.review_persistence import DURABLE_JS, durable_html

HARNESS = r"""
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
const nodes={},storage={...(input.storage||{})},downloads=[],events={};let denyWrite=!!input.denyWrite;
function node(id){return nodes[id]||=( {value:'',textContent:'',disabled:false,handlers:{},
  appendChild(){},addEventListener(k,f){this.handlers[k]=f;},click(){},remove(){}});}
node('review-data').textContent=JSON.stringify(input.payload);
const c={document:{getElementById:node,createElement:()=>({click(){},remove(){}}),body:{appendChild(){}}},
 localStorage:{getItem:k=>{if(input.denyRead)throw Error('blocked read');return storage[k]||null;},
 setItem:(k,v)=>{if(denyWrite)throw Error('QuotaExceededError');storage[k]=v;}},
 Blob:class{constructor(p){this.text=p.join('');}},URL:{createObjectURL:b=>{downloads.push(JSON.parse(b.text));return 'blob';},revokeObjectURL(){}},
 setTimeout(){},window:{confirm:()=>input.confirm!==false,addEventListener:(k,f)=>events[k]=f}};
vm.runInNewContext(input.script,c,{timeout:2000});
(async()=>{
 let warned=false;
 for(const a of input.actions||[]){
  if(a.kind==='input'){node(a.id).value=a.value;node(a.id).handlers.input();}
  else if(a.kind==='click')node(a.id).onclick();
  else if(a.kind==='import')await node('import-file').onchange({target:{files:[{text:async()=>JSON.stringify(a.value)}],value:'file'}});
  else if(a.kind==='unload')events.beforeunload({preventDefault(){warned=true;},returnValue:undefined});
  else if(a.kind==='denyWrite')denyWrite=true;
  else if(a.kind==='storage')events.storage({key:input.payload.storage_key,newValue:'other draft'});
 }
 process.stdout.write(JSON.stringify({storage,downloads,warned,values:Object.fromEntries(Object.entries(nodes).map(([k,v])=>[k,v.value])),notice:node('notice').textContent,position:node('position').textContent}));
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});
"""


@pytest.fixture
def payload():
    cases = [{"case_id": f"case-{i}", "query": f"Question {i}",
              "paragraphs": [{"display_id": "X", "content": "A😀B"},
                             {"display_id": "Y", "content": "Other."}]} for i in range(2)]
    html = durable_html("reviewer_1", cases)
    return json.loads(re.search(r'<script[^>]*id="review-data"[^>]*>(.*?)</script>', html, re.DOTALL).group(1))


def run(payload, **kwargs):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for standalone page JS checks")
    result = subprocess.run([node, "-e", HARNESS], input=json.dumps({"script": DURABLE_JS, "payload": payload, **kwargs}),
                            capture_output=True, text=True, check=True, timeout=10)
    return json.loads(result.stdout)


def fill(text="Unfinished reason"):
    return {"kind": "input", "id": "pair-reason", "value": text}


def test_typing_without_save_survives_reload_and_restores_position(payload):
    a = run(payload, actions=[fill(), {"kind": "click", "id": "next"}, fill("Second 😀 draft")])
    b = run(payload, storage=a["storage"])
    assert b["values"]["pair-reason"] == "Second 😀 draft" and b["position"].startswith("2 / 2")
    c = run(payload, storage=b["storage"], actions=[{"kind": "click", "id": "previous"}])
    assert c["values"]["pair-reason"] == "Unfinished reason"


@pytest.mark.parametrize("failure", ["denyRead", "denyWrite"])
def test_blocked_storage_still_exports_results_and_recoverable_backup(payload, failure):
    a = run(payload, **{failure: True}, actions=[fill(), {"kind": "click", "id": "download"},
                                               {"kind": "click", "id": "backup"}])
    assert len(a["downloads"]) == 2
    assert a["downloads"][0]["answers"][0]["pair_reason"] == "Unfinished reason"
    b = run(payload, actions=[{"kind": "import", "value": a["downloads"][1]}])
    assert b["values"]["pair-reason"] == "Unfinished reason"


def test_invalid_evidence_still_saves_raw_draft_and_exports_backup(payload):
    a = run(payload, actions=[{"kind": "input", "id": "X-evidence", "value": "😀"},
                              {"kind": "input", "id": "X-start", "value": "bad"},
                              {"kind": "click", "id": "download"}])
    assert a["downloads"][0]["drafts"]["case-0"]["X-start"] == "bad"
    assert "修正" in a["notice"]
    b = run(payload, storage=a["storage"])
    assert b["values"]["X-evidence"] == "😀" and b["values"]["X-start"] == "bad"


def test_unicode_evidence_export_import_roundtrip(payload):
    a = run(payload, actions=[{"kind": "input", "id": "X-evidence", "value": "😀"},
                              {"kind": "input", "id": "X-start", "value": "1"},
                              {"kind": "input", "id": "X-end", "value": "2"},
                              {"kind": "click", "id": "download"}])
    exported = a["downloads"][0]
    assert exported["answers"][0]["paragraphs"][0]["evidence_spans"] == [{"quote": "😀", "start": 1, "end": 2}]
    b = run(payload, actions=[{"kind": "import", "value": exported}])
    assert b["values"]["X-evidence"] == "😀" and "导入成功" in b["notice"]


def test_unbacked_edits_warn_before_exit(payload):
    assert run(payload, actions=[fill(), {"kind": "unload"}])["warned"]
    assert not run(payload, actions=[fill(), {"kind": "click", "id": "backup"}, {"kind": "unload"}])["warned"]


@pytest.mark.parametrize("change", ["packet", "storage_key", "case_id", "duplicate"])
def test_wrong_import_never_overwrites_current_draft(payload, change):
    exported = run(payload, actions=[fill(), {"kind": "click", "id": "download"}])["downloads"][0]
    if change in {"packet", "storage_key"}:
        exported[change] = "other"
    elif change == "case_id":
        exported["answers"][0]["case_id"] = "unknown"
    else:
        exported["answers"].append(exported["answers"][0])
    a = run(payload, actions=[fill("Keep me"), {"kind": "import", "value": exported}])
    assert a["values"]["pair-reason"] == "Keep me" and "导入失败" in a["notice"]


def test_import_conflict_requires_confirmation_and_preserves_backup(payload):
    imported = run(payload, actions=[fill("Imported"), {"kind": "click", "id": "backup"}])["downloads"][0]
    a = run(payload, confirm=False, actions=[fill("Existing"), {"kind": "import", "value": imported}])
    assert a["values"]["pair-reason"] == "Existing"
    b = run(payload, actions=[fill("Existing"), {"kind": "import", "value": imported}])
    assert b["values"]["pair-reason"] == "Imported"
    assert b["downloads"][0]["drafts"]["case-0"]["pair-reason"] == "Existing"


def test_corrupt_storage_not_silently_overwritten(payload):
    a = run(payload, storage={payload["storage_key"]: "{broken"}, actions=[fill(), {"kind": "click", "id": "backup"}])
    assert a["storage"][payload["storage_key"]] == "{broken"
    assert a["downloads"][0]["unreadable_local_storage"] == "{broken"
    assert a["downloads"][0]["drafts"]["case-0"]["pair-reason"] == "Unfinished reason"


def test_second_window_changes_stop_silent_overwrites(payload):
    first = run(payload, actions=[fill("On disk")])
    a = run(payload, storage=first["storage"], actions=[{"kind": "storage"}, fill("Keep in memory"),
                                                      {"kind": "click", "id": "backup"}])
    assert a["storage"] == first["storage"]
    assert a["downloads"][0]["drafts"]["case-0"]["pair-reason"] == "Keep in memory"


def test_invalid_draft_select_value_rejected_without_erasing_text(payload):
    v = run(payload, actions=[fill(), {"kind": "click", "id": "backup"}])["downloads"][0]
    v["drafts"]["case-0"]["preference"] = "unexpected"
    a = run(payload, actions=[fill("Existing"), {"kind": "import", "value": v}])
    assert a["values"]["pair-reason"] == "Existing" and "导入失败" in a["notice"]


def test_result_export_also_keeps_unfinished_raw_fields(payload):
    a = run(payload, actions=[{"kind": "input", "id": "X-start", "value": "1"},
                              {"kind": "click", "id": "download"}])
    b = run(payload, actions=[{"kind": "import", "value": a["downloads"][0]}])
    assert b["values"]["X-start"] == "1"


def test_storage_failure_still_warns_after_download_request(payload):
    # A download request cannot prove the browser actually wrote the file.
    result = run(payload, denyWrite=True, actions=[fill(), {"kind": "click", "id": "backup"}, {"kind": "unload"}])
    assert result["warned"]


def test_html_controls_capture_astral_unicode_and_reject_nonexistent_option(payload):
    from .review_page_qa import run as run_html
    html = durable_html("reviewer_1", payload["cases"])
    result = run_html(html, actions=[{"kind": "capture", "side": "X", "start": 1, "end": 2},
                                     {"kind": "input", "id": "ambiguity", "value": "not-an-option"},
                                     {"kind": "click", "id": "download"}])
    answer = result["downloads"][0]["value"]["answers"][0]
    assert answer["paragraphs"][0]["evidence_spans"] == [{"start": 1, "end": 2, "quote": "😀"}]
    assert answer["query_ambiguity"] is None
