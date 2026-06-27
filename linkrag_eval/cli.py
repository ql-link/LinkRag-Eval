"""LinkRag-Eval 统一命令入口:``linkrag-eval <command>``。

子命令随各层落地逐步接入(ingest / run / report)。当前为骨架,仅暴露 config 自检。
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="linkrag-eval", description="toLink-Rag 独立评测/质检")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("config", help="打印已解析配置(脱敏)做自检")
    # TODO(step1+): ingest / run / report 子命令随存储、召回、报告层落地接入。

    args = parser.parse_args(argv)

    if args.command == "config":
        from linkrag_eval.config import get_settings

        s = get_settings()
        masked = "***" if s.judge_api_key else "(空)"
        print(f"qdrant_host     = {s.qdrant_host}")
        print(f"qdrant_prefix   = {s.qdrant_prefix}")
        print(f"qdrant_buckets  = {s.qdrant_bucket_count}")
        print(f"mysql           = {s.db_host}:{s.db_port}/{s.db_name}")
        print(f"judge_model     = {s.judge_model or '(空)'}  api_key={masked}")
        print(f"embed_model     = {s.embed_model}  dim={s.embed_dim}")
        print(f"bm25_mode       = {s.bm25_mode}")
        print(f"user_id(route)  = {s.user_id}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
