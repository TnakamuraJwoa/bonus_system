TITLE_BONUS_SQL = """
WITH RECURSIVE

-- (taitle 当月購入情報)
T_this_month_purchase_info_list as (
SELECT
    p.*,

    CASE
        WHEN p.order_type = 101
        THEN LEAST(IFNULL(p.bv, 0), 50)

        ELSE IFNULL(p.bv, 0)
    END AS custom_bv

FROM bonus_db.purchase_info_list AS p
WHERE p.register_year = %s
  AND p.register_month = %s
),

-- (taitle 当月購入情報)合計
T_sum_this_month_purchase_info_list as (
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

-- line_codeは購入者　⇒上位者(ラインコード) ⇒　その上位者(上位者こーど)
-- 支払い者のtree
payer_tree AS (

    -- ① 起点 = 支払い者本人
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

    -- ② 上にさかのぼる
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
    left join T_sum_this_month_purchase_info_list as pu
      ON t.payer_code = pu.jwoa_code
    WHERE t.lvl < 5000
      AND t.upper_code IS NOT NULL
      AND t.upper_code <> ''
),

-- 紹介者ごとの合計BV
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

    ORDER BY
        upper_code,
        rn
),

-- 収入ライン or 基本ラインごとの合計
line_type_total_bv AS (
    SELECT
        upper_code,
        rn,
        SUM(sum_bv) AS sum_bv

    FROM introducer_total_bv

    GROUP BY
        upper_code,
        rn
),

-- 収入ライン or 基本ラインごとの合計2
line_type_total_bv2 AS (
    SELECT
        upper_code,
        send_bv_name,
        IFNULL(MAX(CASE WHEN rn = 1 THEN sum_bv END),0) AS income_line_bv,
        IFNULL(MAX(CASE WHEN rn = 2 THEN sum_bv END),0) AS basic_line_bv

    FROM line_type_total_bv as a
    left join bonus_db.users as b
    on a.upper_code = b.jmoa_code

    GROUP BY
        upper_code
),

-- タイトル結果
title_result as (
SELECT
    upper_code as jwoa_code,
    send_bv_name as jwoa_name,
    income_line_bv,
    basic_line_bv,
    CASE
        WHEN income_line_bv >= 562500
         AND basic_line_bv >= 562500
        THEN 11

        WHEN income_line_bv >= 375000
         AND basic_line_bv >= 375000
        THEN 10

        WHEN income_line_bv >= 250000
         AND basic_line_bv >= 250000
        THEN 9

        WHEN income_line_bv >= 125000
         AND basic_line_bv >= 125000
        THEN 8

        WHEN income_line_bv >= 62500
         AND basic_line_bv >= 62500
        THEN 7

        WHEN income_line_bv >= 31250
         AND basic_line_bv >= 31250
        THEN 6

        WHEN income_line_bv >= 15000
         AND basic_line_bv >= 15000
        THEN 5

        WHEN income_line_bv >= 7500
         AND basic_line_bv >= 7500
        THEN 4

        WHEN income_line_bv >= 2500
         AND basic_line_bv >= 2500
        THEN 3

        WHEN income_line_bv >= 1250
         AND basic_line_bv >= 1250
        THEN 2

        WHEN income_line_bv >= 750
         AND basic_line_bv >= 750
        THEN 1

        ELSE 0
    END AS title_id
FROM line_type_total_bv2
),

-- -----------------------------------------------------------

-- 当月、３スターダイヤ以上
this_month_three_star_dia as (
select *
from title_result
where title_id >= 1
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

-- ３スターダイヤ以上でアクティブ + 紹介者
active_three_star_dia_with_intro as (
    SELECT
        ats.jwoa_code AS root_jmoa_code,
        ats.jwoa_name AS root_name,
        u.introducer_code,
        u.jmoa_code AS down_jwoa_code,
        u.send_bv_name AS down_name,
        1 AS tree_level
    FROM active_three_star_dia AS ats
    JOIN bonus_db.users AS u
      ON u.introducer_code = ats.jwoa_code
),

-- active_three_star_dia_with_intro を起点に上位者で下を見る
introducer_down_tree AS (

    -- 1階層目：直紹介
    SELECT
        root_jmoa_code,
        root_name,
        introducer_code AS up_jwoa_code,
        down_jwoa_code,
        down_name,
        tree_level,

        0 AS match_level,
        0 AS matched_flg

    FROM active_three_star_dia_with_intro

    UNION ALL

    -- 2階層目以降：下は全員見る。一致したら match_level を +1
    SELECT
        t.root_jmoa_code,
        t.root_name,
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

    FROM introducer_down_tree AS t

    JOIN bonus_db.users AS u
      ON u.introducer_code = t.down_jwoa_code

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
    up_jwoa_code,
    down_jwoa_code,
    down_name,
    tree_level,
    match_level,
    matched_flg
FROM introducer_down_tree
WHERE
    tree_level = 1
    OR
    (
        tree_level >= 2
        AND matched_flg = 1
    )
ORDER BY
    root_jmoa_code,
    match_level,
    tree_level,
    down_jwoa_code
),


-- マッチングレベル + bv
match_level_add_bv as (
SELECT
    a.root_jmoa_code as root_jmoa_code,
    a.root_name,
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

LEFT JOIN T_sum_this_month_purchase_info_list AS b
  ON a.down_jwoa_code = b.jwoa_code

LEFT JOIN title_result AS c
  ON a.root_jmoa_code = c.jwoa_code

  where a.matched_flg = 1
)


select * from match_level_add_bv
order by root_jmoa_code, tree_level, match_level
"""