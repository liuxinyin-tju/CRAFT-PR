# parser/method_parser.py
from __future__ import annotations
from typing import List

from tree_sitter import Node

from core.method import MethodInfo
from core.variables import ParameterInfo
from parser.type_parser import parse_type_node
from parser.body_parser import parse_method_body
from parser.utils import query_captures


METHOD_QUERY = """
(method_declaration) @method
"""

CTOR_QUERY = """
(constructor_declaration) @ctor
"""

METHOD_ATTR_QUERY = """
(method_declaration
    type: (_) @ret
    name: (_) @name
    parameters: (formal_parameters) @params
)
"""

CTOR_ATTR_QUERY = """
(constructor_declaration
    name: (_) @name
    parameters: (formal_parameters) @params
    body: (_) @body
)
"""


def parse_methods(class_body_node: Node, code: str) -> List[MethodInfo]:
    """
    解析 class body 中所有方法和构造方法。
    """
    methods: List[MethodInfo] = []

    # 普通方法
    method_nodes = query_captures(METHOD_QUERY, "method", class_body_node)
    for node in method_nodes:
        methods.append(_parse_single_method(node, code))

    # 构造方法
    ctor_nodes = query_captures(CTOR_QUERY, "ctor", class_body_node)
    for node in ctor_nodes:
        methods.append(_parse_single_constructor(node, code))

    return methods


def _parse_single_method(node: Node, code: str) -> MethodInfo:
    attrs = query_captures(METHOD_ATTR_QUERY, None, node)

    name_node = attrs.get("name", [None])[0]
    ret_node = attrs.get("ret", [None])[0]
    params_node = attrs.get("params", [None])[0]

    body = node.child_by_field_name("body")

    method = MethodInfo(
        name=name_node.text.decode("utf-8") if name_node else "",
        content=node.text.decode("utf-8"),
        return_type=parse_type_node(ret_node, code),
        parameters=_parse_parameters(params_node, code),
        modifiers=set(_extract_modifiers(node)),
        annotations=[],
        local_variables=[],
        method_calls=[],
        is_constructor=False,
        span=_span(node),
        body_span=_span(body) if body else None,
    )

    parse_method_body(method, body, code)
    return method


def _parse_single_constructor(node: Node, code: str) -> MethodInfo:
    attrs = query_captures(CTOR_ATTR_QUERY, None, node)

    name = attrs.get("name", [None])[0]
    params = attrs.get("params", [None])[0]
    body = attrs.get("body", [None])[0]

    method = MethodInfo(
        name=name.text.decode("utf-8") if name else "",
        content=node.text.decode("utf-8"),
        return_type=None,
        parameters=_parse_parameters(params, code),
        modifiers=set(_extract_modifiers(node)),
        annotations=[],
        local_variables=[],
        method_calls=[],
        is_constructor=True,
        span=_span(node),
        body_span=_span(body),
    )

    parse_method_body(method, body, code)
    return method


def _parse_parameters(params_node: Node, code: str):
    params: List[ParameterInfo] = []

    if params_node is None:
        return params

    for p in params_node.children:
        if p.type != "formal_parameter":
            continue

        type_node = None
        name_node = None
        for c in p.children:
            if "type" in c.type:
                type_node = c
            if c.type == "identifier":
                name_node = c

        if type_node and name_node:
            params.append(
                ParameterInfo(
                    name=name_node.text.decode("utf-8"),
                    content=p.text.decode("utf-8"),
                    type=parse_type_node(type_node, code),
                )
            )
    return params


def _extract_modifiers(node: Node):
    if node.children and node.children[0].type == "modifiers":
        return node.children[0].text.decode("utf-8").split()
    return []


def _span(node: Node):
    if node is None:
        return None
    return dict(
        start_byte=node.start_byte,
        end_byte=node.end_byte,
        start_line=node.start_point[0],
        start_col=node.start_point[1],
        end_line=node.end_point[0],
        end_col=node.end_point[1],
    )