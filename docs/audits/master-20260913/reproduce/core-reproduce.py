import asyncio
import ast
import contextlib
import io
import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from linkrag_eval import app, cli
from linkrag_eval.compute.protocol import Bm25Tokens
from linkrag_eval.models import EvalResult, Layer, MetricResult
from linkrag_eval.store.sqlite_bm25 import SQLiteBm25Point, SQLiteBm25Store

OUT = Path('/tmp/linkrag-core-audit')
REPO = Path('/Users/kawauso/Documents/Projects/LinkRag-Eval-issue22-completion')

async def bm25_check():
    path = OUT / 'bm25.sqlite3'
    store = SQLiteBm25Store(path, coarse_weight=100, fine_weight=0)
    await store.upsert_chunks([
        SQLiteBm25Point('coarse', 1, 990001, 1, 'text', Bm25Tokens('needle', 'hay')),
        SQLiteBm25Point('fine', 2, 990001, 1, 'text', Bm25Tokens('hay', 'needle')),
    ])
    request = SimpleNamespace(tokens=['needle'], dataset_id=1, user_id=990001, top_k=10)
    actual1 = [(h.chunk_id, h.score) for h in await store.recall_topk_chunks(request)]
    store.coarse_weight, store.fine_weight = 0, 100
    actual2 = [(h.chunk_id, h.score) for h in await store.recall_topk_chunks(request)]
    with sqlite3.connect(path) as con:
        expected = con.execute("SELECT chunk_id, -bm25(bm25_fts, 0,0,0,0,0,100,0) FROM bm25_fts WHERE bm25_fts MATCH 'needle' ORDER BY 2 DESC").fetchall()
    return {'configured_100_0':actual1, 'configured_0_100':actual2, 'correct_column_100_0':expected}

def migration_check():
    tree = ast.parse((REPO/'alembic/env.py').read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_resolve_url')
    namespace = {'config':SimpleNamespace(attributes={}), 'os':os}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'alembic/env.py', 'exec'), namespace)
    with patch.dict(os.environ, {'ALEMBIC_DATABASE_URL':'mysql+pymysql://example.invalid/tolink_rag_db'}):
        return {'accepted_url':namespace['_resolve_url'](), 'network_calls':0}

async def overwrite_check():
    label='run-top10'
    results=[]
    for value in (1.0, 0.0):
        results.append(EvalResult(run_id=label, snapshot=app._minimal_snapshot(label,10), metrics=[MetricResult(name='recall_chunk',layer=Layer.RETRIEVAL,k=10,mean=value,n=40)]))
    observed=[]
    async def save_result(*args, **kwargs): pass
    def report(result, *args, baseline=None, **kwargs):
        observed.append({'current':result.metrics[0].mean, 'baseline':baseline.metrics[0].mean if baseline else None})
        return {'html':'/tmp/stub.html','json':'/tmp/stub.json'}
    args=SimpleNamespace(dense_top_k=None,sparse_top_k=None,dense_score_threshold=None,sparse_score_threshold=None,dense_weight=None,sparse_weight=None,bm25_weight=None,bm25_top_k=None,enabled_sources=None,run_label='run',top_k=10,precheck=False,out_dir=str(OUT/'run'),dataset='test',golden='unused',require_chunk_references=False,baseline=None)
    with patch('linkrag_eval.config.get_settings',return_value=SimpleNamespace()), patch('linkrag_eval.app.run_eval',new=AsyncMock(side_effect=results)), patch('linkrag_eval.retrieval.build_eval_recall_evaluable',return_value=object()), patch('linkrag_eval.store.db_result_store.EvalDbResultStore',return_value=SimpleNamespace(save_result=save_result)), patch('linkrag_eval.reporters.write_retrieval_reports',side_effect=report), contextlib.redirect_stdout(io.StringIO()):
        await cli._do_run(args)
        args.baseline=label
        await cli._do_run(args)
    saved=json.loads((OUT/'run/results/run-top10.json').read_text())
    return {'runs':observed,'result_files':len(list((OUT/'run/results').glob('*.json'))),'saved_metric':saved['metrics'][0]['mean']}

async def ingest_failure_check():
    async def fail(*args, **kwargs): raise RuntimeError('synthetic failure')
    indexer=SimpleNamespace(index_passages=fail)
    with patch('linkrag_eval.app.load_manifest',return_value=[SimpleNamespace(status='success',doc_id=1,source_id='p',ordinal=0)]), patch('linkrag_eval.app.read_tsv_collection',return_value={'p':'safe text'}):
        total=await app.run_ingest(1,'unused','unused',indexer=indexer,corpus_repo=SimpleNamespace(),retries=1)
    return {'total':total,'raised':False}

async def main():
    output={'bm25_weights':await bm25_check(),'migration_guard':migration_check(),'run_overwrite':await overwrite_check(),'ingest_failure':await ingest_failure_check()}
    (OUT/'evidence.json').write_text(json.dumps(output,indent=2))
    print(json.dumps(output,indent=2))
asyncio.run(main())
