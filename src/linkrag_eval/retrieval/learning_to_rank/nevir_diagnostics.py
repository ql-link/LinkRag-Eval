"""Bounded, offline development diagnostics for the existing NevIR A/B models."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import lightgbm
import numpy as np

from linkrag_eval.retrieval.learning_to_rank.diagnostic_features import trace_features
from linkrag_eval.retrieval.learning_to_rank.diagnostic_trees import audit_pair
from linkrag_eval.retrieval.learning_to_rank.features import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    build_online_features,
)
from linkrag_eval.retrieval.learning_to_rank.nevir_evaluation import (
    EvaluationContractError,
    load_rankers,
    prepare_inputs,
)
from linkrag_eval.retrieval.learning_to_rank.online import validate_production_bundle

REVIEW_SEEDS = {"reviewer_1": 202609071, "reviewer_2": 202609072}
TREE_ATOL = 1e-10


def _read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def _write_rows(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _relation(left: float, right: float) -> str:
    return "correct" if left > right else "wrong" if left < right else "tie"


def _four_cell(a: str, b: str) -> str:
    if a == "not_evaluable" or b == "not_evaluable":
        return "not_evaluable"
    return ("both_correct" if b == "correct" else "only_a_correct") if a == "correct" else (
        "only_b_correct" if b == "correct" else "neither_strictly_correct")


def _review_bodies(prepared: list[dict], mapping: list[dict], corpus_path: Path) -> dict:
    """Read missing review text separately; never add it to method inputs."""
    wanted = {row[f"{side}_chunk_id"] for row in prepared for side in ("preferred", "other")}
    bodies: dict[str, dict] = {}
    for row in prepared:
        for cid in wanted & row["contents"].keys():
            value = row["contents"][cid]
            if cid in bodies and bodies[cid]["content"] != value:
                raise EvaluationContractError("development snapshots disagree on a target body")
            bodies[cid] = {"content": value, "source": "saved_development_candidate_snapshot"}
    missing = wanted - bodies.keys()
    pid_to_cid = {row["source_passage_id"]: row["chunk_id"] for row in mapping
                  if row["chunk_id"] in missing}
    if pid_to_cid and corpus_path.is_file():
        with corpus_path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row["source_passage_id"] in pid_to_cid:
                    bodies[pid_to_cid[row["source_passage_id"]]] = {
                        "content": row["content"], "source": "prepared_corpus_review_only",
                    }
    return bodies


_REVIEW_JS = r"""
const data = JSON.parse(document.getElementById('review-data').textContent);
let index = 0;
const key = data.storage_key;
const stored = JSON.parse(localStorage.getItem(key) || '{}');
const saved = stored.answers || {};
const $ = id => document.getElementById(id);
$('reviewer').value = stored.reviewer_name || '';
$('reviewer-type').value = stored.reviewer_type || '';
const statuses = ['', '支持所问条件', '明确不满足必要条件', '相关但证据不足', '无法裁定'];
for (const side of ['X','Y']) {
  for (const status of statuses) {
    const option = document.createElement('option');
    option.value = status; option.textContent = status || '请选择';
    $(side+'-app').appendChild(option);
  }
  $(side+'-capture').onclick = () => {
    const selection = window.getSelection();
    if (!selection.rangeCount) return;
    const range = selection.getRangeAt(0), container = $(side+'-text');
    if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) {
      $('notice').textContent='请先在对应段落中选中原文。'; return;
    }
    const prefix = range.cloneRange(); prefix.selectNodeContents(container);
    prefix.setEnd(range.startContainer,range.startOffset);
    const quote=range.toString(),start=Array.from(prefix.toString()).length;
    $(side+'-evidence').value=quote;$(side+'-start').value=start;
    $(side+'-end').value=start+Array.from(quote).length;
  };
}
function evidence(side, row) {
  const quote = $(side+'-evidence').value;
  if (!quote) return [];
  const rawStart = $(side+'-start').value;
  const rawEnd = $(side+'-end').value;
  const start = Number(rawStart), end = Number(rawEnd);
  const chars = Array.from(row.paragraphs.find(p=>p.display_id===side).content || '');
  if (rawStart === '' || rawEnd === '' || !Number.isInteger(start) || !Number.isInteger(end)
      || start < 0 || end < start || end > chars.length || chars.slice(start,end).join('') !== quote) {
    throw new Error(side+' 的证据位置与逐字摘录不一致，请核对。');
  }
  return [{quote,start,end}];
}
function persist() {
  const row = data.cases[index];
  let spans;
  try { spans = Object.fromEntries(['X','Y'].map(side=>[side,evidence(side,row)])); }
  catch (error) { $('notice').textContent=error.message; return false; }
  saved[row.case_id] = {
    case_id: row.case_id, reviewer_name: $('reviewer').value,
    reviewer_type: $('reviewer-type').value || null,
    query_ambiguity: $('ambiguity').value || null,
    pair_preference: $('preference').value || null,
    pair_reason: $('pair-reason').value,
    adjudication_status: $('status').value,
    paragraphs: ['X','Y'].map(side => ({
      display_id: side, applicability: $(side+'-app').value || null,
      evidence_spans: spans[side], reason: $(side+'-reason').value
    }))
  };
  localStorage.setItem(key, JSON.stringify({answers:saved,reviewer_name:$('reviewer').value,
    reviewer_type:$('reviewer-type').value || null}));
  return true;
}
function show() {
  const row = data.cases[index]; const answer = saved[row.case_id] || {};
  $('position').textContent = `${index+1} / ${data.cases.length} · ${row.case_id}`;
  $('query').textContent = row.query;
  $('ambiguity').value = answer.query_ambiguity || '';
  $('preference').value = answer.pair_preference || '';
  $('pair-reason').value = answer.pair_reason || '';
  $('status').value = answer.adjudication_status || '待复核';
  for (const paragraph of row.paragraphs) {
    const side = paragraph.display_id;
    $(side+'-text').textContent = paragraph.content === null ? '[正文不可用，保留此题]' : paragraph.content;
    const a = (answer.paragraphs || []).find(x=>x.display_id===side) || {};
    $(side+'-app').value = a.applicability || '';
    const span = (a.evidence_spans || [])[0] || {};
    $(side+'-evidence').value = span.quote || '';
    $(side+'-start').value = span.start ?? '';
    $(side+'-end').value = span.end ?? '';
    $(side+'-reason').value = a.reason || '';
  }
  $('previous').disabled = index === 0;
  $('next').disabled = index === data.cases.length-1;
}
$('previous').onclick = () => {if(persist()){index--;show();}};
$('next').onclick = () => {if(persist()){index++;show();}};
$('save').onclick = () => {if(persist()){$('notice').textContent='已保存到本浏览器。请下载结果文件交付。';}};
$('download').onclick = () => {
  if(!persist()) return;
  const result = {schema_version:1, packet:data.packet, exported_at:new Date().toISOString(),
    reviewer_name:$('reviewer').value, reviewer_type:$('reviewer-type').value || null,
    scheduled_cases:data.cases.length, answers:data.cases.map(row=>saved[row.case_id]).filter(Boolean)};
  const url = URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download=data.packet+'-answers.json';a.click();
  URL.revokeObjectURL(url);
};
show();
"""


def _review_html(packet: str, cases: list[dict]) -> str:
    identity = hashlib.sha256(json.dumps([packet, cases], ensure_ascii=False).encode()).hexdigest()
    payload = json.dumps({"packet": packet, "storage_key": f"nevir-human-review-{identity}",
                          "cases": cases}, ensure_ascii=False).replace("<", "\\u003c")
    paragraphs = "".join(
        f'<section><h2>段落 {side}</h2><pre id="{side}-text"></pre>'
        f'<button id="{side}-capture">将所选原文记为证据</button>'
        f'<label>适用性<select id="{side}-app"></select></label>'
        f'<label>证据逐字摘录<textarea id="{side}-evidence" placeholder="保留原文；下方填写从 0 开始、末端不含的 Unicode 字符位置"></textarea></label>'
        f'<label>起始位置<input id="{side}-start" type="number" min="0">'
        f'结束位置<input id="{side}-end" type="number" min="0"></label>'
        f'<label>简短理由<textarea id="{side}-reason"></textarea></label></section>'
        for side in ("X", "Y")
    )
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>NevIR 独立盲审</title>
<style>body{{font:16px/1.65 system-ui,sans-serif;background:#f5f6f8;color:#172333;max-width:1050px;margin:30px auto;padding:0 20px}}
section,.intro{{background:white;border:1px solid #dbe1e8;border-radius:10px;padding:20px;margin:16px 0}}
h1{{font-size:26px}}h2{{font-size:19px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:16px/1.7 Georgia,serif}}
label{{display:block;margin:12px 0}}input,select,textarea,button{{font:inherit;box-sizing:border-box}}textarea{{width:100%;min-height:80px}}
select,input{{padding:5px;margin-left:10px}}button{{padding:8px 16px;margin:5px;border:1px solid #8397af;background:white;border-radius:5px;cursor:pointer}}
nav{{position:sticky;bottom:0;background:#f5f6f8;padding:10px 0;border-top:1px solid #dbe1e8}}.note{{color:#52637a;font-size:14px}}</style>
<h1>NevIR 开发材料独立盲审</h1><div class="intro"><p>先分别判断两段能否回答查询，再判断有无清楚的相对优劣。不要强迫一正一负；“未获批”也可能回答“是否获批”。</p>
<p class="note">本页不含模型分数、官方偏好或其他审阅者意见。每名审阅者只使用分配给自己的材料，独立填写。文本选中后可复制原文摘录。记录仅保存在本浏览器，最终请下载 JSON。</p>
<label>审阅者姓名<input id="reviewer"></label><label>审阅者类型<select id="reviewer-type"><option value="">请选择</option><option value="human">人类审阅者</option><option value="ai_provisional">AI 暂定分析</option></select></label></div>
<p id="position"></p><section><h2>查询</h2><pre id="query"></pre><label>影响判断的查询歧义<select id="ambiguity"><option value="">请选择</option><option value="no">无</option><option value="yes">有</option><option value="uncertain">无法判断</option></select></label></section>
{paragraphs}<section><h2>单段判断完成后的成对结论</h2><label>相对偏好<select id="preference"><option value="">请选择</option><option value="X">X 更适合</option><option value="Y">Y 更适合</option><option value="tie">无严格优劣</option><option value="undetermined">无法裁定</option></select></label>
<label>理由<textarea id="pair-reason"></textarea></label><label>复核状态<select id="status"><option>待复核</option><option>独立复核</option><option>争议保留</option></select></label></section>
<nav><button id="previous">上一题</button><button id="next">下一题</button><button id="save">保存当前</button><button id="download">下载结果</button><span id="notice" class="note"></span></nav>
<script type="application/json" id="review-data">{payload}</script><script>{_REVIEW_JS}</script></html>'''


def make_review_packets(prepared: list[dict], bodies: dict, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    private = out / "private"
    private.mkdir(exist_ok=True)
    maps, counts = {}, {}
    for name, seed in REVIEW_SEEDS.items():
        rng = random.Random(seed)
        ordered = list(prepared)
        rng.shuffle(ordered)
        public, mapping, forms = [], [], []
        for index, row in enumerate(ordered, 1):
            case_id = f"{name[-1]}-{index:03d}-{rng.getrandbits(32):08x}"
            cids = [row["preferred_chunk_id"], row["other_chunk_id"]]
            rng.shuffle(cids)
            paragraphs = [{"display_id": side, "content": bodies.get(cid, {}).get("content")}
                          for side, cid in zip(("X", "Y"), cids, strict=True)]
            public.append({"case_id": case_id, "query": row["query"], "paragraphs": paragraphs})
            mapping.append({
                "case_id": case_id, "source_query_id": row["source_query_id"],
                "source_group_id": row["source_group_id"], "pair_id": row["pair_id"],
                "display_mapping": dict(zip(("X", "Y"), cids, strict=True)),
                "official_preferred_chunk_id": row["preferred_chunk_id"],
                "body_sources": {cid: bodies.get(cid, {}).get("source", "unavailable") for cid in cids},
                "present_in_query_pool": {cid: cid in row["contents"] for cid in cids},
            })
            forms.append({
                "case_id": case_id, "reviewer_name": None, "reviewer_type": None,
                "query_ambiguity": None, "pair_preference": None, "pair_reason": "",
                "adjudication_status": "待复核",
                "paragraphs": [{"display_id": side, "applicability": None,
                                "evidence_spans": [], "reason": ""} for side in ("X", "Y")],
            })
        folder = out / name
        folder.mkdir(exist_ok=True)
        _write_rows(folder / "cases.jsonl", public)
        _write_rows(folder / "blank-answers.jsonl", forms)
        (folder / "review.html").write_text(_review_html(name, public), encoding="utf-8")
        _write_rows(private / f"{name}-mapping.jsonl", mapping)
        maps[name] = {row["source_query_id"]: row["case_id"] for row in mapping}
        counts[name] = len(public)
    (out / "README.md").write_text(
        "# 独立盲审材料\n\n分别将 `reviewer_1/` 和 `reviewer_2/` 交给两名人类审阅者；各自打开 `review.html`。"
        "不要把 `private/`、诊断报告或模型结果交给审阅者。两人提交后再作分歧裁定，裁定层与官方标签分别保存。"
        "表单未填写不算完成人工复核；AI 输出只能标为 `ai_provisional`。\n\n"
        f"范围为全部 {len(prepared)} 条开发查询的指定两段，缺目标的题保留。复核材料取得的正文不补入模型输入。"
        "显示顺序独立打乱，匿名映射仅在 private 中；自然文本的重复不可消除，未声称既往曝光被抹除。\n",
        encoding="utf-8",
    )
    return {"status": "materials_ready_human_review_pending", "packet_counts": counts,
            "human_reviews_received": 0, "ai_reviews_generated": 0,
            "missing_target_bodies": sorted({row[f"{side}_chunk_id"] for row in prepared
                                              for side in ("preferred", "other")} - bodies.keys()),
            "case_maps": maps}


def _summarize_cases(cases: list[dict], model_names: tuple[str, str] = ("A", "B")) -> dict:
    covered = [row for row in cases if row["coverage_state"] == "both"]
    by_pair: dict[str, list[dict]] = {}
    for row in cases:
        by_pair.setdefault(row["pair_id"], []).append(row)
    pairs = [rows for rows in by_pair.values() if len(rows) == 2
             and all(row["coverage_state"] == "both" for row in rows)]
    return {
        "scheduled_queries": len(cases), "scheduled_pairs": len(by_pair),
        "source_groups": len({row["source_group_id"] for row in cases}),
        "covered_queries": len(covered), "covered_pairs": len(pairs),
        "coverage_counts": dict(Counter(row["coverage_state"] for row in cases)),
        "official_four_cells": dict(Counter(row["official_four_cell"] for row in covered)),
        "models": {name: {
            "strict_relations": dict(Counter(row["models"][name]["relation"] for row in covered)),
            "paired_correct": sum(all(row["models"][name]["relation"] == "correct" for row in pair)
                                  for pair in pairs),
            "identical_leaf_vectors": sum(row["models"][name]["different_leaf_count"] == 0
                                          for row in covered),
        } for name in model_names},
        "full_feature_collisions": sum(row["full_features_exactly_equal"] for row in covered),
        "semantic_attribution": "unknown_pending_human_review",
        "human_reviews_received": 0,
        "mechanism_categories": {"unknown_or_mixed_pending_review": {
            "queries": len(cases), "pairs": len(by_pair),
            "source_groups": len({row["source_group_id"] for row in cases}),
        }},
        "source_group_distribution": {group: dict(Counter(row["official_four_cell"] for row in covered
                                                         if row["source_group_id"] == group))
                                      for group in sorted({row["source_group_id"] for row in cases})},
        "route_preferences": {source: dict(Counter(row["route_preferences"][source]["relation"]
                                                   for row in cases))
                              for source in ("dense", "sparse", "bm25")},
        "frozen_weighted_relations": dict(Counter(row["frozen_weighted_relation"] for row in cases)),
    }


def _reports(out: Path, cases: list[dict], summary: dict, replay: dict) -> None:
    a, b = summary["models"]["A"], summary["models"]["B"]
    lines = [
        "# NevIR 开发材料离线诊断", "",
        "**机械诊断完成；可靠语义归因待人工复核。本轮决策：暂不改动。**", "",
        (f"全部 {summary['scheduled_queries']} 查询／{summary['scheduled_pairs']} 配对／"
        f"{summary['source_groups']} 来源组保留；{summary['covered_queries']} 查询及 "
        f"{summary['covered_pairs']} 配对共同覆盖。缺目标不补入模型输入。"), "",
        "| 原始分数官方口径 | A | B |", "| --- | ---: | ---: |",
        *[f"| {label} | {a['strict_relations'].get(key, 0)} | {b['strict_relations'].get(key, 0)} |"
          for key, label in (("correct", "严格符合"), ("wrong", "严格逆序"), ("tie", "同分"))],
        f"| 双方向均严格符合 | {a['paired_correct']} | {b['paired_correct']} |", "",
        ("A 为本轮在开发池重新计算，没有声称历史 A 开发分数逐值一致；B 与已保存全部开发候选分数核对。"
        "不读取本轮禁止的确认逐题或 Test，不把当前开发结果当成新独立确认。"), "",
        (f"四格：`{json.dumps(summary['official_four_cells'], ensure_ascii=False)}`。"
        "未严格符合包括逆序与同分；来源分布见 summary.json。"), "",
        (f"完整 38 维精确碰撞 {summary['full_feature_collisions']} 查询。"
        f"所有树均同叶的查询 A={a['identical_leaf_vectors']}、B={b['identical_leaf_vectors']}。"
        "碰撞只能解释同分，不能解释严格逆序；没有碰撞也不证明表示充分。"), "",
        ("trace 开／关的完整池特征及 A/B 分数精确一致。逐树核验以 1e-10 绝对容差、rtol=0 "
        "重建原始分数和分差；严格偏好始终直接比较原始浮点分数，不用工程容差改判同分。"
        f"最大分差重建误差 {replay['tree_max_abs_delta_error']:.17g}。"), "",
        ("人工复核尚未提供；此前 AI 审视／曝光标记原样保留，不变成人工金标。"
        "全部病例的语义类别为 unknown_pending_human_review，不能将同覆盖率、规则未命中或树路径直接写成必要条件被遗漏。"), "",
        ("训练支持查询与控制探针均未触发：尚无人工确认的具体语义假设；没有为了完成流程选择文本编辑或删池。"
        "池依赖来自实际原函数的输入列表，不能将列表删项后重编号当作保留原排名的探针。"), "",
        "## 逐例索引", "",
        ("下表按全部开发查询列出，包含原正确、纠正、改坏、双方未对及覆盖限制。"
        "每行 source_query_id 是 cases.jsonl／feature-traces.jsonl／tree-audit.jsonl 的关联键。"), "",
        "| 查询 | 来源组 | 覆盖 | A | B | 四格 |", "| --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(f"| {row['source_query_id']} | {row['source_group_id']} | {row['coverage_state']} | "
                 f"{row['models']['A']['relation']} | {row['models']['B']['relation']} | "
                 f"{row['official_four_cell']} |" for row in cases)
    lines += ["", ("文件：manifest.json、replay-check.json、summary.json、cases.jsonl、"
              "raw-predictions.jsonl、model-inputs.npz、feature-traces.jsonl、tree-audit.jsonl。"
              "原文引用位于 feature traces 的开发快照来源；人工材料在 review/，隐藏映射在 review/private/。"), ""]
    (out / "diagnosis.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "decision.md").write_text(
        "# 本轮决策：暂不改动\n\n"
        "完整开发输入、特征追踪及逐树机械核验已完成，官方偏好下的状态变化可以追溯到当前特征和叶输出。"
        "但尚无人类独立复核及裁定，因此不能将某个字符匹配、聚合或阈值差异可靠对应到证据适用性；"
        "当前证据不足以选择一个研究改动。\n\n"
        "下一步只接收两份独立盲审并裁定分歧，再将可靠证据位置与已保存追踪关联。"
        "推翻“暂不改动”需要在不同来源的可判案例中，将一项具体处理／聚合／模型利用缺口连接到实际错误，"
        "并检查原正确及不支持该机制的案例，足以提出一项可单独检验的变化。"
        "不以任意固定错误数为门槛，不要求增加模型或调参。\n\n"
        "本轮没有执行该后续工作中的人工裁定、算法改动、训练、效果验证或新确认；"
        "训练支持与探针均为 not_run，理由见各自记录。\n", encoding="utf-8",
    )


def run_diagnostics(*, experiment_dir: Path, model_a: Path, model_b: Path,
                    saved_b_predictions: Path, execution_plan: Path, out: Path) -> dict:
    started = time.monotonic()
    out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[4]
    files = {
        "queries": experiment_dir / "prepared/development/queries.jsonl",
        "supervision": experiment_dir / "prepared/development/supervision.jsonl",
        "inputs": experiment_dir / "candidates/development/inputs.jsonl",
        "passage_mapping": experiment_dir / "prepared/passage-mapping.jsonl",
        "saved_b_predictions": saved_b_predictions,
        "model_a": model_a / "model.txt", "model_b": model_b / "model.txt",
        "execution_plan": execution_plan,
    }
    manifest = {
        "status": "running", "mechanical_status": "running", "human_review_status": "pending",
        "started_utc": datetime.now(UTC).isoformat(), "workspace": str(root),
        "branch": _git(root, "branch", "--show-current"), "head": _git(root, "rev-parse", "HEAD"),
        "uncommitted_paths": _git(root, "status", "--short", "--untracked-files=all").splitlines(),
        "versions": {"python": platform.python_version(), "numpy": np.__version__,
                     "lightgbm": lightgbm.__version__},
        "input_paths": {key: str(path.resolve()) for key, path in files.items()},
        "input_sha256": {}, "feature_version": FEATURE_VERSION, "feature_names": FEATURE_NAMES,
        "feature_dtype": "float32", "prediction_num_threads": 1,
        "raw_tree_range": "all existing trees", "tree_reconstruction_atol": TREE_ATOL,
        "tree_reconstruction_rtol": 0, "strict_ties": "exact raw score equality only",
        "data_role": "development", "review_seeds": REVIEW_SEEDS,
        "boundary": {"remote_calls": 0, "fits": 0, "new_models": 0,
                     "confirmation_instances_read": 0, "test_instances_read": 0,
                     "original_inputs_modified": False, "online_policy_modified": False},
    }
    _write_json(out / "manifest.json", manifest)
    try:
        missing = [str(path) for path in files.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"missing required local input: {missing}")
        manifest["input_sha256"] = {key: _sha256(path) for key, path in files.items()}
        (out / "execution-plan.md").write_text(
            execution_plan.read_text(encoding="utf-8"), encoding="utf-8")
        loaded = {key: _read_rows(files[key]) for key in ("queries", "supervision", "inputs", "passage_mapping")}
        prepared = prepare_inputs(**loaded, role="development")
        if not all(row["rank_input_complete"] for row in prepared):
            invalid = [row["source_query_id"] for row in prepared if not row["rank_input_complete"]]
            raise EvaluationContractError(f"incomplete development inputs: {invalid}")
        saved = _read_rows(saved_b_predictions)
        saved_by_id = {row["source_query_id"]: row for row in saved}
        if len(saved_by_id) != len(saved) or set(saved_by_id) != {row["source_query_id"] for row in prepared}:
            raise EvaluationContractError("saved B development query IDs differ")
        manifest["bundle_validation"] = {name: validate_production_bundle(path)
                                         for name, path in (("A", model_a), ("B", model_b))}
        rankers, errors, contracts = load_rankers(model_a, model_b)
        if errors or any(ranker is None for ranker in rankers.values()):
            raise EvaluationContractError(f"model loading failed: {errors}")
        manifest["model_contracts"] = contracts
        bodies = _review_bodies(prepared, loaded["passage_mapping"], experiment_dir / "prepared/corpus.jsonl")
        review = make_review_packets(prepared, bodies, out / "review")
        manifest["review"] = {key: value for key, value in review.items() if key != "case_maps"}
        cases, prediction_rows, traces, tree_rows, replay_rows, matrices = [], [], [], [], [], {}
        for row in prepared:
            qid = row["source_query_id"]
            for key in ("source_group_id", "pair_id", "direction", "official_label_available",
                        "structural_conflict", "semantic_uncertain", "semantic_review_status", "candidate_count"):
                if row[key] != saved_by_id[qid][key]:
                    raise EvaluationContractError(f"saved B supervision association mismatch: {qid}/{key}")
            ids, features = build_online_features(**row["method_row"], candidate_contents=row["contents"])
            if features.dtype != np.float32 or features.shape != (len(ids), len(FEATURE_NAMES)) or not np.isfinite(features).all():
                raise EvaluationContractError("invalid model input matrix")
            scores = {name: np.asarray(ranker.model.predict(features, num_threads=1, num_iteration=-1))
                      for name, ranker in rankers.items()}
            expected = {entry["chunk_id"]: entry["score"] for entry in saved_by_id[qid]["scores"]}
            if len(expected) != len(saved_by_id[qid]["scores"]) or set(expected) != set(ids):
                raise EvaluationContractError(f"saved B candidate identity mismatch: {qid}")
            if not np.array_equal(scores["B"], np.asarray([expected[cid] for cid in ids])):
                raise EvaluationContractError(f"saved B score replay mismatch: {qid}")
            trace = trace_features(query=row["query"], routes=row["method_row"]["routes"],
                                   candidate_contents=row["contents"],
                                   target_chunk_ids=[row["preferred_chunk_id"], row["other_chunk_id"]],
                                   reference_ids=ids, reference_features=features)
            if not trace["verification"]["passed"]:
                raise EvaluationContractError(f"feature trace mismatch: {qid}")
            trace.update(source_query_id=qid, raw_input_reference={"file": str(files["inputs"].resolve()),
                                                                 "source_query_id": qid})
            after_ids, after_features = build_online_features(**row["method_row"], candidate_contents=row["contents"])
            after_scores = {name: np.asarray(ranker.model.predict(after_features, num_threads=1, num_iteration=-1))
                            for name, ranker in rankers.items()}
            if ids != after_ids or not np.array_equal(features, after_features) or any(
                not np.isfinite(scores[name]).all() or not np.array_equal(scores[name], after_scores[name])
                for name in rankers
            ):
                raise EvaluationContractError(f"trace changed features or scores: {qid}")
            target_indices = {side: ids.index(row[f"{side}_chunk_id"]) if row[f"{side}_chunk_id"] in ids else None
                              for side in ("preferred", "other")}
            target_features = {side: features[index] for side, index in target_indices.items() if index is not None}
            case = {key: row[key] for key in ("source_query_id", "source_group_id", "pair_id", "direction",
                                             "coverage_state", "target_presence", "candidate_count")}
            case.update(official_label_basis="official_nevir_pair_preference", human_label=None,
                        prior_semantic_review_status=row.get("semantic_review_status"),
                        human_review_status="pending", semantic_attribution="unknown_pending_human_review",
                        models={}, route_preferences={},
                        full_features_exactly_equal=(bool(np.array_equal(target_features["preferred"], target_features["other"]))
                                                     if len(target_features) == 2 else None),
                        trace_key=qid, tree_audit_key=qid if len(target_features) == 2 else None)
            audits = {}
            for name, ranker in rankers.items():
                if len(target_features) == 2:
                    preferred_score = float(scores[name][target_indices["preferred"]])
                    other_score = float(scores[name][target_indices["other"]])
                    audits[name] = audit_pair(
                        booster=ranker.model, preferred_features=target_features["preferred"],
                        other_features=target_features["other"], feature_names=FEATURE_NAMES,
                        preferred_score=preferred_score, other_score=other_score, label_basis="official",
                    )
                    if not audits[name]["verification"]["passed"]:
                        raise EvaluationContractError(f"tree reconstruction failed: {qid}/{name}")
                    case["models"][name] = {"relation": _relation(preferred_score, other_score),
                                             "preferred_score": preferred_score, "other_score": other_score,
                                             "raw_delta": preferred_score - other_score,
                                             "different_leaf_count": audits[name]["different_leaf_count"]}
                else:
                    case["models"][name] = {"relation": "not_evaluable", "reason": "missing_target"}
            for source, hits in row["method_row"]["routes"].items():
                values = {hit["chunk_id"]: float(hit["score"]) for hit in hits}
                p, o = row["preferred_chunk_id"], row["other_chunk_id"]
                case["route_preferences"][source] = {
                    "status": row["route_status"][source], "preferred_score": values.get(p),
                    "other_score": values.get(o),
                    "relation": _relation(values[p], values[o]) if p in values and o in values else "missing_target",
                }
            if len(target_features) == 2:
                baseline = {hit["chunk_id"]: hit["score"] for hit in trace["pool_summary"]["baseline_order"]}
                p, o = row["preferred_chunk_id"], row["other_chunk_id"]
                case["frozen_weighted_scores"] = {"preferred": baseline.get(p, 0.0), "other": baseline.get(o, 0.0)}
                case["frozen_weighted_relation"] = _relation(baseline.get(p, 0.0), baseline.get(o, 0.0))
            else:
                case["frozen_weighted_relation"] = "not_evaluable"
            observed_b = case["models"]["B"]
            historical_relation = "unavailable" if observed_b["relation"] == "not_evaluable" else observed_b["relation"]
            if historical_relation != saved_by_id[qid]["preference_relation"] or (
                historical_relation != "unavailable" and observed_b["raw_delta"] != saved_by_id[qid]["score_difference"]
            ):
                raise EvaluationContractError(f"saved B preference replay mismatch: {qid}")
            case["official_four_cell"] = _four_cell(case["models"]["A"]["relation"], case["models"]["B"]["relation"])
            cases.append(case)
            traces.append(trace)
            if audits:
                tree_rows.append({"source_query_id": qid, "label_basis": "official", "models": audits})
            prediction_rows.append({"source_query_id": qid, "chunk_ids": ids,
                                    "scores": {name: values.tolist() for name, values in scores.items()},
                                    "matrix_key": qid, "dtype": str(features.dtype),
                                    "online_result": "not_executed_raw_diagnostic_only"})
            matrices[qid] = features
            replay_rows.append({"source_query_id": qid, "candidate_count": len(ids),
                                "feature_trace_exact": True, "a_score_trace_exact": True,
                                "b_score_trace_exact": True, "saved_b_scores_exact": True,
                                "saved_b_supervision_and_preference_exact": True,
                                "saved_b_max_abs_error": 0.0})
        summary = _summarize_cases(cases)
        summary["b_historical_summary_matches"] = (summary["models"]["B"]["strict_relations"].get("correct") == 47
                                                   and summary["models"]["B"]["paired_correct"] == 11)
        if not summary["b_historical_summary_matches"]:
            raise EvaluationContractError("saved B development summary differs from required 47/74 and 11/37")
        all_features = np.concatenate(list(matrices.values()), axis=0)
        summary["feature_column_statistics"] = {
            name: {"minimum": float(all_features[:, index].min()),
                   "maximum": float(all_features[:, index].max()),
                   "unique_values": len(np.unique(all_features[:, index])),
                   "zero_count": int(np.count_nonzero(all_features[:, index] == 0))}
            for index, name in enumerate(FEATURE_NAMES)
        }
        replay = {"status": "passed", "queries": replay_rows,
                  "candidate_rows": sum(row["candidate_count"] for row in replay_rows),
                  "a_history": "no_saved_a_development_predictions_used; newly_computed",
                  "trace_on_off_features_and_scores": "exactly_equal",
                  "tree_atol": TREE_ATOL, "tree_rtol": 0,
                  "tree_max_abs_delta_error": max((audit["verification"]["max_abs_delta_error"]
                                                    for row in tree_rows for audit in row["models"].values()), default=0.0),
                  "tree_max_abs_score_error": max((audit["verification"]["max_abs_score_error"]
                                                    for row in tree_rows for audit in row["models"].values()), default=0.0)}
        for name, rows in (("cases.jsonl", cases), ("raw-predictions.jsonl", prediction_rows),
                           ("feature-traces.jsonl", traces), ("tree-audit.jsonl", tree_rows)):
            _write_rows(out / name, rows)
        np.savez_compressed(out / "model-inputs.npz", **matrices)
        _write_json(out / "replay-check.json", replay)
        _write_json(out / "summary.json", summary)
        reason = "No human-adjudicated specific semantic hypothesis; mechanical differences alone do not identify semantic cause"
        _write_json(out / "training-support.json", {"status": "not_run", "reason": reason, "train_instances_read": 0})
        _write_json(out / "probe_plan.json", {"status": "not_run", "reason": reason, "probe_count": 0})
        _reports(out, cases, summary, replay)
        unchanged = {key: _sha256(path) == manifest["input_sha256"][key] for key, path in files.items()}
        if not all(unchanged.values()):
            raise EvaluationContractError("input artifact changed during diagnostic execution")
        manifest.update(status="partially_completed", mechanical_status="completed",
                        human_review_status="pending", semantic_attribution="pending_human_review",
                        decision="no_change", input_hashes_unchanged=unchanged,
                        completed_automatable_stages=["P0", "P1_materials", "P2", "P3"],
                        conditional_stages={"P3_training_support": "not_run", "P4": "not_run"},
                        summary=summary)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        manifest.update(status="blocked", mechanical_status="blocked",
                        blocker={"type": type(exc).__name__, "detail": str(exc)})
        raise
    finally:
        manifest.update(finished_utc=datetime.now(UTC).isoformat(), elapsed_seconds=time.monotonic() - started)
        _write_json(out / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--model-a", type=Path, required=True)
    parser.add_argument("--model-b", type=Path, required=True)
    parser.add_argument("--saved-b-predictions", type=Path, required=True)
    parser.add_argument("--execution-plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run_diagnostics(**vars(args))
    print(json.dumps({"status": result["status"], "mechanical_status": result["mechanical_status"],
                      "human_review_status": result["human_review_status"], "out": str(args.out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
