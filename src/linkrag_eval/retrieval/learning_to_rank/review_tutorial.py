"""Authored standalone teaching examples; never formal judgments or grading."""
from __future__ import annotations

import html
import json

from .review_schema import CONTRACT, REASON_LOGIC_JS, pair_reason_control, reason_controls

APPLICABILITY = ("支持所问条件", "明确不满足必要条件", "相关但证据不足", "无法裁定")
FIELD_GUIDE = """
<section id="field-guide"><h2>先认识每个字段：填什么、怎么选</h2>
<p>查询就是要回答的问题，X、Y 是两段正文的临时名称，不代表哪段更好。先读清查询要求，再分别判断 X、Y，最后比较。只根据给出的正文，不上网补事实，不请 AI 代答，也不查看另一位审阅者的意见。</p>
<div class="table-scroll"><table><caption>字段填写说明</caption><thead><tr><th scope="col">字段</th><th scope="col">是什么意思、怎样填写</th><th scope="col">何时必填</th></tr></thead><tbody>
<tr><th scope="row">姓名或稳定代号、审阅者类型</th><td>正式页面填写能持续识别你的姓名或代号，续填时保持一致；本人标注选“人类审阅者”。练习页不用填写身份。</td><td>正式标注必填。</td></tr>
<tr><th scope="row">影响判断的查询歧义</th><td>检查问题本身是否有不同理解。“无”：意思清楚；“有”：如“他”没说明是谁，且会影响答案；“无法判断”：拿不准是否有影响。正文没有答案，不等于查询有歧义。</td><td>每题必选；选“有”或“无法判断”，在比较补充中说明疑点。</td></tr>
<tr><th scope="row">适用性</th><td>分别判断这段正文是否提供符合查询要求的证据。四个选项的区别见下方。</td><td>X、Y 各选一项。</td></tr>
<tr><th scope="row">你主要根据哪些内容作出判断？</th><td>勾选实际用到的内容类别，可多选；人物、行为、肯否、时间等类别的解释就在选项旁。类别不表示条件已满足，也不用每题全选。证据不足时，勾选的具体类别表示缺少哪类内容。</td><td>通常每段至少一项。若查询有歧义／无法判断、本段无法裁定，且本段补充已写明疑点，可留空。不要为填满表单强行选。</td></tr>
<tr><th scope="row">证据摘录</th><td>从这一段中选取能支撑判断的原句，保留必要的人物、条件及否定词，不能改写。不要只摘一个脱离上下文的“not”。</td><td>“支持”或“明确不满足”必填；不足或无法裁定可留空，也可摘录有助说明的文字。</td></tr>
<tr><th scope="row">起始、结束（不含）</th><td>它们记录摘录在正文中的位置。用鼠标选中对应正文 → 点击“将所选原文记为证据” → 摘录与两个数字自动填写。不用自己数；“结束”指摘录后面的第一个位置。选错时重新选中并记录。</td><td>有摘录就需要匹配的位置；出现不一致提示时重新选取，不随意改数字。</td></tr>
<tr><th scope="row">段落补充说明</th><td>仅补充选项说不清的内容，一句话即可，如“没有交代周三的时间”或“无法确定 he 指谁”。</td><td>无法裁定、选其他／说不清时必填；不足但没勾具体缺失类型也必填。普通清楚情况可空。</td></tr>
<tr><th scope="row">相对偏好</th><td>读完两段后，选 X 更适合、Y 更适合、无严格优劣或无法裁定。不要因为顺序、篇幅长短或出现否定词就选某段。</td><td>每题必选。两种不选胜者的情况见下方。</td></tr>
<tr><th scope="row">比较依据</th><td>选择最能说明这次比较的一项。前五项描述两段分别能支持、不足或明确不满足的情况；“完整性或直接程度不同”表示都有关但证据质量有区别；歧义时选无法可靠比较，不适用时选其他。它与偏好分别填写，不自动决定胜者。</td><td>每题必选一项。</td></tr>
<tr><th scope="row">比较补充</th><td>说明选项之外的差别或疑点。例如“两段都能回答，但 X 还交代了查询要求的具体时间”。</td><td>查询有歧义或无法判断、偏好无法裁定、比较依据选质量差异／歧义／其他时必填；双方同属支持／不足／不满足却选出胜者，或单段优势依据却选无严格优劣，也需解释。其余可空。</td></tr>
<tr><th scope="row">复核状态</th><td>“待复核”：尚未完成，先存草稿；“独立复核”：已由你独立读完并填写；“争议保留”：已经审阅，但有疑点要留给后续讨论。争议保留也要填齐相关字段，不等于跳过。</td><td>完成的题选独立复核或争议保留；两者都不表示负责人已裁定正确。</td></tr>
</tbody></table></div>
<h3>四类适用性，最容易混在哪里？</h3>
<ul><li><b>支持所问条件：</b>正文给出了符合问题要求的回答证据。问“是否带了笔记本”，明确说“没带”也能回答，不能因为是否定句就判不支持。</li>
<li><b>明确不满足必要条件：</b>问题要求某种条件，正文明确说明所述对象不符合。问“哪间房六点后开放”，正文说“五点关闭”，是明确不满足。</li>
<li><b>相关但证据不足：</b>提到了相关事，但没有交代必要信息。同样问六点后是否开放，正文只说“这间房有座位”，不能猜它的开放时间。</li>
<li><b>无法裁定：</b>歧义、矛盾或理解困难使你无法可靠判断。请说明具体不确定之处。</li></ul>
<p><b>明确不满足 ≠ 没说：</b>前者有反面的明确证据，后者缺信息。<b>无严格优劣 ≠ 无法裁定：</b>前者是你能判断两段没有清楚的优劣；后者是你没有可靠依据作比较。允许两段都支持、都不足或都不满足，不强迫一正一负。</p>
<h3>保存与交回</h3><p>练习只在本页保存，不用提交；清空练习不影响正式标注。正式页每人独立完成全部 76 条，每次离开前下载备份并确认文件已在电脑中。换设备或浏览器时导入 JSON 续填；全部完成后导出标注结果，交回末尾为 <code>-answers.json</code> 的原文件。浏览器自动保存不代替下载备份，具体操作见包内 README。</p>
</section>
"""
EXAMPLES = [
    ("Who did not submit the homework?", "Alice submitted her homework. Bob did not submit his homework.",
     "There are twenty students in the class.",
     ("X 支持：勾选人物或对象、行为或关系、肯定或否定；摘录 Bob did not submit his homework.。"
     "补充说明可以留空。Y 证据不足：勾选缺少必要信息，以及人物或对象、行为或关系。"
     "比较选择 X；依据为一段提供必要证据，另一段不足。查询歧义选无。")),
    ("Which room is open after 6 p.m.?", "Room A closes at 5 p.m.", "Room B stays open until 8 p.m.",
     ("X 明确不满足必要条件，Y 支持。两段都勾选人物或对象、时间数量或比较条件，并分别摘录完整句子；"
     "普通清楚情况的补充说明可以留空。比较选择 Y，依据为一段满足必要条件，另一段明确不满足。查询歧义选无。")),
    ("Did Mia bring a notebook?", "Mia did not bring a notebook.", "Mia left her notebook at home and arrived without it.",
     ("两段均能回答是否带来，因此都可判支持。勾选人物或对象、行为或关系、肯定或否定，并分别摘录完整句子；"
     "比较选无严格优劣，依据为两段均能支持。查询歧义选无，补充说明可以留空。否定句本身不是不相关的理由。")),
]
PRACTICES = [
    {"case_id": "practice-1", "query": "What time does the chess club meet on Wednesday?",
     "paragraphs": [{"display_id": "X", "content": "On Wednesday, the chess club meets at 4 p.m. in Room 3."},
                    {"display_id": "Y", "content": "The chess club meets in Room 3 on Friday at 5 p.m."}],
     "reference": "X 支持并摘录完整句子；Y 证据不足，可勾缺少必要信息和时间数量或比较条件，摘录可选。X 更适合；比较依据为一段提供必要证据，另一段不足。无需普通补充说明。"},
    {"case_id": "practice-2", "query": "Did Ella bring an umbrella?",
     "paragraphs": [{"display_id": "X", "content": "Ella left her umbrella at home and arrived without one."},
                    {"display_id": "Y", "content": "Ella did not bring an umbrella."}],
     "reference": "两段都支持对是否带伞的回答；均需摘录，依据可选人物、行为、肯定或否定。无严格优劣，依据为两段均能支持。无需普通补充说明。"},
    {"case_id": "practice-3", "query": "Did he return the book?",
     "paragraphs": [{"display_id": "X", "content": "Sam returned the book on Monday."},
                    {"display_id": "Y", "content": "Alex returned the book on Tuesday."}],
     "reference": "查询未交代 he 指谁，可选有歧义、两段无法裁定，逐段简注无法确定 he 的指代。依据可勾人物和歧义；若无法选择，类别可留空。比较无法裁定，依据为存在歧义或矛盾无法可靠比较，补充同一疑点。摘录可选。"},
]


def select(id_: str, label: str, options: dict) -> str:
    return f'<label>{label}<select id="{id_}"><option value="">请选择</option>' + ''.join(
        f'<option value="{html.escape(k)}">{html.escape(v)}</option>' for k, v in options.items()) + '</select></label>'


def tutorial_html() -> str:
    examples = ''.join(f'<section><h2>示例 {i}</h2><p>查询：{html.escape(q)}</p><pre>X：{html.escape(x)}\nY：{html.escape(y)}</pre><p>{html.escape(note)}</p></section>'
                       for i, (q, x, y, note) in enumerate(EXAMPLES, 1))
    forms = []
    for i, c in enumerate(PRACTICES, 1):
        prefix = f'p{i}-'
        parts = [f'<form id="p{i}"><h2>独立练习 {i}</h2><p>{html.escape(c["query"])}</p>',
                 select(prefix+'ambiguity', '影响判断的查询歧义', {'no': '无', 'yes': '有', 'uncertain': '无法判断'})]
        for p in c['paragraphs']:
            side = prefix+p['display_id']
            parts += [f'<h3>段落 {p["display_id"]}</h3><pre id="{side}-text">{html.escape(p["content"])}</pre>',
                      select(side+'-app', '适用性', {k: k for k in APPLICABILITY}),
                      reason_controls(side),
                      (f'<button type="button" id="{side}-capture">将所选原文记为证据</button>'
                      f'<label>证据摘录（支持／明确不满足时必填）<textarea id="{side}-evidence"></textarea></label>'
                      f'<label>起始<input id="{side}-start" type="number">结束（不含）<input id="{side}-end" type="number"></label>'
                      f'<label>补充说明（无法裁定、其他或无法用类别说明缺失信息时必填）<textarea id="{side}-reason"></textarea></label>')]
        parts += [select(prefix+'preference', '相对偏好', {'X':'X 更适合','Y':'Y 更适合','tie':'无严格优劣','undetermined':'无法裁定'}),
                  pair_reason_control(prefix), f'<label>比较补充（歧义、特殊比较或其他原因时必填）<textarea id="{prefix}pair-reason"></textarea></label>',
                  select(prefix+'status', '复核状态', {'待复核':'待复核','独立复核':'独立复核','争议保留':'争议保留'}),
                  f'<p id="p{i}-missing" role="status"></p></form>']
        forms.append(''.join(parts))
    payload = json.dumps({'cases': PRACTICES, 'reason_contract': CONTRACT,
                          'storage_key': 'linkrag-authored-tutorial-structured-v2'}, ensure_ascii=False).replace('<', '\\u003c')
    references = ''.join(f'<p>练习 {i}：{html.escape(c["reference"])}</p>' for i,c in enumerate(PRACTICES,1))
    return ('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>独立审阅入门</title><style>body{font:17px/1.7 system-ui;max-width:980px;margin:24px auto;padding:0 18px;color:#172333;background:#f5f6f8}
section,form{background:white;padding:22px;border:1px solid #dbe1e8;border-radius:10px;margin:20px 0}label{display:block;margin:10px 0}
textarea{width:100%;min-height:65px}input,select,textarea,button{font:inherit}button{padding:10px;margin:10px 0}pre{white-space:pre-wrap;font:17px/1.6 Georgia}fieldset{border:1px solid #ccd5e0}.note{font-size:14px;color:#52637a}[hidden]{display:none!important}
.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:620px}th,td{padding:12px;border:1px solid #ccd5e0;vertical-align:top;text-align:left}thead{background:#eef2f7}th[scope=row]{width:18%}caption{text-align:left;font-weight:bold;margin:8px 0}</style>
<h1>先练习，再独立审阅</h1><p>以下 3 个示例和 3 道练习均为教学自编，不是正式 76 条中的案例，也不是人工金标。练习不计分；独立填完全部 3 题后才显示参考解释。</p>
<p>每段选择适用性，通常至少选一种判断依据。若查询有歧义／无法判断、本段无法裁定，且已在本段补充说明中写明疑点，依据类别可以留空；不强迫选择或摘录。支持／明确不满足仍必须摘录原文。证据不足要指出缺少哪类内容，可勾具体类别或写短注；只勾“缺少必要信息”仍不完整。无法裁定或选择其他时简短写出疑点。普通清楚情况不用反复写理由。</p>
<p>比较依据与相对偏好分别填写，程序不会替你决定。两段都支持、都不足或都不满足也允许；若仍有严格优劣，请简要解释。查询有歧义、无法比较、证据质量差异或其他原因时补充说明。</p>
<p>证据位置按 Unicode 字符计数，推荐选中对应正文后按记录按钮。练习使用与正式页相同的字段条件；练习进度与正式标注隔离。练习内容无需交回。</p>'''
            + FIELD_GUIDE + examples + ''.join(forms) + '<button id="reveal" disabled>全部完成后显示参考解释（不计分）</button><button id="reset">清空练习</button><p id="notice" role="status"></p>'
            + f'<section id="references" hidden><h2>参考解释</h2>{references}<p>允许有不同但有正文依据的判断；参考不自动判定你对错。</p></section>'
            + '<p>完成练习后，打开同目录 <a href="review.html">review.html</a> 开始自己的全部 76 条。仍有疑问请先联系负责人。</p>'
            + f'<script id="review-data" type="application/json">{payload}</script><script>{TUTORIAL_JS}</script></html>')


TUTORIAL_JS = r"""
const data=JSON.parse(document.getElementById('review-data').textContent),reasonContract=data.reason_contract;
/* REASON_LOGIC */
const $=id=>document.getElementById(id),keys=Object.keys(reasonContract.reason_types);
const fields=data.cases.flatMap((c,i)=>{const p='p'+(i+1)+'-';return ['ambiguity','preference','pair-reason-code','pair-reason','status'].map(k=>p+k)
 .concat(['X','Y'].flatMap(s=>['app','evidence','start','end','reason',...keys.map(k=>'basis-'+k)].map(k=>p+s+'-'+k)));});
function readAnswer(c,i){
 const prefix='p'+(i+1)+'-',get=k=>$(prefix+k).value;
 return {answer_schema_version:2,query_ambiguity:get('ambiguity'),pair_preference:get('preference'),pair_reason_code:get('pair-reason-code'),pair_reason:get('pair-reason'),adjudication_status:get('status'),
 paragraphs:c.paragraphs.map(p=>{const s=p.display_id,q=get(s+'-evidence'),start=get(s+'-start'),end=get(s+'-end');
  if(q&&(start===''||end===''||!Number.isInteger(Number(start))||!Number.isInteger(Number(end))||Number(start)<0||Number(end)<=Number(start)||Number(end)>Array.from(p.content).length||Array.from(p.content).slice(Number(start),Number(end)).join('')!==q))throw Error(s+' 证据位置不一致');
  return {display_id:s,applicability:get(s+'-app'),reason_types:keys.filter(k=>$(prefix+s+'-basis-'+k).checked),reason:get(s+'-reason'),evidence_spans:q?[{quote:q,start:Number(start),end:Number(end)}]:[]};})};
}
function update(){
 let all=true;
 data.cases.forEach((c,i)=>{let missing=[];try{const a=readAnswer(c,i);missing=structuredMissing(a).map(missingText);
 if(!a.query_ambiguity)missing.push('请选择查询歧义');if(!a.pair_preference)missing.push('请选择相对偏好');
 if(!['独立复核','争议保留'].includes(a.adjudication_status))missing.push('请选择已完成的复核状态');
 if(a.paragraphs.some(p=>!p.applicability))missing.push('请选择两段适用性');}catch(e){missing=[e.message];}
 $('p'+(i+1)+'-missing').textContent=missing.join('；')||'条件字段已齐全，不代表判断正确。';if(missing.length)all=false;});
 $('reveal').disabled=!all;if(!all)$('references').hidden=true;
}
function save(){update();try{localStorage.setItem(data.storage_key,JSON.stringify(Object.fromEntries(fields.map(id=>[id,id.includes('-basis-')?($(id).checked?'1':''):$(id).value]))));$('notice').textContent='练习已保存，仅限本页；正式标注另行保存。';}catch(e){$('notice').textContent='练习本地保存不可用；本页仍可练习，关闭后可能丢失。';}}
for(const id of fields){$(id).addEventListener('input',save);$(id).addEventListener('change',save);}
for(let i=1;i<=3;i++)for(const side of ['X','Y']){const s='p'+i+'-'+side;$(s+'-text').textContent=data.cases[i-1].paragraphs.find(p=>p.display_id===side).content;
 $(s+'-capture').onclick=()=>{const sel=window.getSelection();if(!sel.rangeCount)return;const r=sel.getRangeAt(0),n=$(s+'-text');if(!n.contains(r.startContainer)||!n.contains(r.endContainer))return;
 const before=r.cloneRange();before.selectNodeContents(n);before.setEnd(r.startContainer,r.startOffset);const quote=r.toString(),start=Array.from(before.toString()).length;
 $(s+'-evidence').value=quote;$(s+'-start').value=String(start);$(s+'-end').value=String(start+Array.from(quote).length);save();};}
try{const raw=localStorage.getItem(data.storage_key);if(raw){const v=JSON.parse(raw);if(!v||typeof v!=='object'||Array.isArray(v))throw Error('format');
 for(const id of fields)if(typeof v[id]==='string'){if(id.includes('-basis-'))$(id).checked=v[id]==='1';else $(id).value=v[id];}}}catch(e){$('notice').textContent='练习草稿无法恢复；可重新填写。';}
update();$('reveal').onclick=()=>{update();if(!$('reveal').disabled)$('references').hidden=false;};
$('reset').onclick=()=>{if(!window.confirm('清空这 3 道练习？正式标注不受影响。'))return;for(const id of fields){if(id.includes('-basis-'))$(id).checked=false;else $(id).value='';}$('references').hidden=true;save();};
""".replace('/* REASON_LOGIC */', REASON_LOGIC_JS)
