"""Versioned structured review distribution; public cases and private identities stay fixed."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from .review_handoff import file_sha256, read_rows
from .review_persistence import durable_html
from .review_schema import (
    CONTRACT,
    REASON_SCHEMA_VERSION,
    STORAGE_SUFFIX,
    VALIDATION_POLICY_VERSION,
    pair_reason_control,
    reason_controls,
)
from .review_tutorial import tutorial_html

FILES = ('review.html', 'cases.jsonl', 'blank-answers.jsonl', 'README.md', '标注入门.html')
INSTRUCTIONS = '''# 独立审阅：结构化原因版

每人独立完成自己收到的全部 76 条。以当前查询和正文为依据，不上网补事实，不使用 AI 代审，不查看另一人的意见。允许两段都支持、都不足、都不满足或无法比较；不强迫一正一负，不预设问题都属于某种类型。

## 打开

1. 完整解压自己的 ZIP 到固定文件夹；用桌面浏览器先打开 `标注入门.html`。3 个示例和 3 道练习均为自编教学内容，不是正式材料，不计分。全部练习条件字段齐全后才显示参考解释。
2. 再打开同目录 `review.html`，填稳定姓名或代号，类型选“人类审阅者”。不要在 ZIP 预览或无痕窗口里填写。

## 填写

先看查询，再独立判断 X、Y，最后比较。四种段落适用性保持原意：“支持所问条件”“明确不满足必要条件”“相关但证据不足”“无法裁定”。“没做”可以回答“是否做过”，不能仅因为是否定句就判不支持。

| 字段 | 什么时候需要填写 |
| --- | --- |
| 每段判断依据（可多选） | 通常至少一类；若查询有歧义／无法判断、本段无法裁定，且本段补充已写明疑点，可留空。其余只勾与自己判断有关的类型，类别本身不表示条件已满足。 |
| 原文摘录 | 支持或明确不满足时必填；证据不足或无法裁定时可选。选中对应正文后按记录按钮，自动填 Unicode 字符位置。不能用说明替代原文。 |
| 缺少什么 | 证据不足时指出内容类型：可选人物／行为／肯否／时间数量等，或补充一句。只勾“缺少必要信息”仍需具体化。 |
| 段落补充说明 | 无法裁定、选其他／说不清，或没有用类别说明缺少什么时必填。普通清楚情况可以留空。 |
| 比较依据 | 必填，8 个固定选项覆盖单段优势、两段均支持／不足／不满足、证据质量差异、歧义和其他；不会自动改变偏好。 |
| 比较补充 | 证据质量差异、歧义／其他、查询有歧义／无法判断、比较无法裁定时必填。若两段处于同类状态但选择严格优劣，或选择单段优势却判无严格优劣，也请简要说明。其余可以留空。 |

完成的题选“独立复核”；保留疑问可选“争议保留”并说明疑点。未审题保持“待复核”。若已见过某例分析，请在补充说明里注明。

## 保存、恢复、导出

每次输入、选择会自动保存，页底显示状态。**每次离开前点“下载备份（可恢复）”，确认下载目录出现 JSON 文件。** 不要只保存网页或原 ZIP，不要清理浏览器数据或多窗口同时填写。同一浏览器也可能因移动目录、换地址或设备而读不到草稿，独立 JSON 备份用于恢复。

点“导入备份／结果”恢复自己的 JSON。版本 2 严格核对自己的包、正文、原因格式；不接受别人的包。导入替换当前内容前先下载当前备份。旧版本 1 的草稿或结果可导入，原文字和证据保留，新增原因类型不会自动推断；请逐题补选并核对。新旧本地草稿使用不同存储键，旧草稿不被覆盖。无法直接读取旧本地草稿时，先在旧页下载 JSON，再到新页导入。

本轮只修订完整性检查策略，版本 2 的已导出文件无需修改或重导出。旧页面的完成数可能仍沿用旧规则；负责人按新策略重新检查原答案，不修改原文件中的旧摘要。因歧义无法裁定的有效记录仍是待裁定意见，不能当作已确定的相关性标签。

浏览器保存失败会明确提示，当前页仍可下载备份和导出。下载开始不等于文件已落盘，请检查浏览器下载记录。任何离线页面都不能保证断电或文件被删后恢复，务必保留独立备份。

点“导出标注结果”，交回末尾为 `-answers.json` 的完整原文件。页面分别提示条件字段完整数和记录数；字段完整不代表判断正确。部分结果可导出，但请注明进度；最终每人应完成全部 76 条。证据位置错误时会输出可恢复备份，修正后再导出。不要交截图或空白模板。旧格式结果不能直接当成本版完整提交，需先导入补填再导出。

`cases.jsonl` 是原公共材料；`blank-answers.jsonl` 是新版空白结构参考，无需手工编辑。所有 JSON 原文件请保留，交回后由负责人核对映射并生成待人类裁定的分歧，不自动裁定。
'''


def structured_html(reviewer: str, cases: list[dict]) -> str:
    page = durable_html(reviewer, cases)
    pattern = r'(<script type="application/json" id="review-data">)(.*?)(</script>)'
    match = re.search(pattern, page, re.DOTALL)
    data = json.loads(match[2])
    data.update(schema_version=2, reason_contract=CONTRACT, legacy_storage_key=data['storage_key'],
                storage_key=data['storage_key']+STORAGE_SUFFIX)
    encoded = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')
    page = page[:match.start(2)] + encoded + page[match.end(2):]
    page = page.replace('<h1>NevIR 开发材料独立盲审</h1>', '<h1>NevIR 独立盲审 · 结构化原因版</h1><p><a href="标注入门.html">先阅读示例并完成练习</a> · 每人完成全部 76 条</p><p id="migration-notice" role="status" class="note"></p>')
    for side in ('X', 'Y'):
        anchor = f'<label>适用性<select id="{side}-app"></select></label>'
        page = page.replace(anchor, anchor + reason_controls(side) + f'<p id="{side}-requirements" class="note" aria-live="polite"></p>')
        page = page.replace(f'<label>简短理由<textarea id="{side}-reason">', f'<label>补充说明（无法裁定、其他或未说明缺失类型时必填）<textarea id="{side}-reason">')
    page = page.replace('证据逐字摘录<textarea', '证据逐字摘录（支持／明确不满足时必填）<textarea')
    page = page.replace('<label>理由<textarea id="pair-reason">', pair_reason_control() + '<label>比较补充（歧义、特殊比较或其他时必填）<textarea id="pair-reason">')
    return page


def upgrade_structured(source_manifest: Path, out: Path) -> dict:
    if out.exists():
        raise ValueError('refuse to overwrite distribution')
    manifest = json.loads(source_manifest.read_text())
    for reviewer, p in manifest['packages'].items():
        for name, digest in p['distribution_files'].items():
            if file_sha256(source_manifest.parent/reviewer/name) != digest:
                raise ValueError('source distribution changed')
        if file_sha256(Path(p['zip_path'])) != p['zip_sha256']:
            raise ValueError('source ZIP changed')
        if file_sha256(Path(p['mapping_path'])) != p['mapping_sha256']:
            raise ValueError('private mapping changed')
    out.mkdir(parents=True)
    tutorial = tutorial_html()
    for reviewer, p in manifest['packages'].items():
        src, dest = source_manifest.parent/reviewer, out/reviewer
        dest.mkdir()
        shutil.copyfile(src/'cases.jsonl', dest/'cases.jsonl')
        cases, blank = read_rows(src/'cases.jsonl'), read_rows(src/'blank-answers.jsonl')
        if [r['case_id'] for r in cases] != [r['case_id'] for r in blank]:
            raise ValueError('blank form identities/order differ')
        for row in blank:
            if row['reviewer_name'] or any(p['reason'] or p['evidence_spans'] or p['applicability'] for p in row['paragraphs']):
                raise ValueError('source blank contains existing answers')
            row.update(answer_schema_version=2, pair_reason_code=None)
            for paragraph in row['paragraphs']:
                paragraph['reason_types'] = []
        (dest/'blank-answers.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in blank))
        (dest/'review.html').write_text(structured_html(reviewer,cases))
        (dest/'README.md').write_text(INSTRUCTIONS)
        (dest/'标注入门.html').write_text(tutorial)
        archive = out/f'{reviewer}_package.zip'
        with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
            for name in FILES:
                z.write(dest/name,f'{reviewer}/{name}')
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and set(z.namelist()) == {f'{reviewer}/{n}' for n in FILES}
            for name in FILES:
                assert z.read(f'{reviewer}/{name}') == (dest/name).read_bytes()
        p.update(zip_path=str(archive.resolve()),zip_sha256=file_sha256(archive),
                 distribution_files={n:file_sha256(dest/n) for n in FILES},
                 page_version='structured_review_v2',tutorial_version='structured_tutorial_v2',
                 original_cases_and_order_unchanged=True, blank_schema_upgraded=True)
        p.pop('review_page_unchanged_after_tutorial',None)
    manifest.update(created_at=datetime.now(UTC).isoformat(), upgraded_from=str(source_manifest.resolve()),
                    answer_schema_version=2,reason_schema_version=REASON_SCHEMA_VERSION,persistence_version='structured_review_v2',
                    validation_policy_version=VALIDATION_POLICY_VERSION,
                    tutorial='3 authored examples + 3 independent exercises; shared conditional requirements; no grading',
                    browser_acceptance='not verified in real browser; standing Browser URL security denial, no workaround',
                    script_acceptance='pending final ZIP QA',human_submissions_received=0,
                    adjudication_status='pending',synthetic_qa_is_not_human_submission=True)
    for obsolete in ('final_independent_acceptance','previous_distribution_archive','tutorial_added_at','intake_revision'):
        manifest.pop(obsolete,None)
    (out/'handoff-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-manifest',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    result=upgrade_structured(args.source_manifest,args.out)
    print(json.dumps({name:p['zip_path'] for name,p in result['packages'].items()},indent=2))


if __name__ == '__main__':
    main()
