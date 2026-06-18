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

-- -----------------------------------------------------------

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
where bonus_amount > 0
order by root_jmoa_code, tree_level, match_level

"""