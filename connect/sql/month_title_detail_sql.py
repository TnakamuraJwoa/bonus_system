MONTH_TITLE_DETAIL_CTE_SQL = """
WITH RECURSIVE

-- 月タイトル計算用の当月購入情報
T_this_month_purchase_info_list AS (
    SELECT
        p.*,
        CASE
            WHEN p.order_type IN (101, 105)
            THEN LEAST(IFNULL(p.bv, 0), 50)
            ELSE IFNULL(p.bv, 0)
        END AS custom_bv
    FROM bonus_db.purchase_info_list AS p
    WHERE p.register_year = %s
      AND p.register_month = %s
),

-- 購入者ごとの当月BV合計
T_sum_this_month_purchase_info_list AS (
    SELECT
        jwoa_code,
        send_bv_name,
        SUM(custom_bv) AS sum_bv
    FROM T_this_month_purchase_info_list
    GROUP BY
        jwoa_code,
        send_bv_name
    HAVING SUM(custom_bv) > 0
),

-- 購入者から上位者へたどり、対象上位者から見た直下ラインを算出する
payer_tree AS (
    SELECT
        u.jmoa_code AS payer_code,
        u.send_bv_name AS payer_name,
        u.jmoa_code AS line_code,
        u.placement_code AS upper_code,
        0 AS lvl,
        pu.sum_bv
    FROM bonus_db.users AS u
    JOIN T_sum_this_month_purchase_info_list AS pu
      ON pu.jwoa_code = u.jmoa_code

    UNION ALL

    SELECT
        t.payer_code,
        t.payer_name,
        up.jmoa_code AS line_code,
        up.placement_code AS upper_code,
        t.lvl + 1 AS lvl,
        pu.sum_bv
    FROM payer_tree AS t
    JOIN bonus_db.users AS up
      ON up.jmoa_code = t.upper_code
    LEFT JOIN T_sum_this_month_purchase_info_list AS pu
      ON t.payer_code = pu.jwoa_code
    WHERE t.lvl < 5000
      AND t.upper_code IS NOT NULL
      AND t.upper_code <> ''
),

-- 対象上位者ごとの直下ラインBV合計とライン種別
introducer_total_bv AS (
    SELECT
        upper_code,
        line_code,
        SUM(sum_bv) AS sum_bv,
        CASE
            WHEN ROW_NUMBER() OVER (
                PARTITION BY upper_code
                ORDER BY SUM(sum_bv) DESC
            ) >= 3
            THEN 2
            ELSE ROW_NUMBER() OVER (
                PARTITION BY upper_code
                ORDER BY SUM(sum_bv) DESC
            )
        END AS rn
    FROM payer_tree
    GROUP BY
        upper_code,
        line_code
)
"""


MONTH_TITLE_LINE_SUMMARY_SQL = """
{cte_sql}
SELECT
    itb.upper_code AS target_jwoa_code,
    target_user.send_bv_name AS target_name,
    itb.line_code,
    line_user.send_bv_name AS line_name,
    CASE
        WHEN itb.rn = 1 THEN '収入ライン'
        ELSE '基本ライン'
    END AS line_type_label,
    itb.rn AS line_type,
    itb.sum_bv
FROM introducer_total_bv AS itb
LEFT JOIN bonus_db.users AS target_user
  ON itb.upper_code = target_user.jmoa_code
LEFT JOIN bonus_db.users AS line_user
  ON itb.line_code = line_user.jmoa_code
WHERE itb.upper_code = %s
ORDER BY
    itb.rn,
    itb.sum_bv DESC,
    itb.line_code
"""


MONTH_TITLE_PAYER_DETAIL_SQL = """
{cte_sql}
SELECT
    pt.upper_code AS target_jwoa_code,
    target_user.send_bv_name AS target_name,
    pt.line_code,
    line_user.send_bv_name AS line_name,
    CASE
        WHEN itb.rn = 1 THEN '収入ライン'
        ELSE '基本ライン'
    END AS line_type_label,
    itb.rn AS line_type,
    pt.payer_code,
    pt.payer_name,
    pt.lvl,
    pt.sum_bv
FROM payer_tree AS pt
JOIN introducer_total_bv AS itb
  ON itb.upper_code = pt.upper_code
 AND itb.line_code = pt.line_code
LEFT JOIN bonus_db.users AS target_user
  ON pt.upper_code = target_user.jmoa_code
LEFT JOIN bonus_db.users AS line_user
  ON pt.line_code = line_user.jmoa_code
WHERE pt.upper_code = %s
"""
