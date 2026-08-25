"""照合順序修正の同値性と性能を検証する（参照のみ）。"""

import os
import time

import django
import pymysql

pymysql.install_as_MySQLdb()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "connect_app.settings_dev")
django.setup()

from django.db import connections

from connect.basic_income_line_detail import BasicIncomeLineDetailView
from connect.models import PeriodMaster
from connect.sql.basic_income_line_detail_sql import BASIC_INCOME_LINE_DETAIL_CTE_SQL

AFTER_SQL = BASIC_INCOME_LINE_DETAIL_CTE_SQL
FIXED_ON = (
    "ON u.jmoa_code =\n"
    "         CONVERT(a.placement_code USING utf8mb3) COLLATE utf8mb3_bin"
)
assert AFTER_SQL.count(FIXED_ON) == 1, "修正箇所が1件ではありません"

SELECT_COLUMNS = """
    kibetu, placement_code, placement_name, placement_rank, line_code,
    purchaser_code, purchaser_name, path_codes, purchase_bv, carry_over_bv,
    calc_bv, line_rank, line_role_label, line_total_bv, capped_line_total_bv,
    income_line_cap, line_over_cap_bv, income_line_bv, basic_line_bv,
    income_line_over_cap_bv, next_carry_over_bv, detail_type, detail_type_label
"""
ORDER_BY = """
    ORDER BY placement_code, line_total_bv DESC, line_code, detail_sort, purchaser_code
"""

with connections["rds"].cursor() as cursor:
    cursor.execute("SET SESSION MAX_EXECUTION_TIME=300000")

    cursor.execute("SELECT MAX(kibetu) FROM bonus_db.basic_bv_line")
    prev_kibetu = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT kibetu FROM bonus_db.period_master
        WHERE st_date > (SELECT st_date FROM bonus_db.period_master WHERE kibetu = %s)
        ORDER BY st_date LIMIT 1
        """,
        [prev_kibetu],
    )
    kibetu = cursor.fetchone()[0]
    print(f"検証期別: {kibetu}（繰り越し元 {prev_kibetu}）")

    # --- 5,6: 同値性の検証 -------------------------------------------------
    # 変更したのは結合条件の書き方だけなので、両式が同じ行を結び付けるかを直接比較する。
    print("\n=== 結合結果の同値性 ===")
    cursor.execute(
        "SELECT COUNT(*) FROM bonus_db.basic_bv_line WHERE kibetu = %s", [prev_kibetu]
    )
    print(f"  対象 basic_bv_line 行数（kibetu={prev_kibetu}）: {cursor.fetchone()[0]:,}")

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM bonus_db.basic_bv_line AS a
        LEFT JOIN nexus_production.users AS u1
          ON u1.jmoa_code = CONVERT(a.placement_code USING utf8mb3) COLLATE utf8mb3_bin
        LEFT JOIN nexus_production.users AS u2
          ON u2.jmoa_code = a.placement_code
        WHERE a.kibetu = %s
          AND NOT (u1.jmoa_code <=> u2.jmoa_code AND u1.send_bv_name <=> u2.send_bv_name)
        """,
        [prev_kibetu],
    )
    diff = cursor.fetchone()[0]
    print(f"  修正前後で結合先が異なる行: {diff:,}  -> {'一致' if diff == 0 else '不一致'}")

    # CONVERT が非可逆になる値（utf8mb4 固有の4バイト文字）が無いことを全期別で確認する。
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM bonus_db.basic_bv_line
        WHERE placement_code IS NOT NULL
          AND CONVERT(CONVERT(placement_code USING utf8mb3) USING utf8mb4)
              <> placement_code
        """
    )
    print(f"  CONVERT で欠落する placement_code（全期別）: {cursor.fetchone()[0]:,}")

    # --- 7: 修正後の実行時間 ----------------------------------------------
    period = PeriodMaster.objects.using("rds").get(kibetu=kibetu)
    base_params = BasicIncomeLineDetailView._build_period_params(
        BasicIncomeLineDetailView(), kibetu, period
    )
    count_tail = "SELECT COUNT(*) AS cnt FROM income_line_detail WHERE 1 = 1"
    rows_tail = f"SELECT {SELECT_COLUMNS} FROM income_line_detail WHERE 1 = 1 {ORDER_BY}"

    print("\n=== 修正後の実行時間 ===")
    for label, tail in (("COUNT", count_tail), ("全件SELECT", rows_tail)):
        started = time.perf_counter()
        cursor.execute(f"{AFTER_SQL}\n{tail}", base_params)
        rows = cursor.fetchall()
        elapsed = time.perf_counter() - started
        detail = rows[0][0] if label == "COUNT" else len(rows)
        print(f"  {label}: {elapsed:.3f} 秒 / 件数={detail:,}")
        if label == "全件SELECT":
            carry = [r for r in rows if r[22] == "繰り越し"]
            print(f"\n=== 修正した結合が効く行（繰り越し）: {len(carry):,}件 ===")
            for r in carry[:5]:
                print(f"  placement_code={r[1]} name={r[2]} carry_over_bv={r[9]}")
            print(f"  会員名が空の繰り越し行: {sum(1 for r in carry if not r[2]):,}件")
