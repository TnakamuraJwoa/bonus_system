import logging
from collections import defaultdict

from django.db import connections

from connect.sql.placement_tree_sql import (
    PLACEMENT_TREE_DOWNLINE_SQL,
    PLACEMENT_TREE_FOCUS_SQL,
    PLACEMENT_TREE_MEMBER_COUNT_SQL,
    PLACEMENT_TREE_UPLINE_SQL,
)

logger = logging.getLogger(__name__)

MAX_TREE_DEPTH = 15
MAX_TREE_NODES = 500


def _row_to_dict(cursor, row):
    cols = [col[0] for col in cursor.description]
    return dict(zip(cols, row))


def _execute_rows(sql, params):
    with connections["rds"].cursor() as cursor:
        logger.info("上位者ツリーSQLを実行します。")
        cursor.execute(sql, params)
        return [_row_to_dict(cursor, row) for row in cursor.fetchall()]


def _execute_scalar(sql, params):
    with connections["rds"].cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return int(row[0]) if row else 0


def _node_from_row(row):
    return {
        "jwoa_code": row.get("jwoa_code") or "",
        "send_bv_name": row.get("send_bv_name") or "",
        "rank": row.get("rank"),
        "placement_code": row.get("placement_code") or "",
        "rel_level": row.get("rel_level", 0),
        "children": [],
    }


def _build_children_tree(parent_code, children_by_parent):
    nodes = []
    for row in children_by_parent.get(parent_code, []):
        node = _node_from_row(row)
        node["children"] = _build_children_tree(node["jwoa_code"], children_by_parent)
        nodes.append(node)
    return nodes


def build_member_tree_view(jwoa_code):
    result = {
        "tree_ancestors": [],
        "tree_focus": None,
        "tree_children": [],
        "tree_truncated": False,
        "tree_unavailable_reason": None,
        "tree_node_count": 0,
    }

    member_code = (jwoa_code or "").strip()
    if not member_code:
        result["tree_unavailable_reason"] = (
            "Enter a member code and search to display the tree."
        )
        return result

    member_count = _execute_scalar(
        PLACEMENT_TREE_MEMBER_COUNT_SQL,
        [member_code],
    )
    if member_count == 0:
        result["tree_unavailable_reason"] = (
            f"会員コード {member_code} のデータが見つかりません。"
        )
        return result
    if member_count > 1:
        result["tree_unavailable_reason"] = (
            f"会員コード {member_code} が複数件ヒットしています。"
            "完全一致で1件に特定できるコードを入力してください。"
        )
        return result

    focus_rows = _execute_rows(PLACEMENT_TREE_FOCUS_SQL, [member_code])
    if not focus_rows:
        result["tree_unavailable_reason"] = (
            f"会員コード {member_code} のデータが見つかりません。"
        )
        return result

    focus = _node_from_row(focus_rows[0])
    focus["rel_level"] = 0

    upline_rows = _execute_rows(
        PLACEMENT_TREE_UPLINE_SQL,
        [member_code, MAX_TREE_DEPTH, MAX_TREE_NODES],
    )
    downline_rows = _execute_rows(
        PLACEMENT_TREE_DOWNLINE_SQL,
        [member_code, MAX_TREE_DEPTH, MAX_TREE_NODES],
    )

    ancestors = [_node_from_row(row) for row in upline_rows]

    children_by_parent = defaultdict(list)
    for row in downline_rows:
        children_by_parent[row["placement_code"]].append(row)

    children = _build_children_tree(member_code, children_by_parent)

    node_count = len(ancestors) + 1 + len(downline_rows)
    truncated = (
        len(upline_rows) >= MAX_TREE_NODES
        or len(downline_rows) >= MAX_TREE_NODES
    )

    result["tree_ancestors"] = ancestors
    result["tree_focus"] = focus
    result["tree_children"] = children
    result["tree_truncated"] = truncated
    result["tree_node_count"] = node_count
    return result
