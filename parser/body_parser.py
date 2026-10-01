# parser/body_parser.py
from __future__ import annotations
from typing import Optional

from tree_sitter import Node

from core.variables import LocalVariableInfo
from core.method import MethodCallInfo
from core.types import TypeInfo

from parser.utils import query_captures
from parser.type_parser import parse_type_node


LOCAL_VAR_QUERY = """
(local_variable_declaration) @var
"""

LOCAL_VAR_ATTR_QUERY = """
(local_variable_declaration
    type: (_) @type
    declarator: (variable_declarator name: (identifier) @name)
)
"""

CALL_QUERY = """
(method_invocation) @call
"""

CALL_ATTR_QUERY = """
(method_invocation
    object: (_) @object
    name: (_) @name
    arguments: (argument_list) @args
)
"""


def parse_method_body(method_ctx, body_node: Optional[Node], code: str):
    """
    解析方法体，提取：
        - 局部变量 LocalVariableInfo
        - 方法调用 MethodCallInfo
    """
    if body_node is None:
        return

    # -------- 1) 局部变量 --------
    var_nodes = query_captures(LOCAL_VAR_QUERY, "var", body_node)

    for vnode in var_nodes:
        attrs = query_captures(LOCAL_VAR_ATTR_QUERY, None, vnode)
        tlist = attrs.get("type", [])
        nlist = attrs.get("name", [])

        for tnode, nnode in zip(tlist, nlist):
            method_ctx.local_variables.append(
                LocalVariableInfo(
                    name=nnode.text.decode("utf-8"),
                    content=vnode.text.decode("utf-8"),
                    type=parse_type_node(tnode, code),
                    span=None,
                )
            )

    # -------- 2) 方法调用 --------
    call_nodes = query_captures(CALL_QUERY, "call", body_node)
    for cnode in call_nodes:
        attrs = query_captures(CALL_ATTR_QUERY, None, cnode)

        obj = attrs.get("object", [None])[0]
        name = attrs.get("name", [None])[0]

        call = MethodCallInfo(
            qualifier=obj.text.decode("utf-8") if obj else None,
            method_name=name.text.decode("utf-8") if name else "",
            argument_types=[],
            span=None,
            content=cnode.text.decode("utf-8"),
        )

        method_ctx.method_calls.append(call)