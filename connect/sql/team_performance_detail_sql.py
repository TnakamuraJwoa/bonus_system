_PURCHASE_MONTH_FILTER = """
WHERE p.register_year = %s
  AND p.register_month = %s
"""


WEEK_TEAM_PERFORMANCE_DETAIL_SQL = """
WITH RECURSIVE

-- (title 当月購入情報)
T_this_month_purchase_info_list AS (
SELECT
    p.*,

    CASE
        WHEN p.order_type IN (101, 105)
        THEN LEAST(IFNULL(p.bv, 0), 50)

        ELSE IFNULL(p.bv, 0)
    END AS custom_bv

FROM bonus_db.purchase_info_list AS p
WHERE p.bonus_payment_date >= %s
  AND p.bonus_payment_date <= %s
),

-- (title 当月購入情報)合計
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

-- line_codeは購入者 ⇒ 上位者(ラインコード) ⇒ その上位者(上位者コード)
-- 支払い者のtree
payer_tree AS (

    -- 起点 = 支払い者本人
    SELECT
        u.jmoa_code AS purchaser_code,
        u.send_bv_name AS purchaser_name,
        u.jmoa_code AS line_code,
        u.placement_code AS upper_code,
        0 AS lvl,
        pu.sum_bv
    FROM nexus_production.users AS u
    JOIN T_sum_this_month_purchase_info_list AS pu
      ON pu.jwoa_code = u.jmoa_code

    UNION ALL

    -- 上にさかのぼる
    SELECT
        t.purchaser_code,
        t.purchaser_name,
        up.jmoa_code AS line_code,
        up.placement_code AS upper_code,
        t.lvl + 1 AS lvl,
        pu.sum_bv
    FROM payer_tree AS t
    JOIN nexus_production.users AS up
      ON up.jmoa_code = t.upper_code
    LEFT JOIN T_sum_this_month_purchase_info_list AS pu
      ON t.purchaser_code = pu.jwoa_code
    WHERE t.lvl < 5000
      AND t.upper_code IS NOT NULL
      AND t.upper_code <> ''
)

SELECT
    upper_code,
    line_code,
    purchaser_code,
    purchaser_name,
    lvl,
    sum_bv
FROM payer_tree
"""


def _build_team_performance_detail_sql(purchase_filter):
    return f"""
WITH RECURSIVE

-- (title 当月購入情報)
T_this_month_purchase_info_list AS (
SELECT
    p.*,

    CASE
        WHEN p.order_type IN (101, 105)
        THEN LEAST(IFNULL(p.bv, 0), 50)

        ELSE IFNULL(p.bv, 0)
    END AS custom_bv

FROM bonus_db.purchase_info_list AS p
{purchase_filter}
),

-- (title 当月購入情報)合計
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

-- line_codeは購入者 ⇒ 上位者(ラインコード) ⇒ その上位者(上位者コード)
-- 支払い者のtree
payer_tree AS (

    -- 起点 = 支払い者本人
    SELECT
        u.jmoa_code AS purchaser_code,
        u.send_bv_name AS purchaser_name,
        u.jmoa_code AS line_code,
        u.placement_code AS upper_code,
        0 AS lvl,
        pu.sum_bv
    FROM nexus_production.users AS u
    JOIN T_sum_this_month_purchase_info_list AS pu
      ON pu.jwoa_code = u.jmoa_code

    UNION ALL

    -- 上にさかのぼる
    SELECT
        t.purchaser_code,
        t.purchaser_name,
        up.jmoa_code AS line_code,
        up.placement_code AS upper_code,
        t.lvl + 1 AS lvl,
        pu.sum_bv
    FROM payer_tree AS t
    JOIN nexus_production.users AS up
      ON up.jmoa_code = t.upper_code
    LEFT JOIN T_sum_this_month_purchase_info_list AS pu
      ON t.purchaser_code = pu.jwoa_code
    WHERE t.lvl < 5000
      AND t.upper_code IS NOT NULL
      AND t.upper_code <> ''
)

SELECT
    upper_code,
    line_code,
    purchaser_code,
    purchaser_name,
    lvl,
    sum_bv
FROM payer_tree
"""


MONTH_TEAM_PERFORMANCE_DETAIL_SQL = _build_team_performance_detail_sql(_PURCHASE_MONTH_FILTER)
