# parser/type_parser.py
from __future__ import annotations
from typing import Optional
from core.types import TypeInfo

PRIMITIVES = {"int", "float", "double", "boolean", "char", "byte", "short", "long"}


def parse_type_node(node, code: str) -> Optional[TypeInfo]:
    """
    将 Tree-sitter 的类型节点解析为 TypeInfo。
    类型结构拆分逻辑：
        - raw: 原始代码中的类型字符串
        - base: 去掉泛型和数组后的主类型名
        - array_dimension: 统计 "[]"
        - is_primitive: 是否为基本类型
        - is_fqn: 是否包含'.'判断为是否为 FQN
    """
    if node is None:
        return None

    raw = node.text.decode("utf-8").strip()
    array_dim = raw.count("[]")

    base = raw
    if "<" in base:
        base = base.split("<", 1)[0]
    base = base.replace("[]", "").strip()

    is_primitive = base in PRIMITIVES
    is_fqn = "." in base and not is_primitive

    return TypeInfo(
        raw=raw,
        base=base,
        array_dimension=array_dim,
        is_primitive=is_primitive,
        is_fqn=is_fqn,
        generics=[],   # 泛型若要拆可再扩展
    )