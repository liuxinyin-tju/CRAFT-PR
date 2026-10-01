# parser/class_parser.py
from __future__ import annotations
from typing import List, Optional

from tree_sitter import Node

from core.clazz import ClassInfo
from parser.field_parser import parse_fields
from parser.method_parser import parse_methods


def parse_classes(root: Node, code: str) -> List[ClassInfo]:
    """
    从文件 AST 解析所有顶层类/接口/枚举，并递归解析内部类。
    最终返回文件中所有 ClassInfo 列表。
    """
    classes: List[ClassInfo] = []

    for child in root.children:
        if child.type in ("class_declaration", "interface_declaration", "enum_declaration"):
            parse_single_class(child, code, None, classes)

    return classes


def parse_single_class(node: Node, code: str, outer: Optional[ClassInfo], collector: List[ClassInfo]) -> ClassInfo:
    name_node = node.child_by_field_name("name")
    cls_name = name_node.text.decode("utf-8") if name_node else ""

    kind = node.type.replace("_declaration", "")
    modifiers = []
    if node.children and node.children[0].type == "modifiers":
        modifiers = node.children[0].text.decode("utf-8").split()

    superclass = _get_super_name(node)
    interfaces = _get_interface_names(node)

    cls = ClassInfo(
        name=cls_name,
        package=None,     # file_parser 填充
        kind=kind,
        content=node.text.decode("utf-8"),
        superclass_name=superclass,
        interface_names=interfaces,
        modifiers=set(modifiers),
        annotations=[],
        fields={},
        methods={},
        span=_span(node),
        outer_class=outer,
    )

    body = node.child_by_field_name("body")
    if body:
        field_list = parse_fields(body, code)
        cls.fields = {f.name: f for f in field_list}

        method_list = parse_methods(body, code)
        for m in method_list:
            cls.methods.setdefault(m.name, []).append(m)

        # 内部类
        for ch in body.children:
            if ch.type in ("class_declaration", "interface_declaration", "enum_declaration"):
                inner = parse_single_class(ch, code, cls, collector)
                cls.inner_classes[inner.name] = inner

    collector.append(cls)
    return cls


def _get_super_name(node: Node) -> Optional[str]:
    super_node = node.child_by_field_name("superclass")
    if super_node is None:
        return None
    txt = super_node.text.decode("utf-8").strip()
    parts = txt.split()
    return parts[1] if len(parts) >= 2 else None


def _get_interface_names(node: Node) -> List[str]:
    result: List[str] = []
    itf = node.child_by_field_name("super_interfaces")
    if itf is None:
        return result

    txt = itf.text.decode("utf-8").strip()
    if txt.startswith("implements"):
        txt = txt[len("implements"):].strip()

    for part in txt.split(","):
        part = part.strip()
        if part:
            result.append(part)
    return result


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