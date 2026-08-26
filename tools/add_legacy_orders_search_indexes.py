"""旧BONUS_SYSTEM(リンパ) 注文一覧の絞り込み・並び替え用インデックスを張る。

主キー追加までで既定表示と注文日検索は速くなったが、まだインデックスの無い列で
絞り込む・並べ替えると 1 回 60〜230 秒かかる（実測）。

    注文状況で絞る          82 秒
    注文区分で絞る          84 秒
    注文番号の部分一致     126 秒
    会員IDの部分一致       233 秒
    会員IDで並べ替え       233 秒
    金額・作成日時で並べ替え 90〜135 秒

一覧は「まず ID だけを引くサブクエリ」に変えてあるので、対象列 1 本のインデックスが
あればそのサブクエリはインデックスだけで完結する（主キー追加により二次インデックスは
暗黙に ID を含む）。前方一致でない LIKE でも、200MB のテーブル本体ではなく
数十MB のインデックスだけを走査すれば済むようになる。

いずれも二次インデックスなので INPLACE / LOCK=NONE でオンラインに追加できる。
何度実行しても既にあるものは飛ばす。

    python tools/add_legacy_orders_search_indexes.py --dry-run
    python tools/add_legacy_orders_search_indexes.py
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

# 画面の絞り込み欄・並び替え可能な見出しに対応する列だけを対象にする。
INDEXES = (
    ("idx_jp_om_orders_doc_no", "(DOC_NO)", "注文番号の絞り込みと並び替え"),
    ("idx_jp_om_orders_order_status", "(ORDER_STATUS)", "注文状況の絞り込みと並び替え"),
    ("idx_jp_om_orders_order_type", "(ORDER_TYPE)", "注文区分の絞り込みと並び替え"),
    ("idx_jp_om_orders_member_id", "(MEMBER_ID)", "会員IDの絞り込みと並び替え"),
    ("idx_jp_om_orders_firstname", "(FIRSTNAME)", "注文者_氏名の絞り込みと並び替え"),
    ("idx_jp_om_orders_lastname", "(LASTNAME)", "注文者_氏名の絞り込み"),
    ("idx_jp_om_orders_bonus_date", "(BONUS_DATE)", "ボーナス計算対象日の並び替え"),
    ("idx_jp_om_orders_create_date", "(CREATE_DATE)", "作成日時の並び替え"),
    ("idx_jp_om_orders_total_amount", "(TOTAL_NET_AMOUNT)", "購入合計金額の並び替え"),
    ("idx_jp_om_orders_total_bv", "(TOTAL_BV)", "合計BVの並び替え"),
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


def table_size(cursor):
    cursor.execute(
        """
        SELECT ROUND(DATA_LENGTH/1024/1024), ROUND(INDEX_LENGTH/1024/1024)
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        """,
        [SCHEMA, TABLE],
    )
    return cursor.fetchone()


def main():
    dry_run = "--dry-run" in sys.argv

    with connections["rds"].cursor() as cursor:
        present = existing_indexes(cursor)
        print(f"既存インデックス: {sorted(present)}")
        data_mb, index_mb = table_size(cursor)
        print(f"現在のサイズ: データ {data_mb}MB / インデックス {index_mb}MB")
        print()

        for name, columns, purpose in INDEXES:
            sql = (
                f"ALTER TABLE {SCHEMA}.{TABLE} "
                f"ADD INDEX {name} {columns}, "
                f"ALGORITHM=INPLACE, LOCK=NONE"
            )
            if name in present:
                print(f"skip : {name} は既にあります")
                continue
            if dry_run:
                print(f"dry  : {columns:22} {purpose}")
                continue

            print(f"実行 : {columns:22} {purpose}")
            started = time.time()
            cursor.execute(sql)
            print(f"       完了 ({(time.time() - started) * 1000:.0f} ms)")

        if dry_run:
            return

        print()
        print("統計情報を更新します")
        cursor.execute(f"ANALYZE TABLE {SCHEMA}.{TABLE}")
        data_mb, index_mb = table_size(cursor)
        print(f"更新後のサイズ: データ {data_mb}MB / インデックス {index_mb}MB")
        print(f"最終インデックス: {sorted(existing_indexes(cursor))}")


if __name__ == "__main__":
    main()
