# parser/utils.py
from __future__ import annotations
from typing import Dict, List, Optional

from tree_sitter import Node, Query
from configs.config import JAVA_LANGUAGE


def query_captures(query_str: str, cap: Optional[str], node: Node):
    """
    Tree-sitter Query 辅助函数。
    基于 tree-sitter 0.24.0 的 Python binding：
        query.captures(node) → Dict[str, List[Node]]

    行为约定：
        - cap 不为 None：返回该 capture 名称对应的节点列表 List[Node]
        - cap 为 None：返回完整 dict，用于提取多个 capture
    """
    query = JAVA_LANGUAGE.query(query_str)
    # query = Query(JAVA_LANGUAGE, query_str)
    captures: Dict[str, List[Node]] = query.captures(node)

    if cap is not None:
        return captures.get(cap, [])
    return captures