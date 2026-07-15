TITLE_BONUS_SQL = """

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

-- -----------------------------------------------------------

-- 当月、３スターダイヤ以上
this_month_three_star_dia as (
select *
from title_result
where title_id >= 6
),


-- 当月アクティブ設定会員
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


-- 前月アクティブ設定会員
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

-- 紹介者tree
placement_tree AS (
    -- 1階層目
    SELECT
        a.jwoa_code AS root_jmoa_code,
        a.jwoa_name AS root_name,
        a.jwoa_code AS up_jwoa_code,
        a.jwoa_name AS up_name,
        u.jmoa_code AS down_jwoa_code,
        u.send_bv_name AS down_name,

        CASE
            WHEN EXISTS (
                SELECT 1
                FROM active_three_star_dia AS ats
                WHERE ats.jwoa_code = u.jmoa_code
            )
            THEN 1
            ELSE 0
        END AS down_star_dia_flg,
        
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM active_three_star_dia AS ats
                WHERE ats.jwoa_code = u.jmoa_code
            )
            THEN 1
            ELSE 0
        END AS down_match_level,

        1 AS tree_level

    FROM active_three_star_dia AS a

    JOIN bonus_db.users AS u
      ON a.jwoa_code = u.introducer_code

    UNION ALL

    -- 2階層目以降
    SELECT
        a.root_jmoa_code,
        a.root_name,
        a.down_jwoa_code AS up_jwoa_code,
        a.down_name AS up_name,
        u.jmoa_code AS down_jwoa_code,
        u.send_bv_name AS down_name,

        CASE
            WHEN EXISTS (
                SELECT 1
                FROM active_three_star_dia AS ats
                WHERE ats.jwoa_code = u.jmoa_code
            )
            THEN 1
            ELSE 0
        END AS down_star_dia_flg,
        
        
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM active_three_star_dia AS ats
                WHERE ats.jwoa_code = u.jmoa_code
            )
            THEN a.down_match_level + 1
            ELSE a.down_match_level
        END AS down_match_level,

        a.tree_level + 1 AS tree_level

    FROM placement_tree AS a

    JOIN bonus_db.users AS u
      ON a.down_jwoa_code = u.introducer_code
),

-- treeの絞込
-- 傘下に3スター達成してる
down_star_dia AS (
    SELECT 
     t.title_id as root_title_id,
     a.*
     
    FROM placement_tree as a
    
    left join title_result as t
    on a.root_jmoa_code = t.jwoa_code
    
    WHERE down_star_dia_flg = 1
    ORDER BY root_jmoa_code, down_match_level
),

-- - - - - - - - - - -傘下のBVの合計 - - - - - - - - - - - -

-- downの会員
down_users as (
select
 down_jwoa_code,
 down_name
from down_star_dia
group by down_jwoa_code, down_name
),

-- 傘下のBV
down_users_bv as (

select 
 a.down_jwoa_code as root_jwoa_code,
 a.down_name as root_name,
 a.down_jwoa_code as up_jwoa_code,
 a.down_name as up_name,
 a.down_jwoa_code as down_code,
 a.down_name as down_name,
 1 as level,
 b.sum_bv as bv
from down_users as a

left join title_bonus_target_purchase_list as b
on a.down_jwoa_code = b.jwoa_code

union all

select
 a.root_jwoa_code,
 a.root_name,
 a.down_code as up_jwoa_code,
 a.down_name as up_name,
 u.jmoa_code as down_code,
 u.send_bv_name as down_name,
 a.level + 1 as level,
 IFNULL(b.sum_bv, 0) as bv
from down_users_bv as a

JOIN bonus_db.users AS u
on a.down_code = u.introducer_code

left join title_bonus_target_purchase_list as b
on u.jmoa_code = b.jwoa_code

),

-- 傘下のBVの合計
sum_down_users_bv as (
select
 root_jwoa_code,
 sum(bv) as sum_bv
from down_users_bv
group by root_jwoa_code
),


-- - - - - - - - - - -↑傘下のBVの合計 - - - - - - - - - - - -
-- title_result
title_bonus_result as (
SELECT
 a.*,
 b.sum_bv
FROM down_star_dia as a

left join sum_down_users_bv as b
on a.down_jwoa_code = b.root_jwoa_code

),


title_bonus_result1 as (
select
 root_jmoa_code,
 root_name,
 up_jwoa_code,
 down_jwoa_code,
 down_name,
 tree_level,
 down_match_level as match_level,
 root_title_id as title_id,
 sum_bv,
 
    CASE
        WHEN root_title_id = 6 AND down_match_level <= 1
        THEN 0.02

        WHEN root_title_id = 7 AND down_match_level <= 2
        THEN 0.02

        WHEN root_title_id = 8 AND down_match_level <= 3
        THEN 0.02

        WHEN root_title_id = 9 AND down_match_level <= 3
        THEN 0.02

        WHEN root_title_id = 9 AND down_match_level = 4
        THEN 0.01

        WHEN root_title_id IN (10, 11) AND down_match_level <= 3
        THEN 0.02

        WHEN root_title_id IN (10, 11) AND down_match_level IN (4, 5)
        THEN 0.01

        ELSE 0
    END AS rate,
    
    CASE
        WHEN root_title_id = 6 AND down_match_level <= 1
        THEN sum_bv * 0.02

        WHEN root_title_id = 7 AND down_match_level <= 2
        THEN sum_bv * 0.02

        WHEN root_title_id = 8 AND down_match_level <= 3
        THEN sum_bv * 0.02

        WHEN root_title_id = 9 AND down_match_level <= 3
        THEN sum_bv * 0.02

        WHEN root_title_id = 9 AND down_match_level = 4
        THEN sum_bv * 0.01

        WHEN root_title_id IN (10, 11) AND down_match_level <= 3
        THEN sum_bv * 0.02

        WHEN root_title_id IN (10, 11) AND down_match_level IN (4, 5)
        THEN sum_bv * 0.01

        ELSE 0
    END AS bonus_amount

from title_bonus_result
order by root_jmoa_code, match_level
)

SELECT
    tbr.root_jmoa_code,
    tbr.root_name,
    tbr.up_jwoa_code,
    tbr.down_jwoa_code,
    tbr.down_name,
    tbr.tree_level,
    tbr.match_level,
    tbr.sum_bv,
    tbr.title_id,
    COALESCE(tm.title_name, 'タイトルなし') AS title_name,
    tbr.rate,
    tbr.bonus_amount
FROM title_bonus_result1 AS tbr
LEFT JOIN bonus_db.title_master AS tm
  ON tbr.title_id = tm.title_id
WHERE tbr.bonus_amount > 0
ORDER BY tbr.root_jmoa_code, tbr.match_level

"""