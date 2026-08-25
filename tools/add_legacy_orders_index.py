"""旧BONUS_SYSTEM(リンパ) 注文テーブルに一覧用のインデックスを張る。

bonus_db.JP_OM_ORDERS は旧システムからの移行コピーで、主キーもインデックスも
1 本も無い（87 万件 / 177MB）。そのため注文一覧はページを開くたびに
テーブル全体を走査して filesort しており、1 ページ目で約 32 秒、
後ろのページでは 110 秒を超える。

ここで張るのは二次インデックスだけなので、MySQL 8 では INPLACE / LOCK=NONE で
オンラインに追加できる（テーブル再構築も書き込み停止も無い）。
何度実行しても既にあるものは飛ばす。

    python tools/add_legacy_orders_index.py          # 追加を実行
    python tools/add_legacy_orders_index.py --dry-run  # 実行内容だけ表示
"""
import os
import sys
import time

import pymysql

pymysql.install_as_MySQLdb()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "connect_app.settings_dev")

import django

django.setup()

from django.db import connections

SCHEMA = "bonus_db"
TABLE = "JP_OM_ORDERS"

# ID: 既定の並び順（o.ID DESC）と Excel 出力のキーセット送りに使う。
#     COUNT(*) もこの小さいインデックスで数えられるようになる。
# ORDER_DATE: 注文日 FROM/TO・注文年・注文月の絞り込みと並び替えに使う。
INDEXES = (
    ("idx_jp_om_orders_id", "(ID)"),
    ("idx_jp_om_orders_order_date", "(ORDER_DATE)"),
)


def existing_indexes(cursor):
    cursor.execute(
        """
        SELECT DISTINCT INDEX_NAME
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        """,
        [SCHEMA, TABLE],
    )
    return {row[0] for row in cursor.fetchall()}


def main():
    dry_run = "--dry-run" in sys.argv

    with connections["rds"].cursor() as cursor:
        present = existing_indexes(cursor)
        print(f"既存インデックス: {sorted(present) or 'なし'}")

        for name, columns in INDEXES:
            sql = (
                f"ALTER TABLE {SCHEMA}.{TABLE} "
                f"ADD INDEX {name} {columns}, "
                f"ALGORITHM=INPLACE, LOCK=NONE"
            )
            if name in present:
                print(f"skip : {name} は既にあります")
                continue
            if dry_run:
                print(f"dry  : {sql}")
                continue

            print(f"実行 : {sql}")
            started = time.time()
            cursor.execute(sql)
            print(f"完了 : {name}  ({(time.time() - started) * 1000:.0f} ms)")

        cursor.execute(
            """
            SELECT ROUND(DATA_LENGTH/1024/1024) AS data_mb,
                   ROUND(INDEX_LENGTH/1024/1024) AS index_mb
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            """,
            [SCHEMA, TABLE],
        )
        row = cursor.fetchone()
        if row:
            print(f"テーブルサイズ: データ {row[0]}MB / インデックス {row[1]}MB")


if __name__ == "__main__":
    main()
