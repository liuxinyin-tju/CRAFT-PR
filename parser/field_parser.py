# parser/field_parser.py
from __future__ import annotations
from typing import List

from tree_sitter import Node

from core.variables import FieldInfo
from parser.type_parser import parse_type_node
from parser.utils import query_captures


FIELD_QUERY = """
(field_declaration) @field
"""

FIELD_ATTR_QUERY = """
(field_declaration
    type: (_) @type
    declarator: (variable_declarator name: (identifier) @name)
)
"""


def parse_fields(class_body_node: Node, code: str) -> List[FieldInfo]:
    """
    从 class body 中解析字段列表。
    逻辑：
        - 定位所有 field_declaration
        - 分别解析字段类型和字段名
        - 若存在修饰符，加入字段信息
    """
    fields: List[FieldInfo] = []

    field_nodes = query_captures(FIELD_QUERY, "field", class_body_node)

    for node in field_nodes:
        attrs = query_captures(FIELD_ATTR_QUERY, None, node)
        types = attrs.get("type", [])
        names = attrs.get("name", [])

        modifiers = set(_extract_modifiers(node))

        for tnode, nnode in zip(types, names):
            fields.append(
                FieldInfo(
                    name=nnode.text.decode("utf-8"),
                    type=parse_type_node(tnode, code),
                    modifiers=modifiers,
                    annotations=[],
                    initializer_src=None,
                    span=None,
                    content=node.text.decode("utf-8"),
                )
            )

    return fields


def _extract_modifiers(node: Node):
    if node.children and node.children[0].type == "modifiers":
        return node.children[0].text.decode("utf-8").split()
    return []