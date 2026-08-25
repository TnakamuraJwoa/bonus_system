"""旧BONUS_SYSTEM(リンパ) 注文テーブルの ID を主キーにする。

JP_OM_ORDERS は移行時に主キー無しで作られている。InnoDB は主キーが無いと
内部の隠し ROW_ID で行を並べるため、二次インデックスは ID を持てない。
その結果「注文日で絞って ID 順に並べる」という一覧の基本形がどのインデックスでも
成立せず、オプティマイザが ID インデックスを誤選択して 1 ページ 60 秒近くかかる。

ID を主キーにすると
  - クラスタインデックス自体が ID 順になり、既定の ID DESC 並びが只の逆走査になる
  - 二次インデックス（ORDER_DATE）が暗黙に ID を含み、日付で絞って ID 順に
    並べる形がインデックスだけで済む
ため、ID 用の二次インデックスは不要になるので落とす。

前提（実行前に検証する）:
  - ID に NULL が無い（列定義が NOT NULL）
  - ID が一意（COUNT(*) と COUNT(DISTINCT ID) が一致）

注意: 主キー追加はクラスタインデックスの再構築を伴う（177MB）。MySQL 8 では
INPLACE / LOCK=NONE でオンラインに実行できるが、数分かかり一時領域を使う。
以後この表に ID が重複する行を投入すると取込がエラーになる。

    python tools/add_legacy_orders_primary_key.py --dry-run
    python tools/add_legacy_orders_primary_key.py
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
REDUNDANT_ID_INDEX = "idx_jp_om_orders_id"


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

        if "PRIMARY" in present:
            print("skip : 主キーは既にあります")
            return

        print("検証 : ID の一意性を確認します（全走査のため時間がかかります）")
        cursor.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT ID), COUNT(ID) FROM {SCHEMA}.{TABLE}"
        )
        total, distinct_id, non_null_id = cursor.fetchone()
        print(f"       件数={total} / ID異なり数={distinct_id} / ID非NULL数={non_null_id}")
        if not (total == distinct_id == non_null_id):
            print("中止 : ID が一意でない、または NULL があるため主キーにできません")
            sys.exit(1)

        add_pk = (
            f"ALTER TABLE {SCHEMA}.{TABLE} "
            f"ADD PRIMARY KEY (ID), ALGORITHM=INPLACE, LOCK=NONE"
        )
        drop_idx = f"ALTER TABLE {SCHEMA}.{TABLE} DROP INDEX {REDUNDANT_ID_INDEX}"

        if dry_run:
            print(f"dry  : {add_pk}")
            if REDUNDANT_ID_INDEX in present:
                print(f"dry  : {drop_idx}")
            return

        print(f"実行 : {add_pk}")
        started = time.time()
        cursor.execute(add_pk)
        print(f"完了 : 主キー追加  ({(time.time() - started) * 1000:.0f} ms)")

        if REDUNDANT_ID_INDEX in present:
            print(f"実行 : {drop_idx}")
            started = time.time()
            cursor.execute(drop_idx)
            print(f"完了 : 冗長な ID インデックス削除  ({(time.time() - started) * 1000:.0f} ms)")

        print(f"最終インデックス: {sorted(existing_indexes(cursor))}")


if __name__ == "__main__":
    main()
