WEEK_BONUS_SQL = """
WITH
drive_bonus AS (
    SELECT
        introducer_code AS pay_code,
        SUM(sum_bonus_amount) AS sum_bv
    FROM bonus_db.B_drive_bonus_result
    WHERE kibetu = %s
    GROUP BY introducer_code
),

basic_bonus AS (
    SELECT
        placement_code AS pay_code,
        SUM(bonus_amount) AS sum_bv
    FROM bonus_db.B_basic_bonus_result
    WHERE kibetu = %s
    GROUP BY placement_code
),

matching_bonus AS (
    SELECT
        introducer_code AS pay_code,
        SUM(matching_bonus) AS sum_bv
    FROM bonus_db.B_matching_bonus_result
    WHERE kibetu = %s
    GROUP BY introducer_code
),

week_user_list AS (
    SELECT
        a.pay_code,
        IFNULL(b.send_bv_name, '') AS jwoa_name
    FROM (
        SELECT pay_code FROM drive_bonus
        UNION
        SELECT pay_code FROM basic_bonus
        UNION
        SELECT pay_code FROM matching_bonus
    ) AS a
    INNER JOIN nexus_production.users AS b
        ON a.pay_code = b.jmoa_code
),

week_bonus AS (
    SELECT
        %s AS 期別,
        a.pay_code AS 会員番号,
        a.jwoa_name AS 会員名,
        TRUNCATE(IFNULL(b.sum_bv, 0), 2) AS ドライブボーナス,
        TRUNCATE(IFNULL(c.sum_bv, 0), 2) AS ベーシックボーナス,
        TRUNCATE(IFNULL(d.sum_bv, 0), 2) AS マッチングボーナス,
        TRUNCATE(
            IFNULL(b.sum_bv, 0)
            + IFNULL(c.sum_bv, 0)
            + IFNULL(d.sum_bv, 0),
            2
        ) AS 週間ボーナス
    FROM week_user_list AS a

    LEFT JOIN drive_bonus AS b
        ON a.pay_code = b.pay_code

    LEFT JOIN basic_bonus AS c
        ON a.pay_code = c.pay_code

    LEFT JOIN matching_bonus AS d
        ON a.pay_code = d.pay_code
)

SELECT *
FROM week_bonus
ORDER BY 週間ボーナス DESC, 会員番号;
"""