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


-- ------------------------- taitle  ----------------------------------

-- タイトル結果（月タイトル登録済みデータを参照）
title_result as (
SELECT
    a.*
FROM (
    SELECT
        jwoa_code,
        jwoa_name,
        income_line_bv,
        basic_line_bv,
        title_id,
        CASE
            WHEN income_line_bv >= 562500
             AND basic_line_bv >= 562500
            THEN 11

            WHEN income_line_bv >= 375000
             AND basic_line_bv >= 375000
            THEN 9

            WHEN income_line_bv >= 250000
             AND basic_line_bv >= 250000
            THEN 7

            WHEN income_line_bv >= 125000
             AND basic_line_bv >= 125000
            THEN 5

            WHEN income_line_bv >= 62500
             AND basic_line_bv >= 62500
            THEN 3

            WHEN income_line_bv >= 31250
             AND basic_line_bv >= 31250
            THEN 1

            ELSE 0
        END AS score
    FROM bonus_db.month_title
    WHERE kibetu = %s
) AS a
WHERE a.score > 0
),


-- ------------------------- 支払い対象会員  --------------------------

payment_target_members as (
SELECT
 a.jmoa_code as jwoa_code,
 a.send_bv_name as jwoa_name,
 b.title_id,
 b.score
FROM bonus_db.users AS a

JOIN title_result AS b
  ON a.jmoa_code = b.jwoa_code

JOIN repurchase_50over_users AS c
  ON a.jmoa_code = c.jwoa_code
),



-- ---------------------------- total_score  --------------------------
total_score as (
select
 sum(score) as total_score
from payment_target_members
group by jwoa_code
),


-- ------------------------- 再購入超過BV総額  -------------------------
-- 再購入超過BV総額
-- 総点数
-- 一点に対するボーナス
repurchase_over_total_bv AS (
    SELECT
        2000 AS total_over_bv,
        (SELECT total_score FROM total_score) AS total_score,
        TRUNCATE(
            (2000 * 0.05) / (SELECT total_score FROM total_score),
            2
        ) AS one_score_bonus

),

-- -------------------------  3スターダイヤグローバル配当結果  -------------------------

three_star_global_bonus_result as (
select
 *,
 (SELECT total_over_bv FROM repurchase_over_total_bv) as total_over_bv,
 (SELECT one_score_bonus FROM repurchase_over_total_bv) as one_score_bonus,
 score * (SELECT one_score_bonus FROM repurchase_over_total_bv) as bonus_amount
from payment_target_members
)



select * from three_star_global_bonus_result
"""