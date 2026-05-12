BASIC_BV_LINE_SQL = """
WITH RECURSIVE


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


-- アクティブ会員
is_active_users as (
select *, 50 as bv
from bonus_db.active_users
where year = %s and month = %s
),


-- 前週のベーシック繰り越しBV
prev_basic_carry_over_bv AS (
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
          AND p.bonus_payment_date < %s

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


-- 繰り越しBV(アクティブ会員だけ)
active_prev_basic_carry_over_bv as (
select a.*
from prev_basic_carry_over_bv as a
join sum_prev_purchasers_list as b
on a.placement_code = b.jwoa_code
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
      AND bonus_payment_date < %s
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
      AND bonus_payment_date < %s
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

-- 支払い者のリスト_in_前月の購入情報 + 繰り越しBV
payer_list_prevMonth_users_add_carry_bv as (
SELECT
    上位者コード,
    上位者名,
    ラインコード,
    購入者コード,
    購入者名,
    sum_bv,
    0 AS carry_flg
FROM payer_list_prevMonth_users

UNION ALL

SELECT
    placement_code AS 上位者コード,
    '' AS 上位者名,
    jwoa_code AS ラインコード,
    '' AS 購入者コード,
    '' AS 購入者名,
    carry_over_bv AS sum_bv,
    1 AS carry_flg
FROM active_prev_basic_carry_over_bv
),

sum_payer_list_prevMonth_users_add_carry_bv as (
select 
 上位者コード,
 ラインコード,
 sum(sum_bv) as line_bv
from payer_list_prevMonth_users_add_carry_bv
group by
 上位者コード,
 ラインコード
),

-- 収入ライン or 基本ラインの判定
line_flg AS (
SELECT
    a.*,

    CASE
        WHEN ROW_NUMBER() OVER (
            PARTITION BY a.上位者コード
            ORDER BY a.plus_carry_bv DESC
        ) >= 3
        THEN 2

        ELSE ROW_NUMBER() OVER (
            PARTITION BY a.上位者コード
            ORDER BY a.plus_carry_bv DESC
        )
    END AS rn

FROM (
    SELECT
        上位者コード,
        ラインコード,
        SUM(line_bv) AS plus_carry_bv
    FROM sum_payer_list_prevMonth_users_add_carry_bv
    GROUP BY
        上位者コード,
        ラインコード
) AS a
order by 上位者コード
),

-- 基本ライン、収入ラインごとに合計
sum_line_flg as (
select
 上位者コード,
 rn,
 sum(plus_carry_bv) as sum_plus_carry_bv
from line_flg
group by
 上位者コード,
 rn
order by
 上位者コード,
 rn
),

-- rn1 - rn2
line_diff AS (
SELECT
    上位者コード,

    IFNULL(
        MAX(CASE WHEN rn = 1 THEN sum_plus_carry_bv END),
        0
    ) AS rn1_bv,

    IFNULL(
        MAX(CASE WHEN rn = 2 THEN sum_plus_carry_bv END),
        0
    ) AS rn2_bv,

    IFNULL(
        MAX(CASE WHEN rn = 1 THEN sum_plus_carry_bv END),
        0
    )
    -
    IFNULL(
        MAX(CASE WHEN rn = 2 THEN sum_plus_carry_bv END),
        0
    ) AS diff_bv

FROM sum_line_flg
GROUP BY 上位者コード
)

select
 a.上位者コード as placement_code,
 a.ラインコード as jmoa_code,
 0 as bv,
 b.diff_bv as carry_over_bv
from line_flg as a
left join line_diff as b
on a.上位者コード = b.上位者コード
where a.rn = 1
"""