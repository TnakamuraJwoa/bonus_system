REPURCHASE_LAST_MONTH = """
-- 注文情報テーブルにボーナス支払日の日付を追加

WITH bonus_orders AS (
    SELECT
        o.*,
        b.bonus_payment_date,
        COALESCE(b.bonus_payment_date, o.deposit_at) AS payment_date
    FROM bonus_db.orders AS o
    LEFT JOIN bonus_db.bonus_payment_date AS b
        ON o.order_code = b.order_code
),

aa as (
SELECT
    a.order_code,
    b.jwoa_code,
    u.send_bv_name,
    a.order_type,
    a.total_bv,
    b.distribution_bv AS bv,
    a.deposit_at,
    a.order_at,
    a.payment_date,
    a.order_year,
    a.order_month,
    %s AS register_year,
    %s AS register_month
FROM bonus_orders AS a
LEFT JOIN bonus_db.orders_distribution_bv AS b
    ON a.order_code = b.order_code
LEFT JOIN bonus_db.users AS u
    ON b.jwoa_code = u.jmoa_code
WHERE a.order_status NOT IN (206, 207, 208)
  AND a.payment_date >= %s
  AND a.payment_date < %s
  AND a.bv_actived_flg = 1

UNION ALL

SELECT
    doc_no AS order_code,
    member_no AS jwoa_code,
    firstname AS send_bv_name,
    105 AS order_type,
    0 AS total_bv,
    total_bv AS bv,
    payment_date AS deposit_at,
    payment_date AS order_at,
    payment_date AS bonus_payment_date,
    order_year,
    order_month,
    %s AS register_year,
    %s AS register_month
FROM bonus_db.api_users_bv
WHERE order_year = %s
  AND order_month = %s
)

SELECT *
FROM aa
"""