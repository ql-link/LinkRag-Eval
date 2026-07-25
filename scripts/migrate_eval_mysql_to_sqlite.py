#!/usr/bin/env python3
"""从只读 MySQL eval 库同步到本地 SQLite；密码只从环境变量读取。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote_plus

from linkrag_eval.store.database_migration import sync_database


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-host", required=True)
    parser.add_argument("--source-port", type=int, default=3306)
    parser.add_argument("--source-user", default="root")
    parser.add_argument("--source-database", default="tolink_rag_eval_db")
    parser.add_argument("--source-label", help="报告中记录的真实源主机；SSH 隧道场景使用")
    parser.add_argument("--source-backup-ref", help="可选的源备份路径/标识")
    parser.add_argument("--target", default="runs/linkrag_eval.sqlite3")
    parser.add_argument("--report", default="runs/linkrag_eval.sqlite3.migration.json")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if args.source_database != "tolink_rag_eval_db":
        raise SystemExit("安全护栏:只允许读取 tolink_rag_eval_db")
    password = os.environ.get("EVAL_MIGRATION_SOURCE_PASSWORD")
    if password is None:
        raise SystemExit("缺少 EVAL_MIGRATION_SOURCE_PASSWORD")
    source_url = (
        f"mysql+pymysql://{quote_plus(args.source_user)}:{quote_plus(password)}@"
        f"{args.source_host}:{args.source_port}/{args.source_database}?charset=utf8mb4"
    )
    report = sync_database(source_url, args.target, replace=args.replace)
    report.update(
        {
            "source_host": args.source_label or args.source_host,
            "source_port": args.source_port,
            "source_database": args.source_database,
            "source_transport_host": args.source_host,
            "source_backup_ref": args.source_backup_ref,
        }
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
