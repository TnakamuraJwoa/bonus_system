TITLE_BONUS_DETAIL_CTE_SQL = """
WITH RECURSIVE

-- タイトルボーナス対象売上 x
-- 初回購入BV + ランクアップ購入BV + 再購入・特別対応（合算して上限50BV）
title_bonus_target_purchase_list as (
SELECT
    p.jwoa_code,
    (
        LEAST(
            SUM(
                CASE
                    WHEN p.order_type IN (101, 105)
                    THEN IFNULL(p.bv, 0)
                    ELSE 0
                END
            ),
            50
        )
        + SUM(
            CASE
                WHEN p.order_type IN (102, 103)
                THEN IFNULL(p.bv, 0)
                ELSE 0
            END
        )
    ) AS sum_bv
FROM bonus_db.purchase_info_list AS p
WHERE p.order_type IN (101, 102, 103, 105)
  AND p.register_year = %s
  AND p.register_month = %s
GROUP BY
    p.jwoa_code
HAVING (
        LEAST(
            SUM(
                CASE
                    WHEN p.order_type IN (101, 105)
                    THEN IFNULL(p.bv, 0)
                    ELSE 0
                END
            ),
            50
        )
        + SUM(
            CASE
                WHEN p.order_type IN (102, 103)
                THEN IFNULL(p.bv, 0)
                ELSE 0
            END
        )
    ) > 0
),

-- タイトル結果（月タイトル登録済みデータを参照）
title_result as (
SELECT
    jwoa_code,
    jwoa_name,
    income_line_bv,
    basic_line_bv,
    title_id
FROM bonus_db.month_title
WHERE kibetu = %s
),

-- 当月、３スターダイヤ以上
this_month_three_star_dia as (
select *
from title_result
where title_id >= 6
),

-- 当月アクティブ会員
this_month_active_users as (
SELECT
    id,
    jwoa_code,
    year,
    month,
    created_at
FROM bonus_db.active_users
WHERE year = %s AND month = %s
  AND active_status = 1
),

-- 前月アクティブ会員
prev_month_active_users as (
SELECT
    id,
    jwoa_code,
    year,
    month,
    created_at
FROM bonus_db.active_users
WHERE year = %s AND month = %s
  AND active_status = 1
),

-- 当月購入リスト
-- 再購入 + ランクアップ + 特別対応
this_month_purchase_list AS (
    SELECT
        register_year,
        register_month,
        jwoa_code,
        SUM(IFNULL(bv, 0)) AS sum_bv
    FROM bonus_db.purchase_info_list AS p
    WHERE order_type IN (101, 103, 105)
      AND register_year = %s
      AND register_month = %s
    GROUP BY
     register_year,
     register_month,
     jwoa_code
    HAVING SUM(IFNULL(bv, 0)) >= 50
),

-- 前月購入リスト
-- 再購入 + ランクアップ + 特別対応
prev_month_purchase_list AS (
    SELECT
        register_year,
        register_month,
        jwoa_code,
        SUM(IFNULL(bv, 0)) AS sum_bv
    FROM bonus_db.purchase_info_list AS p
    WHERE order_type IN (101, 103, 105)
      AND register_year = %s
      AND register_month = %s
    GROUP BY
     register_year,
     register_month,
     jwoa_code
    HAVING SUM(IFNULL(bv, 0)) >= 50
),

-- 当月初回購入
this_month_syokai_list AS (
    SELECT
        register_year,
        register_month,
        jwoa_code,
        SUM(IFNULL(bv, 0)) AS sum_bv
    FROM bonus_db.purchase_info_list AS p
    WHERE order_type = 102
      AND register_year = %s
      AND register_month = %s
    GROUP BY
     register_year,
     register_month,
     jwoa_code
    HAVING SUM(IFNULL(bv, 0)) >= 50
),

-- 前月、当月、アクティブ
purchase_active as (
-- 再購入 + ランクアップ + 特別対応
SELECT a.jwoa_code
FROM this_month_purchase_list AS a
JOIN prev_month_purchase_list AS b
  ON a.jwoa_code = b.jwoa_code

UNION

-- 初回
SELECT jwoa_code
FROM this_month_syokai_list

UNION

-- アクティブ
SELECT a.jwoa_code
FROM this_month_active_users  AS a
JOIN prev_month_active_users  AS b
  ON a.jwoa_code = b.jwoa_code
),

-- ３スターダイヤ以上でアクティブ
active_three_star_dia as (
SELECT a.*
FROM this_month_three_star_dia AS a
JOIN purchase_active  AS b
  ON a.jwoa_code = b.jwoa_code
),

-- ３スターダイヤ以上でアクティブ + 直下傘下組織
active_three_star_dia_with_placement as (
    SELECT
        ats.jwoa_code AS root_jmoa_code,
        ats.jwoa_name AS root_name,
        u.jmoa_code AS line_jwoa_code,
        u.send_bv_name AS line_name,
        u.jmoa_code AS down_jwoa_code,
        u.send_bv_name AS down_name,
        1 AS tree_level
    FROM active_three_star_dia AS ats
    JOIN bonus_db.users AS u
      ON u.placement_code = ats.jwoa_code
),

-- 直下傘下組織の全員を上位者ツリーでたどる
placement_line_tree AS (
    SELECT
        root_jmoa_code,
        root_name,
        line_jwoa_code,
        line_name,
        down_jwoa_code,
        down_name,
        tree_level
    FROM active_three_star_dia_with_placement

    UNION ALL

    SELECT
        t.root_jmoa_code,
        t.root_name,
        t.line_jwoa_code,
        t.line_name,
        u.jmoa_code AS down_jwoa_code,
        u.send_bv_name AS down_name,
        t.tree_level + 1 AS tree_level
    FROM placement_line_tree AS t
    JOIN bonus_db.users AS u
      ON u.placement_code = t.down_jwoa_code
    WHERE t.tree_level < 10000
),

-- 直下傘下組織ごとのタイトルボーナス対象売上 x
placement_line_sales AS (
    SELECT
        t.root_jmoa_code,
        t.line_jwoa_code,
        SUM(IFNULL(p.sum_bv, 0)) AS sum_bv
    FROM placement_line_tree AS t
    LEFT JOIN title_bonus_target_purchase_list AS p
      ON t.down_jwoa_code = p.jwoa_code
    GROUP BY
        t.root_jmoa_code,
        t.line_jwoa_code
),

-- active_three_star_dia_with_placement を起点に上位者ツリーで下を見る
placement_down_tree AS (

    -- 1階層目：直下傘下組織
    SELECT
        a.root_jmoa_code,
        a.root_name,
        a.line_jwoa_code,
        a.line_name,
        a.root_jmoa_code AS up_jwoa_code,
        a.down_jwoa_code,
        a.down_name,
        a.tree_level,

        CASE
            WHEN ats.jwoa_code IS NOT NULL THEN 1
            ELSE 0
        END AS match_level,

        CASE
            WHEN ats.jwoa_code IS NOT NULL THEN 1
            ELSE 0
        END AS matched_flg

    FROM active_three_star_dia_with_placement AS a
    LEFT JOIN active_three_star_dia AS ats
      ON ats.jwoa_code = a.down_jwoa_code

    UNION ALL

    -- 2階層目以降：下は全員見る。一致したら match_level を +1
    SELECT
        t.root_jmoa_code,
        t.root_name,
        t.line_jwoa_code,
        t.line_name,
        t.down_jwoa_code AS up_jwoa_code,
        u.jmoa_code AS down_jwoa_code,
        u.send_bv_name AS down_name,
        t.tree_level + 1 AS tree_level,

        t.match_level +
        CASE
            WHEN ats.jwoa_code IS NOT NULL THEN 1
            ELSE 0
        END AS match_level,

        CASE
            WHEN ats.jwoa_code IS NOT NULL THEN 1
            ELSE 0
        END AS matched_flg

    FROM placement_down_tree AS t

    JOIN bonus_db.users AS u
      ON u.placement_code = t.down_jwoa_code

    LEFT JOIN active_three_star_dia AS ats
      ON ats.jwoa_code = u.jmoa_code

    WHERE t.tree_level < 10000
      AND t.match_level < 6
),

-- マッチングレベル
match_level AS (
SELECT
    root_jmoa_code,
    root_name,
    line_jwoa_code,
    line_name,
    up_jwoa_code,
    down_jwoa_code,
    down_name,
    tree_level,
    match_level,
    matched_flg
FROM placement_down_tree
WHERE matched_flg = 1
),

-- マッチングレベル + bv
match_level_add_bv as (
SELECT
    a.root_jmoa_code as root_jmoa_code,
    a.root_name,
    a.line_jwoa_code,
    a.line_name,
    a.up_jwoa_code,
    a.down_jwoa_code,
    a.down_name,
    a.tree_level,
    a.match_level,
    b.sum_bv,
    c.title_id,

    CASE
        WHEN c.title_id = 6 AND a.match_level <= 1
        THEN 0.02

        WHEN c.title_id = 7 AND a.match_level <= 2
        THEN 0.02

        WHEN c.title_id = 8 AND a.match_level <= 3
        THEN 0.02

        WHEN c.title_id = 9 AND a.match_level <= 3
        THEN 0.02

        WHEN c.title_id = 9 AND a.match_level = 4
        THEN 0.01

        WHEN c.title_id IN (10, 11) AND a.match_level <= 3
        THEN 0.02

        WHEN c.title_id IN (10, 11) AND a.match_level IN (4, 5)
        THEN 0.01

        ELSE 0
    END AS rate,

    CASE
        WHEN c.title_id = 6 AND a.match_level <= 1
        THEN b.sum_bv * 0.02

        WHEN c.title_id = 7 AND a.match_level <= 2
        THEN b.sum_bv * 0.02

        WHEN c.title_id = 8 AND a.match_level <= 3
        THEN b.sum_bv * 0.02

        WHEN c.title_id = 9 AND a.match_level <= 3
        THEN b.sum_bv * 0.02

        WHEN c.title_id = 9 AND a.match_level = 4
        THEN b.sum_bv * 0.01

        WHEN c.title_id IN (10, 11) AND a.match_level <= 3
        THEN b.sum_bv * 0.02

        WHEN c.title_id IN (10, 11) AND a.match_level IN (4, 5)
        THEN b.sum_bv * 0.01

        ELSE 0
    END AS bonus_amount

FROM match_level AS a

LEFT JOIN placement_line_sales AS b
  ON a.root_jmoa_code = b.root_jmoa_code
 AND a.line_jwoa_code = b.line_jwoa_code

LEFT JOIN title_result AS c
  ON a.root_jmoa_code = c.jwoa_code

WHERE a.matched_flg = 1
)
"""


TITLE_BONUS_DETAIL_SELECT_SQL = """
SELECT
    m.root_jmoa_code AS root_jwoa_code,
    m.root_name,
    m.line_jwoa_code,
    m.line_name,
    m.up_jwoa_code,
    m.down_jwoa_code,
    m.down_name,
    m.tree_level,
    m.match_level,
    m.sum_bv,
    m.title_id,
    COALESCE(tm.title_name, 'タイトルなし') AS title_name,
    m.rate,
    m.bonus_amount
FROM match_level_add_bv AS m
LEFT JOIN bonus_db.title_master AS tm
  ON m.title_id = tm.title_id
WHERE m.bonus_amount > 0
"""


TITLE_BONUS_PURCHASE_PLACEMENT_TEAM_CTE_SQL = """
WITH RECURSIVE purchase_team AS (
    SELECT
        root.jmoa_code AS root_jwoa_code,
        root.send_bv_name AS root_name,
        root.jmoa_code AS line_jwoa_code,
        root.send_bv_name AS line_name,
        root.jmoa_code AS down_jwoa_code,
        root.send_bv_name AS down_name,
        0 AS tree_level,
        CAST(root.jmoa_code AS CHAR(20000)) AS path_codes
    FROM bonus_db.users AS root
    WHERE root.jmoa_code = %s

    UNION ALL

    SELECT
        t.root_jwoa_code,
        t.root_name,
        CASE WHEN t.tree_level = 0 THEN u.jmoa_code ELSE t.line_jwoa_code END AS line_jwoa_code,
        CASE WHEN t.tree_level = 0 THEN u.send_bv_name ELSE t.line_name END AS line_name,
        u.jmoa_code AS down_jwoa_code,
        u.send_bv_name AS down_name,
        t.tree_level + 1 AS tree_level,
        CONCAT(t.path_codes, ',', u.jmoa_code) AS path_codes
    FROM purchase_team AS t
    JOIN bonus_db.users AS u
      ON u.placement_code = t.down_jwoa_code
    WHERE t.tree_level < 10000
      AND FIND_IN_SET(u.jmoa_code, t.path_codes) = 0
)
"""


TITLE_BONUS_PURCHASE_INTRODUCER_TEAM_CTE_SQL = """
WITH RECURSIVE purchase_team AS (
    SELECT
        root.jmoa_code AS root_jwoa_code,
        root.send_bv_name AS root_name,
        root.jmoa_code AS line_jwoa_code,
        root.send_bv_name AS line_name,
        root.jmoa_code AS down_jwoa_code,
        root.send_bv_name AS down_name,
        0 AS tree_level,
        CAST(root.jmoa_code AS CHAR(20000)) AS path_codes
    FROM bonus_db.users AS root
    WHERE root.jmoa_code = %s

    UNION ALL

    SELECT
        t.root_jwoa_code,
        t.root_name,
        CASE WHEN t.tree_level = 0 THEN u.jmoa_code ELSE t.line_jwoa_code END AS line_jwoa_code,
        CASE WHEN t.tree_level = 0 THEN u.send_bv_name ELSE t.line_name END AS line_name,
        u.jmoa_code AS down_jwoa_code,
        u.send_bv_name AS down_name,
        t.tree_level + 1 AS tree_level,
        CONCAT(t.path_codes, ',', u.jmoa_code) AS path_codes
    FROM purchase_team AS t
    JOIN bonus_db.users AS u
      ON u.introducer_code = t.down_jwoa_code
    WHERE t.tree_level < 10000
      AND FIND_IN_SET(u.jmoa_code, t.path_codes) = 0
)
"""


TITLE_BONUS_PURCHASE_DETAIL_SELECT_SQL = """
SELECT
    t.root_jwoa_code,
    t.root_name,
    t.line_jwoa_code,
    t.line_name,
    t.down_jwoa_code,
    t.down_name,
    t.tree_level,
    mt.title_id,
    COALESCE(tm.title_name, 'タイトルなし') AS title_name,
    p.id,
    p.order_code,
    p.order_type,
    CASE p.order_type
        WHEN 101 THEN '再購入品'
        WHEN 102 THEN '初回購入品'
        WHEN 103 THEN 'ランクアップ購入品'
        WHEN 105 THEN '特別対応購入品'
        ELSE '対象外'
    END AS order_type_name,
    p.bv AS original_bv,
    CASE
        WHEN p.order_type IN (101, 105)
        THEN LEAST(IFNULL(p.bv, 0), 50)
        WHEN p.order_type IN (102, 103)
        THEN IFNULL(p.bv, 0)
        ELSE 0
    END AS bv_max50,
    p.bonus_payment_date,
    p.register_year,
    p.register_month,
    p.order_year,
    p.order_month
FROM purchase_team AS t
JOIN bonus_db.purchase_info_list AS p
  ON p.jwoa_code = t.down_jwoa_code
 AND p.order_type IN (101, 102, 103, 105)
 AND p.register_year = %s
 AND p.register_month = %s
LEFT JOIN bonus_db.month_title AS mt
  ON mt.kibetu = %s
 AND mt.jwoa_code = t.down_jwoa_code
LEFT JOIN bonus_db.title_master AS tm
  ON tm.title_id = mt.title_id
WHERE
    CASE
        WHEN p.order_type IN (101, 105)
        THEN LEAST(IFNULL(p.bv, 0), 50)
        WHEN p.order_type IN (102, 103)
        THEN IFNULL(p.bv, 0)
        ELSE 0
    END > 0
"""
