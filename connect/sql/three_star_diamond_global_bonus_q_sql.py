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

-- 当月タイトル結果
title_result as (
select a.*
from (SELECT
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
    END AS title_id,

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
FROM line_type_total_bv2) as a
where score > 0
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