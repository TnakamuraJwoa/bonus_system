INTRODUCER_TREE_REBUILD_CACHE_SQL = """
INSERT INTO bonus_db.C_users_introducer_tree_cache (
    introducer_code,
    introducer_name,
    introducer_rank,
    jwoa_code,
    jwoa_name,
    `rank`,
    tree_level
)
WITH RECURSIVE user_tree (
    introducer_code,
    introducer_name,
    introducer_rank,
    jwoa_code,
    jwoa_name,
    `rank`,
    tree_level
) AS (
    SELECT
        u.introducer_code,
        parent.send_bv_name,
        parent.`rank`,
        u.jmoa_code,
        u.send_bv_name,
        u.`rank`,
        0
    FROM bonus_db.users u
    LEFT JOIN bonus_db.users parent
        ON parent.jmoa_code = u.introducer_code
    WHERE u.jmoa_code = 'JP1873001'

    UNION ALL

    SELECT
        u.introducer_code,
        parent.send_bv_name,
        parent.`rank`,
        u.jmoa_code,
        u.send_bv_name,
        u.`rank`,
        ut.tree_level + 1
    FROM user_tree ut
    INNER JOIN bonus_db.users u
        ON u.introducer_code = ut.jwoa_code
    LEFT JOIN bonus_db.users parent
        ON parent.jmoa_code = u.introducer_code
)
SELECT
    introducer_code,
    introducer_name,
    introducer_rank,
    jwoa_code,
    jwoa_name,
    `rank`,
    tree_level
FROM user_tree
ORDER BY tree_level, jwoa_code
"""


INTRODUCER_TREE_MEMBER_COUNT_SQL = """
    SELECT COUNT(*)
    FROM bonus_db.C_users_introducer_tree_cache
    WHERE jwoa_code = %s
"""


INTRODUCER_TREE_FOCUS_SQL = """
    SELECT
        c.id,
        c.introducer_code,
        c.introducer_name,
        c.introducer_rank,
        c.jwoa_code,
        c.jwoa_name,
        c.`rank`,
        c.tree_level,
        c.created_at
    FROM bonus_db.C_users_introducer_tree_cache c
    WHERE c.jwoa_code = %s
    ORDER BY c.id
    LIMIT 1
"""


INTRODUCER_TREE_UPLINE_SQL = """
WITH RECURSIVE upline AS (
    SELECT
        c.id,
        c.introducer_code,
        c.introducer_name,
        c.introducer_rank,
        c.jwoa_code,
        c.jwoa_name,
        c.`rank`,
        c.tree_level,
        c.created_at,
        0 AS rel_level
    FROM bonus_db.C_users_introducer_tree_cache c
    WHERE c.jwoa_code = %s

    UNION ALL

    SELECT
        c.id,
        c.introducer_code,
        c.introducer_name,
        c.introducer_rank,
        c.jwoa_code,
        c.jwoa_name,
        c.`rank`,
        c.tree_level,
        c.created_at,
        u.rel_level - 1 AS rel_level
    FROM bonus_db.C_users_introducer_tree_cache c
    INNER JOIN upline u
        ON c.jwoa_code = u.introducer_code
    WHERE u.rel_level > -%s
      AND u.introducer_code IS NOT NULL
      AND u.introducer_code <> ''
)
SELECT
    id,
    introducer_code,
    introducer_name,
    introducer_rank,
    jwoa_code,
    jwoa_name,
    `rank`,
    tree_level,
    created_at,
    rel_level
FROM upline
WHERE rel_level < 0
ORDER BY rel_level ASC
LIMIT %s
"""


INTRODUCER_TREE_DOWNLINE_SQL = """
WITH RECURSIVE downline AS (
    SELECT
        c.id,
        c.introducer_code,
        c.introducer_name,
        c.introducer_rank,
        c.jwoa_code,
        c.jwoa_name,
        c.`rank`,
        c.tree_level,
        c.created_at,
        1 AS rel_level
    FROM bonus_db.C_users_introducer_tree_cache c
    WHERE c.introducer_code = %s

    UNION ALL

    SELECT
        c.id,
        c.introducer_code,
        c.introducer_name,
        c.introducer_rank,
        c.jwoa_code,
        c.jwoa_name,
        c.`rank`,
        c.tree_level,
        c.created_at,
        d.rel_level + 1 AS rel_level
    FROM bonus_db.C_users_introducer_tree_cache c
    INNER JOIN downline d
        ON c.introducer_code = d.jwoa_code
    WHERE d.rel_level < %s
)
SELECT
    id,
    introducer_code,
    introducer_name,
    introducer_rank,
    jwoa_code,
    jwoa_name,
    `rank`,
    tree_level,
    created_at,
    rel_level
FROM downline
ORDER BY rel_level ASC, jwoa_code ASC
LIMIT %s
"""
