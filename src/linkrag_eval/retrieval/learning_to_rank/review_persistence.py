"""Standalone durable review UI; retain original cases, storage key and answer schema."""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from linkrag_eval.retrieval.learning_to_rank.nevir_diagnostics import _REVIEW_JS, _review_html
from linkrag_eval.retrieval.learning_to_rank.review_handoff import file_sha256, read_rows
from linkrag_eval.retrieval.learning_to_rank.review_schema import REASON_LOGIC_JS

DURABLE_JS = r"""
const data = JSON.parse(document.getElementById('review-data').textContent);
const structured=data.schema_version===2, reasonContract=data.reason_contract||{};
const reasonKeys=Object.keys(reasonContract.reason_types||{});
/* REASON_LOGIC */
const $ = id => document.getElementById(id);
const cases = new Map(data.cases.map(c=>[c.case_id,c]));
const fields = ['ambiguity','preference','pair-reason','status',
  ...['X','Y'].flatMap(s=>['app','evidence','start','end','reason'].map(k=>s+'-'+k))];
if(structured)fields.push('pair-reason-code',...['X','Y'].flatMap(s=>reasonKeys.map(k=>s+'-basis-'+k)));
let index=0, answers=Object.create(null), drafts=Object.create(null), needsBackup=false;
let migratedLegacy=false;
let storageBlocked=false, unreadableStorage='', originalReadError=false;
let storageConflict=false;
const say = text => {$('notice').textContent=text;};
const statuses=['','支持所问条件','明确不满足必要条件','相关但证据不足','无法裁定'];
for(const side of ['X','Y']) for(const value of statuses){
  const option=document.createElement('option');option.value=value;option.textContent=value||'请选择';
  $(side+'-app').appendChild(option);
}
function rawAnswer(a){
  const r={'ambiguity':a.query_ambiguity||'','preference':a.pair_preference||'',
    'pair-reason':a.pair_reason||'','status':a.adjudication_status||'待复核'};
  for(const side of ['X','Y']){
    const p=(a.paragraphs||[]).find(p=>p.display_id===side)||{}, s=(p.evidence_spans||[])[0]||{};
    Object.assign(r,{[side+'-app']:p.applicability||'',[side+'-evidence']:s.quote||'',
      [side+'-start']:String(s.start??''),[side+'-end']:String(s.end??''),[side+'-reason']:p.reason||''});
    if(structured)for(const k of reasonKeys)r[side+'-basis-'+k]=(p.reason_types||[]).includes(k)?'1':'';
  }
  if(structured)r['pair-reason-code']=a.pair_reason_code||'';
  return r;
}
function span(raw,side,c){
  const quote=raw[side+'-evidence']||'';
  if(!quote)return [];
  const rs=raw[side+'-start'],re=raw[side+'-end'],start=Number(rs),end=Number(re);
  const chars=Array.from(c.paragraphs.find(p=>p.display_id===side).content||'');
  if(rs===''||re===''||!Number.isInteger(start)||!Number.isInteger(end)||start<0||end<=start
      ||end>chars.length||chars.slice(start,end).join('')!==quote)throw Error(c.case_id+'：'+side+' 证据位置不一致');
  return [{quote,start,end}];
}
function normalize(raw,c){
  const result={case_id:c.case_id,reviewer_name:$('reviewer').value,reviewer_type:$('reviewer-type').value||null,
    query_ambiguity:raw.ambiguity||null,pair_preference:raw.preference||null,
    pair_reason:raw['pair-reason']||'',adjudication_status:raw.status||'待复核',
    paragraphs:['X','Y'].map(side=>({display_id:side,applicability:raw[side+'-app']||null,
      evidence_spans:span(raw,side,c),reason:raw[side+'-reason']||''}))};
  if(structured){result.answer_schema_version=2;result.pair_reason_code=raw['pair-reason-code']||null;
    for(const p of result.paragraphs)p.reason_types=reasonKeys.filter(k=>raw[p.display_id+'-basis-'+k]==='1');}
  return result;
}
function snapshot(){
  const rows=[];
  for(const c of data.cases){
    if(structured&&drafts[c.case_id]){try{rows.push(normalize(drafts[c.case_id],c));}catch(e){/* raw draft remains recoverable */}}
    else if(answers[c.case_id])rows.push(answers[c.case_id]);
  }
  return {schema_version:structured?2:1,reason_schema_version:structured?reasonContract.reason_schema_version:undefined,
    validation_policy_version:structured?reasonContract.validation_policy_version:undefined,
    draft_format:structured?2:1,migrated_from_legacy:migratedLegacy||undefined,packet:data.packet,storage_key:data.storage_key,
    scheduled_cases:data.cases.length,exported_at:new Date().toISOString(),
    reviewer_name:$('reviewer').value,reviewer_type:$('reviewer-type').value||null,
    position:index,answers:rows,
    drafts: {...drafts},unreadable_local_storage:unreadableStorage||undefined};
}
function store(){
  try{
    if(originalReadError)throw Error('原草稿不能读取，保留原数据');
    if(storageConflict)throw Error('其他窗口修改了草稿');
    localStorage.setItem(data.storage_key,JSON.stringify(snapshot()));storageBlocked=false;
    say('已自动保存到此浏览器 · 已记录 '+Object.keys(drafts).length+' / '+data.cases.length+' 题。离开前请下载备份。');
  }catch(error){storageBlocked=true;say((storageConflict?'其他窗口修改了草稿，已停止覆盖保存。':'浏览器保存不可用：')+'当前内容仅在本页内存中！请立即下载备份；仍可导出结果。');}
}
function remember(){
  const c=data.cases[index],raw=Object.fromEntries(fields.map(id=>[id,id.includes('-basis-')?($(id).checked?'1':''):$(id).value]));
  drafts[c.case_id]=raw;needsBackup=true;
  try{answers[c.case_id]=normalize(raw,c);}catch(error){delete answers[c.case_id];}
  store();
  if(structured)showRequirements(raw,c);
}
function showRequirements(raw,c){
 if(!structured)return;
 let missing=[];try{missing=structuredMissing(normalize(raw,c));}catch(error){missing=['X.evidence','Y.evidence'];}
 for(const side of ['X','Y'])$(side+'-requirements').textContent=missing.filter(k=>k.startsWith(side+'.')).map(missingText).join('；')||'本段条件字段已齐全；不代表判断已核验。';
 $('pair-requirements').textContent=missing.filter(k=>!k.includes('.')).map(missingText).join('；')||'比较依据已记录；程序不会据此改动偏好。';
 $('migration-notice').textContent=migratedLegacy?'已从旧格式恢复原文字；新增依据类型未自动选择，请逐题核对补填。旧本地草稿没有覆盖。':'';
}
function show(){
  const c=data.cases[index],raw=drafts[c.case_id]||rawAnswer(answers[c.case_id]||{});
  $('position').textContent=`${index+1} / ${data.cases.length} · ${c.case_id}`;
  $('query').textContent=c.query;
  for(const p of c.paragraphs)$(p.display_id+'-text').textContent=p.content??'[正文不可用]';
  for(const id of fields){if(id.includes('-basis-'))$(id).checked=raw[id]==='1';else $(id).value=raw[id]??(id==='status'?'待复核':'');}
  if(structured)showRequirements(raw,c);
  $('previous').disabled=index===0;$('next').disabled=index===data.cases.length-1;
}
function validateImport(v,local=false){
  if(!v||typeof v!=='object'||Array.isArray(v))throw Error('备份格式不正确');
  const version=v.schema_version??(local?1:null);
  if(!(structured?[1,2]:[1]).includes(version)||(!local&&(v.packet!==data.packet||v.scheduled_cases!==data.cases.length)))throw Error('不是这份审阅包的备份或格式版本不支持');
  const incomingKey=structured&&version===1?data.legacy_storage_key:data.storage_key;
  if(v.storage_key&&v.storage_key!==incomingKey)throw Error('正文版本或审阅包不匹配');
  if(version===2&&(v.storage_key!==data.storage_key||v.reason_schema_version!==reasonContract.reason_schema_version))throw Error('结构化原因版本不匹配');
  if(typeof v.reviewer_name!=='string'||![null,'','human','ai_provisional'].includes(v.reviewer_type??null))throw Error('审阅者信息格式不正确');
  const nextAnswers=Object.create(null),nextDrafts=Object.create(null);
  const rows=Array.isArray(v.answers)?v.answers:(local&&v.answers&&typeof v.answers==='object'?Object.values(v.answers):null);
  if(!rows)throw Error('缺少 answers');
  for(const a of rows){
    if(!a||!cases.has(a.case_id)||nextAnswers[a.case_id])throw Error('未知或重复的匿名编号');
    if(!Array.isArray(a.paragraphs)||a.paragraphs.length!==2||a.paragraphs.some((p,i)=>p.display_id!==['X','Y'][i]))throw Error('段落标识不匹配');
    if(![null,'','no','yes','uncertain'].includes(a.query_ambiguity??null)
        ||![null,'','X','Y','tie','undetermined'].includes(a.pair_preference??null)
        ||!['待复核','独立复核','争议保留'].includes(a.adjudication_status||'待复核'))throw Error('判断取值不正确');
    for(const p of a.paragraphs){
      if(!statuses.includes(p.applicability||'')||typeof p.reason!=='string'||!Array.isArray(p.evidence_spans)||p.evidence_spans.length>1)throw Error('段落判断格式不正确');
      for(const s of p.evidence_spans){
        const chars=Array.from(cases.get(a.case_id).paragraphs.find(x=>x.display_id===p.display_id).content||'');
        if(!Number.isInteger(s.start)||!Number.isInteger(s.end)||s.start<0||s.end<=s.start||s.end>chars.length
          ||chars.slice(s.start,s.end).join('')!==s.quote)throw Error('导入证据与原文不匹配');
      }
    }
    if(typeof a.pair_reason!=='string')throw Error('理由格式不正确');
    if(version===2)structuredShape(a);
    else if(a.pair_reason_code!==undefined||a.paragraphs.some(p=>p.reason_types!==undefined))throw Error('旧格式中混入新原因字段');
    nextAnswers[a.case_id]=a;nextDrafts[a.case_id]=rawAnswer(a);
  }
  if(v.drafts!==undefined){
    if(v.draft_format!==version||!v.drafts||typeof v.drafts!=='object'||Array.isArray(v.drafts))throw Error('草稿格式不正确');
    for(const [id,raw] of Object.entries(v.drafts)){
      if(!cases.has(id)||!raw||typeof raw!=='object'||Array.isArray(raw)
        ||Object.entries(raw).some(([k,value])=>!fields.includes(k)||typeof value!=='string'))throw Error('草稿编号或字段不匹配');
      if(!['','no','yes','uncertain'].includes(raw.ambiguity||'')
        ||!['','X','Y','tie','undetermined'].includes(raw.preference||'')
        ||!['','待复核','独立复核','争议保留'].includes(raw.status||'')
        ||!statuses.includes(raw['X-app']||'')||!statuses.includes(raw['Y-app']||''))throw Error('草稿选择值不正确');
      if(version===1&&Object.keys(raw).some(k=>k.includes('-basis-')||k==='pair-reason-code'))throw Error('旧草稿混入新格式字段');
      if(version===2&&(Object.entries(raw).some(([k,v])=>k.includes('-basis-')&&!['','1'].includes(v))
          ||(raw['pair-reason-code']&&!Object.hasOwn(reasonContract.pair_reason_codes,raw['pair-reason-code']))))throw Error('结构化草稿选项不正确');
      nextDrafts[id]={...raw};
    }
  }
  return {answers:nextAnswers,drafts:nextDrafts,name:v.reviewer_name,type:v.reviewer_type||'',
    migrated:structured&&(version===1||v.migrated_from_legacy===true),
    position:Number.isInteger(v.position)&&v.position>=0&&v.position<data.cases.length?v.position:0};
}
function applyImport(v){
  answers=v.answers;drafts=v.drafts;index=v.position;
  migratedLegacy=!!v.migrated;
  $('reviewer').value=v.name;$('reviewer-type').value=v.type;show();
}
function download(value,suffix){
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;
  a.download=data.packet+'-'+new Date().toISOString().replace(/[:.]/g,'-')+'-'+suffix+'.json';
  document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
}
try{
  const raw=localStorage.getItem(data.storage_key);
  if(raw){unreadableStorage=raw;applyImport(validateImport(JSON.parse(raw),true));unreadableStorage='';}
  else if(structured){const old=localStorage.getItem(data.legacy_storage_key);
    if(old)applyImport(validateImport(JSON.parse(old),true));}
}catch(error){originalReadError=true;storageBlocked=true;}
show();
if(storageBlocked)say('无法读取原本地草稿，原数据不会被覆盖。可导入 JSON 备份；新填写内容请下载备份。');
else say('已恢复本地草稿（若有）。填写时自动保存，离开前仍请下载备份。');
for(const id of [...fields,'reviewer','reviewer-type']){
  $(id).addEventListener('input',remember);$(id).addEventListener('change',remember);
}
for(const side of ['X','Y'])$(side+'-capture').onclick=()=>{
  const selection=window.getSelection();if(!selection.rangeCount)return;
  const range=selection.getRangeAt(0),container=$(side+'-text');
  if(!container.contains(range.startContainer)||!container.contains(range.endContainer)){say('请在对应段落中选择原文');return;}
  const prefix=range.cloneRange();prefix.selectNodeContents(container);prefix.setEnd(range.startContainer,range.startOffset);
  const quote=range.toString(),start=Array.from(prefix.toString()).length;
  $(side+'-evidence').value=quote;$(side+'-start').value=String(start);$(side+'-end').value=String(start+Array.from(quote).length);remember();
};
$('previous').onclick=()=>{remember();if(index>0)index--;store();show();};
$('next').onclick=()=>{remember();if(index<data.cases.length-1)index++;store();show();};
$('save').onclick=remember;
$('backup').onclick=()=>{remember();download(snapshot(),'backup');needsBackup=false;
  say('已发起备份下载：请确认 JSON 文件已在下载目录中。该文件可导入恢复；请勿只保存网页或 ZIP。');};
$('download').onclick=()=>{
  remember();const result=snapshot();
  try{result.answers=data.cases.filter(c=>drafts[c.case_id]).map(c=>normalize(drafts[c.case_id],c));}
  catch(error){download(result,'backup');needsBackup=false;say(error.message+'。已下载可恢复草稿备份，请修正后再导出结果。');return;}
  delete result.unreadable_local_storage;
  if(structured){
    const incomplete=[];
    for(const a of result.answers){const missing=structuredMissing(a);
      if(!a.reviewer_name.trim()||a.reviewer_type!=='human')missing.push('reviewer_identity');
      if(!a.query_ambiguity)missing.push('query_ambiguity');if(!a.pair_preference)missing.push('pair_preference');
      if(!['独立复核','争议保留'].includes(a.adjudication_status))missing.push('review_status');
      if(a.paragraphs.some(p=>!p.applicability))missing.push('paragraph_applicability');
      if(missing.length)incomplete.push({case_id:a.case_id,missing});}
    result.completion={complete_cases:result.answers.length-incomplete.length,scheduled_cases:data.cases.length,incomplete_cases:incomplete};
  }
  download(result,'answers');needsBackup=false;
  say('已发起结果下载（'+(structured?'条件字段完整 '+result.completion.complete_cases+' / '+data.cases.length+'；':'')+'记录 '+result.answers.length+' / '+data.cases.length+' 题，可能含未完成项）。请确认下载文件并交回；也可导入续填。');
};
$('import-file').onchange=async event=>{
  const file=event.target.files[0];if(!file)return;
  try{
    const value=validateImport(JSON.parse(await file.text()));
    if(Object.keys(drafts).length||Object.keys(answers).length||unreadableStorage){
      if(!window.confirm('导入将替换当前草稿。继续前将下载现有草稿备份，请确认下载成功后保留该文件。是否继续？'))return;
      download(snapshot(),'before-import-backup');
    }
    applyImport(value);needsBackup=true;store();
    if(!storageBlocked)say('导入成功，已恢复 '+Object.keys(drafts).length+' 题并保存。可继续填写。');
  }catch(error){say('导入失败，当前草稿未替换：'+error.message);}
  finally{event.target.value='';}
};
window.addEventListener('beforeunload',event=>{
  if(needsBackup||storageBlocked){event.preventDefault();event.returnValue='';}
});
window.addEventListener('storage',event=>{
  if(event.key===data.storage_key||event.key===null){
    storageConflict=true;storageBlocked=true;needsBackup=true;
    say('另一窗口修改或清除了本地草稿。当前窗口已停止覆盖保存，请先下载备份并关闭多余窗口。');
  }
});
""".replace("/* REASON_LOGIC */", REASON_LOGIC_JS)

INSTRUCTIONS = """# 独立审阅：保存与交回

每人独立完成原全部 76 条。以正文为依据，不上网补事实，不使用 AI 代审，不查看另一人的意见。分别判断两段是否支持查询，区分明确不满足、证据不足和无法裁定；允许两段相当，填写证据和理由，不强迫一正一负。若已见过某例分析，请在理由中注明。

## 打开和保存

1. 将 ZIP 完整解压到固定文件夹，用桌面 Chrome、Edge 或 Firefox 打开 `review.html`，不要在 ZIP 预览或无痕窗口中填写。
2. 填写稳定姓名／代号，类型选“人类审阅者”。每次输入和选择都会自动保存到当前浏览器；页面底部显示保存状态。未填完或证据位置暂时不一致也会保留原始草稿。
3. **每次离开前点击“下载备份（可恢复）”，确认下载目录里确实出现 JSON 文件。** 文件名含时间，保留旧备份，不要只保存网页或原 ZIP。系统发起下载不等于文件已经落盘，需检查浏览器下载记录。
4. 不要清理浏览器数据或同时在多个窗口填写同一份材料。换设备、换浏览器、移动目录或本地草稿不可用时，点“导入备份／结果”选择最近的 JSON 恢复。只接受自己的原包，错误编号、正文版本或错误证据会被拒绝。
5. 导入替换已有进度前会征求确认并下载现有草稿备份。导入取消、格式错误不会替换现有内容。

浏览器保存不可用时会明确提示，此时内容仅在页面内存中；立即下载备份。即使本地存储不可用，备份和结果下载仍可使用。任何纯离线页面都不能保证断电、设备损坏或人为删除时绝不丢数据，独立 JSON 备份才是跨设备恢复依据。

## 填写和交回

每人完成全部 76 条。在 X/Y 正文中选中证据后点击记录证据按钮，填写理由、歧义和相对偏好；完成的题设“独立复核”，无法确定可设“争议保留”。位置使用 Unicode 字符，从 0 开始、末端不含，推荐原文选择功能。

完成后点击“导出标注结果”，确认下载了末尾为 `-answers.json` 的文件，将该原文件交回。导出会提示记录数量；记录数量不等于完成数量，仍须逐题核对必填内容。如证据位置不一致，会导出可恢复的 `-backup.json` 草稿并说明原因，修正后再导出正式结果。可部分导出，但交回时注明进度。不要仅交截图或空白模板。

## 如果双击网页无法正常使用

在**仅含自己公共材料**的解压目录运行 `python3 -m http.server 8765 --bind 127.0.0.1`，浏览器打开 `http://127.0.0.1:8765/review.html`。保持同一地址和端口续填。切换打开方式前先下载备份，再导入；不要从项目根目录或含 private 映射的目录启动服务。
"""


def durable_html(reviewer: str, cases: list[dict]) -> str:
    html = _review_html(reviewer, cases)
    html = html.replace(_REVIEW_JS, DURABLE_JS)
    html = html.replace('<button id="download">下载结果</button>',
                        '<button id="backup">下载备份（可恢复）</button>'
                        '<button id="download">导出标注结果</button>'
                        '<label>导入备份／结果<input id="import-file" type="file" accept=".json,application/json"></label>')
    html = html.replace('记录仅保存在本浏览器，最终请下载 JSON。',
                        '输入时自动保存到本浏览器；每次离开前下载 JSON 备份，可导入恢复。')
    html = html.replace('id="notice" class="note"', 'id="notice" class="note" role="status" aria-live="polite"')
    return html


def upgrade_handoff(source_manifest: Path, out: Path) -> dict:
    """New distribution only; original N05 and previous packages remain byte-identical."""
    if out.exists():
        raise ValueError("refuse to overwrite distribution")
    manifest = json.loads(source_manifest.read_text())
    for reviewer, package in manifest["packages"].items():
        for name, digest in package["distribution_files"].items():
            if file_sha256(source_manifest.parent / reviewer / name) != digest:
                raise ValueError("source distribution changed")
        if file_sha256(Path(package["mapping_path"])) != package["mapping_sha256"]:
            raise ValueError("original mapping changed")
    out.mkdir(parents=True)
    for reviewer, package in manifest["packages"].items():
        src, dest = source_manifest.parent / reviewer, out / reviewer
        dest.mkdir()
        for name in ("cases.jsonl", "blank-answers.jsonl"):
            shutil.copyfile(src / name, dest / name)
        cases = read_rows(src / "cases.jsonl")
        if (src / "review.html").read_text() != _review_html(reviewer, cases):
            raise ValueError("upgrade requires the verified original renderer")
        (dest / "review.html").write_text(durable_html(reviewer, cases))
        (dest / "README.md").write_text(INSTRUCTIONS)
        archive = out / f"{reviewer}_package.zip"
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as z:
            for name in package["distribution_files"]:
                z.write(dest / name, f"{reviewer}/{name}")
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            assert set(z.namelist()) == {f"{reviewer}/{n}" for n in package["distribution_files"]}
            for name in package["distribution_files"]:
                assert z.read(f"{reviewer}/{name}") == (dest / name).read_bytes()
        package.update(zip_path=str(archive.resolve()), zip_sha256=file_sha256(archive),
                       distribution_files={name: file_sha256(dest / name) for name in package["distribution_files"]},
                       page_version="durable_review_v1", original_cases_and_order_unchanged=True)
    manifest.update(created_at=datetime.now(UTC).isoformat(),
                    upgraded_from=str(source_manifest.resolve()), persistence_version="durable_review_v1",
                    browser_acceptance="real browser not verified", script_acceptance="pending")
    (out / "handoff-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest
