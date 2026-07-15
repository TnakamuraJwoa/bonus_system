CROWN_DIAMOND_GLOBAL_BONUS_Y_SQL = """
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

-- 当月、クラウンダイヤ大使以上
this_month_crown_dia as (
select *
from title_result
where title_id >= 10
),


-- ------------------------- 支払い対象会員  --------------------------

-- 前月50BV以上再購入した会員
-- 当月、クラウンダイヤ大使以上
payment_target_members AS (
    SELECT
        a.jmoa_code AS jwoa_code,
        a.send_bv_name AS jwoa_name,
        b.title_id,

        CASE
            WHEN b.title_id = 10 THEN 1
            WHEN b.title_id = 11 THEN 2
            ELSE 0
        END AS score

    FROM bonus_db.users AS a

    JOIN this_month_crown_dia AS b
      ON a.jmoa_code = b.jwoa_code

    JOIN prev_month_active AS c
      ON a.jmoa_code = c.jwoa_code
),


-- ------------------------- 売上総額  -------------------------
-- 売上総額BV
order_all_bv as (
    SELECT
        SUM(IFNULL(p.bv, 0)) AS sum_bv
    FROM bonus_db.purchase_info_list AS p
    WHERE p.order_type
      AND p.register_year = %s
      AND p.register_month = %s
),



-- ---------------------------- total_score  --------------------------
total_score as (
select
 sum(score) as total_score
from payment_target_members
),


-- -------------------------  グローバル配当結果  ---------
global_bonus_result as (
SELECT
    ptm.*,

    (
        SELECT ts.total_score
        FROM total_score AS ts
    ) AS total_score,

    (
        SELECT otb.sum_bv
        FROM order_all_bv AS otb
    ) AS sum_bv
FROM payment_target_members AS ptm
)


SELECT
    a.jwoa_code,
    a.jwoa_name,
    a.title_id,
    a.score,
    a.total_score,
    a.sum_bv as total_bv,

    TRUNCATE(
        IFNULL(
            (a.sum_bv * (a.score / NULLIF(a.total_score, 0))) * 0.01,
            0
        ),
        2
    ) AS bonus_amount

FROM global_bonus_result AS a
"""
