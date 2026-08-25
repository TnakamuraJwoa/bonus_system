THREE_STAR_DIAMOND_GLOBAL_BONUS_Q_SQL = """
WITH RECURSIVE


-- ------------------------- 前月50BV  --------------------------------
-- 前月50BV再購入情報
-- 特別対応も含む
repurchase_50over_list as (
SELECT *
FROM bonus_db.purchase_info_list
WHERE order_type IN (101, 105)
  AND register_year = %s
  AND register_month = %s
),


-- 前月50BV再購入会員
repurchase_50over_users as (
SELECT
    jwoa_code,
    send_bv_name AS jwoa_name,
    SUM(bv) AS sum_bv
FROM repurchase_50over_list
GROUP BY
    jwoa_code
HAVING
    SUM(bv) >= 50
),


-- 前月50BV再購入会員 + アクティブ設定会員
prev_month_active as (
select jwoa_code
from repurchase_50over_users

union

select jwoa_code
FROM bonus_db.active_users
WHERE year = %s AND month = %s
  AND active_status = 1
),

-- ------------------------- taitle  ----------------------------------

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


-- ------------------------- 支払い対象会員  --------------------------

-- 前月50BV以上再購入した会員
-- 当月、３スターダイヤ以上
payment_target_members AS (
    SELECT
        a.jmoa_code AS jwoa_code,
        a.send_bv_name AS jwoa_name,
        b.title_id,

        CASE
            WHEN b.title_id = 6 THEN 1
            WHEN b.title_id = 7 THEN 3
            WHEN b.title_id = 8 THEN 5
            WHEN b.title_id = 9 THEN 7
            WHEN b.title_id = 10 THEN 9
            WHEN b.title_id = 11 THEN 11
            ELSE 0
        END AS score

    FROM nexus_production.users AS a

    JOIN this_month_three_star_dia AS b
      ON a.jmoa_code = b.jwoa_code

    JOIN prev_month_active AS c
      ON a.jmoa_code = c.jwoa_code
),


-- ------------------------- 再購入超過BV総額  -------------------------
-- 再購入超過BV総額
repurchase_bv as (
    SELECT
        p.jwoa_code,
        SUM(IFNULL(p.bv, 0)) AS sum_bv,
        GREATEST(SUM(IFNULL(p.bv, 0)) - 50, 0) AS over_bv
    FROM bonus_db.purchase_info_list AS p
    WHERE p.order_type IN (101, 105)
      AND p.register_year = %s
      AND p.register_month = %s
    GROUP BY
        p.jwoa_code
),

-- 再購入超過BV
repurchase_over_bv as (
select *
from repurchase_bv
where over_bv > 0
),

-- 超過BV総額
over_total_bv AS (
    SELECT
        IFNULL(SUM(over_bv), 0) AS sum_over_bv
    FROM repurchase_over_bv
),

-- ---------------------------- total_score  --------------------------
total_score as (
select
 sum(score) as total_score
from payment_target_members
),


-- -------------------------  3スターダイヤグローバル配当結果  ---------
three_star_bonus_result as (
SELECT
    ptm.*,
    
    (
        SELECT ts.total_score
        FROM total_score AS ts
    ) AS total_score,
    
    (
        SELECT otb.sum_over_bv
        FROM over_total_bv AS otb
    ) AS total_over_bv
FROM payment_target_members AS ptm
)


SELECT
    a.jwoa_code,
    a.jwoa_name,
    a.title_id,
    a.score,
    a.total_score,
    a.total_over_bv,

    TRUNCATE(
        IFNULL(
            (a.total_over_bv * (a.score / NULLIF(a.total_score, 0))) * 0.05,
            0
        ),
        2
    ) AS bonus_amount

FROM three_star_bonus_result AS a
"""