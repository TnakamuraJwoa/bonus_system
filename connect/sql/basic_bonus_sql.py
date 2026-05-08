BASIC_BONUS_SQL = """
WITH RECURSIVE

-- アクティブ会員
is_active_users as (
select *, 50 as bv
from bonus_db.active_users
where year = %s and month = %s
),

-- 前週の期別
prev_kibetu AS (
    SELECT prev_kibetu
    FROM (
        SELECT
            kibetu,
            LAG(kibetu) OVER (ORDER BY st_date) AS prev_kibetu
        FROM bonus_db.period_master
    ) t
    WHERE kibetu = %s
),

-- 前週のベーシック繰り越しBV
prev_week_basic_carry_over_bv AS (
    SELECT
        kibetu,
        placement_code,
        jmoa_code AS jwoa_code,
        carry_over_bv
    FROM bonus_db.basic_bv_line
    WHERE kibetu = (
        SELECT prev_kibetu
        FROM prev_kibetu
    )
),


-- group_by(購入者リスト)
-- 前月の購入情報（active_users含む)
sum_prev_purchasers_list AS (
    SELECT
        x.jwoa_code,
        SUM(IFNULL(x.bv, 0)) AS bv
    FROM (
        -- 前月の購入情報
        SELECT
            p.jwoa_code,
            p.bv
        FROM bonus_db.purchase_info_list p
        WHERE p.bonus_payment_date >= %s
          AND p.bonus_payment_date <  %s

        UNION ALL

        -- アクティブ会員分を追加
        SELECT
            iau.jwoa_code,
            iau.bv
        FROM is_active_users iau
    ) x
    GROUP BY x.jwoa_code
    HAVING SUM(IFNULL(x.bv, 0)) >= 50
),


-- 再購入リスト
repurchase_list AS (
    SELECT
        order_code,
        jwoa_code,
        bonus_payment_date,
        order_type,
        bv,
        LEAST(IFNULL(bv, 0), 50) AS custom_bv
    FROM bonus_db.purchase_info_list AS p
    WHERE order_type IN (101, 105)
      AND bonus_payment_date >= %s
      AND bonus_payment_date <  %s
),

-- ランクアップ、初回購入情報リスト
rank_up_list AS (
    SELECT
        order_code,
        jwoa_code,
        bonus_payment_date,
        order_type,
        bv,
        IFNULL(bv, 0) AS custom_bv
    FROM bonus_db.purchase_info_list AS p
    WHERE order_type IN (102, 103)
      AND bonus_payment_date >= %s
      AND bonus_payment_date <  %s
),

-- 再購入リスト + ランクアップ、初回購入情報リスト
purchase_list_union AS (
    SELECT *
    FROM repurchase_list
    WHERE custom_bv > 0

    UNION ALL

    SELECT *
    FROM rank_up_list
    WHERE custom_bv > 0
),


-- 購入リストの合計
purchase_sum_bv AS (
    SELECT
        jwoa_code,
        SUM(custom_bv) AS sum_bv
    FROM purchase_list_union
    GROUP BY jwoa_code
),

-- 購入者リスト
purchase_users AS (
    SELECT DISTINCT
        jwoa_code
    FROM purchase_list_union
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
        0 AS lvl
    FROM bonus_db.users AS u
    JOIN purchase_users AS pu
      ON pu.jwoa_code = u.jmoa_code

    UNION ALL

    -- ② 上にさかのぼる
    SELECT
        t.payer_code,
        t.payer_name,
        up.jmoa_code AS line_code,
        up.placement_code AS upper_code,
        t.lvl + 1 AS lvl
    FROM payer_tree AS t
    JOIN bonus_db.users AS up
      ON up.jmoa_code = t.upper_code
    WHERE t.lvl < 1000
      AND t.upper_code IS NOT NULL
      AND t.upper_code <> ''
),


-- 支払い者のリスト
payer_list AS (
    SELECT
        t.payer_code AS 購入者コード,
        t.payer_name AS 購入者名,
        t.line_code AS ラインコード,
        t.upper_code AS 上位者コード,
        up.send_bv_name AS 上位者名,
        t.lvl + 1 AS 階層
    FROM payer_tree AS t
    LEFT JOIN bonus_db.users AS up
      ON up.jmoa_code = t.upper_code
    WHERE t.upper_code IS NOT NULL
      AND t.upper_code <> ''
    order by 購入者コード, 階層
),


-- 支払い者のリスト_in_前月の購入情報
payer_list_prevMonth_users as (
SELECT
    pl.*,
    ur.new_rank as 上位者ランク,
    p_sum_bv.sum_bv
FROM payer_list AS pl
JOIN sum_prev_purchasers_list AS spl
  ON spl.jwoa_code = pl.上位者コード
left join bonus_db.users_target_rank as ur
 on pl.上位者コード = ur.jmoa_code
left join purchase_sum_bv as p_sum_bv
 on pl.購入者コード = p_sum_bv.jwoa_code
order by pl.上位者名, pl.ラインコード, 階層
),


-- 収入ライン or 基本ラインの判定
line_flg AS (
SELECT
    a.*,
    IFNULL(b.carry_over_bv, 0) AS carry_over_bv,
    a.line_bv + IFNULL(b.carry_over_bv, 0) AS plus_carry_bv,

    CASE
        WHEN ROW_NUMBER() OVER (
            PARTITION BY a.上位者コード
            ORDER BY a.line_bv + IFNULL(b.carry_over_bv, 0) DESC
        ) >= 3
        THEN 2

        ELSE ROW_NUMBER() OVER (
            PARTITION BY a.上位者コード
            ORDER BY a.line_bv + IFNULL(b.carry_over_bv, 0) DESC
        )
    END AS rn

FROM (
    SELECT
        上位者コード,
        上位者名,
        上位者ランク,
        ラインコード,
        SUM(sum_bv) AS line_bv
    FROM payer_list_prevMonth_users
    GROUP BY
        上位者コード,
        上位者名,
        上位者ランク,
        ラインコード
) AS a
LEFT JOIN prev_week_basic_carry_over_bv b
  ON a.上位者コード = b.placement_code
 AND a.ラインコード = b.jwoa_code
),

-- ブルーダイヤ
blue_daiya as (
SELECT 上位者コード
FROM line_flg
WHERE rn IN (1, 2)
GROUP BY 上位者コード
HAVING
    COUNT(*) = 2
    AND MIN(plus_carry_bv) >= 250000
),

-- ans_basic_bonus
ans_basic_bonus AS (
SELECT
    a.上位者コード as placement_code,
    a.上位者名 as placement_name,
    a.上位者ランク as placement_rank,
    a.ラインコード as line_code,
    a.購入者コード as purchaser_code,
    a.購入者名 as purchaser_name,
    a.階層 as level,
    a.sum_bv,
    IFNULL(b.plus_carry_bv, 0) as plus_carry_bv,

    CASE
        WHEN bd.上位者コード IS NOT NULL THEN 20
        WHEN a.上位者ランク = 1 THEN 10
        WHEN a.上位者ランク = 4 THEN 12
        ELSE 0
    END AS bonus_rate,

    TRUNCATE(
        CASE
            WHEN bd.上位者コード IS NOT NULL THEN LEAST(IFNULL(b.plus_carry_bv, 0), 250000) * 0.20
            WHEN a.上位者ランク = 1 THEN LEAST(IFNULL(b.plus_carry_bv, 0), 5000) * 0.10
            WHEN a.上位者ランク = 4 THEN LEAST(IFNULL(b.plus_carry_bv, 0), 125000) * 0.12
            ELSE 0
        END,
    2
    ) AS bonus_amount,

    CASE
        WHEN bd.上位者コード IS NOT NULL THEN 1
        ELSE 0
    END AS blue_daiya_flg

FROM payer_list_prevMonth_users AS a
JOIN line_flg AS b
  ON a.上位者コード = b.上位者コード
 AND a.ラインコード = b.ラインコード

LEFT JOIN blue_daiya bd
  ON a.上位者コード = bd.上位者コード
WHERE b.rn > 1
)


select
 *
from ans_basic_bonus
"""