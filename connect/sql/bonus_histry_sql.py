WEEK_BONUS_HISTORY_SQL = """
    SELECT
        p.kibetu,
        p.completion_date,

        MAX(
            CASE
                WHEN h.bonus_name = 'drive_bonus'
                THEN DATE(h.registered_at)
            END
        ) AS drive_bonus,
        MAX(
            CASE
                WHEN h.bonus_name = 'drive_bonus'
                 AND (
                    h.comment_text LIKE '0件%%'
                    OR h.comment_text LIKE '%%: 0件登録'
                 )
                THEN 1
            END
        ) AS drive_bonus_is_empty,

        MAX(
            CASE
                WHEN h.bonus_name = 'basic_bonus'
                THEN DATE(h.registered_at)
            END
        ) AS basic_bonus,
        MAX(
            CASE
                WHEN h.bonus_name = 'basic_bonus'
                 AND (
                    h.comment_text LIKE '0件%%'
                    OR h.comment_text LIKE '%%: 0件登録'
                 )
                THEN 1
            END
        ) AS basic_bonus_is_empty,

        MAX(
            CASE
                WHEN h.bonus_name = 'matching_bonus'
                THEN DATE(h.registered_at)
            END
        ) AS matching_bonus,
        MAX(
            CASE
                WHEN h.bonus_name = 'matching_bonus'
                 AND (
                    h.comment_text LIKE '0件%%'
                    OR h.comment_text LIKE '%%: 0件登録'
                 )
                THEN 1
            END
        ) AS matching_bonus_is_empty,

        MAX(
            CASE
                WHEN h.bonus_name = 'week_bonus'
                THEN DATE(h.registered_at)
            END
        ) AS week_bonus,
        MAX(
            CASE
                WHEN h.bonus_name = 'week_bonus'
                 AND (
                    h.comment_text LIKE '0件%%'
                    OR h.comment_text LIKE '%%: 0件登録'
                 )
                THEN 1
            END
        ) AS week_bonus_is_empty

    FROM bonus_db.period_master p

    LEFT JOIN (
        SELECT a.*
        FROM bonus_db.bonus_register_history a
        INNER JOIN (
            SELECT
                kibetu,
                bonus_name,
                MAX(registered_at) AS max_registered_at
            FROM bonus_db.bonus_register_history
            WHERE bonus_name IN (
                'drive_bonus',
                'basic_bonus',
                'matching_bonus',
                'week_bonus'
            )
            GROUP BY kibetu, bonus_name
        ) b
            ON a.kibetu = b.kibetu
           AND a.bonus_name = b.bonus_name
           AND a.registered_at = b.max_registered_at
    ) h
        ON p.kibetu = h.kibetu

    WHERE p.st_date IS NULL
       OR p.st_date <= DATE(CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo'))

    GROUP BY p.kibetu, p.completion_date
    ORDER BY p.st_date DESC, p.kibetu DESC;
"""

MONTH_BONUS_HISTORY_SQL = """
    SELECT
        mp.kibetu,
        mp.year,
        mp.month,
        mp.payment_date,

        MAX(
            CASE
                WHEN h.bonus_name = 'month_title'
                THEN DATE(h.registered_at)
            END
        ) AS month_title,
        MAX(
            CASE
                WHEN h.bonus_name = 'month_title'
                 AND (
                    h.comment_text LIKE '0件%%'
                    OR h.comment_text LIKE '%%: 0件登録'
                 )
                THEN 1
            END
        ) AS month_title_is_empty,

        MAX(
            CASE
                WHEN h.bonus_name = 'title_bonus'
                THEN DATE(h.registered_at)
            END
        ) AS title_bonus,
        MAX(
            CASE
                WHEN h.bonus_name = 'title_bonus'
                 AND (
                    h.comment_text LIKE '0件%%'
                    OR h.comment_text LIKE '%%: 0件登録'
                 )
                THEN 1
            END
        ) AS title_bonus_is_empty,

        MAX(
            CASE
                WHEN h.bonus_name = 'title_diff_bonus'
                THEN DATE(h.registered_at)
            END
        ) AS title_diff_bonus,
        MAX(
            CASE
                WHEN h.bonus_name = 'title_diff_bonus'
                 AND (
                    h.comment_text LIKE '0件%%'
                    OR h.comment_text LIKE '%%: 0件登録'
                 )
                THEN 1
            END
        ) AS title_diff_bonus_is_empty,

        MAX(
            CASE
                WHEN h.bonus_name = 'repurchase_over_bonus'
                THEN DATE(h.registered_at)
            END
        ) AS repurchase_over_bonus,
        MAX(
            CASE
                WHEN h.bonus_name = 'repurchase_over_bonus'
                 AND (
                    h.comment_text LIKE '0件%%'
                    OR h.comment_text LIKE '%%: 0件登録'
                 )
                THEN 1
            END
        ) AS repurchase_over_bonus_is_empty,

        MAX(
            CASE
                WHEN h.bonus_name = 'three_star_global_bonus'
                THEN DATE(h.registered_at)
            END
        ) AS three_star_global_bonus,
        MAX(
            CASE
                WHEN h.bonus_name = 'three_star_global_bonus'
                 AND (
                    h.comment_text LIKE '0件%%'
                    OR h.comment_text LIKE '%%: 0件登録'
                 )
                THEN 1
            END
        ) AS three_star_global_bonus_is_empty,

        MAX(
            CASE
                WHEN h.bonus_name = 'month_bonus'
                THEN DATE(h.registered_at)
            END
        ) AS month_bonus,
        MAX(
            CASE
                WHEN h.bonus_name = 'month_bonus'
                 AND (
                    h.comment_text LIKE '0件%%'
                    OR h.comment_text LIKE '%%: 0件登録'
                 )
                THEN 1
            END
        ) AS month_bonus_is_empty

    FROM bonus_db.monthly_period mp

    LEFT JOIN (
        SELECT a.*
        FROM bonus_db.bonus_register_history a
        INNER JOIN (
            SELECT
                kibetu,
                bonus_name,
                MAX(registered_at) AS max_registered_at
            FROM bonus_db.bonus_register_history
            WHERE bonus_name IN (
                'month_title',
                'title_bonus',
                'title_diff_bonus',
                'repurchase_over_bonus',
                'three_star_global_bonus',
                'month_bonus'
            )
            GROUP BY kibetu, bonus_name
        ) b
            ON a.kibetu = b.kibetu
           AND a.bonus_name = b.bonus_name
           AND a.registered_at = b.max_registered_at
    ) h
        ON mp.kibetu = h.kibetu

    GROUP BY mp.kibetu, mp.year, mp.month, mp.payment_date
    ORDER BY mp.year DESC, mp.month DESC, mp.kibetu DESC;
"""
