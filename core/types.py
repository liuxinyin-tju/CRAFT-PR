# core/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TypeInfo:
    """
    表示一个 Java 类型的统一结构模型。
    该结构在“第一阶段语法解析”阶段存储源代码中的类型表示；
    在“第二阶段语义解析”中填入最终的类型解析结果。

    ------------------------------------------------------------
    字段含义：

    raw:
        源代码中出现的类型原文。
        例如：
            "int"
            "String"
            "List<User>"
            "Map<String, List<Order>>"
            "Order[]"

    base:
        去掉泛型、数组符号后的基础类型名。
        例如：
            raw="List<User>"    → base="List"
            raw="Order[][]"     → base="Order"

    generics:
        类型中的泛型参数列表，每个都是一个 TypeInfo。
        例如 Map<String,User> 会解析为 generics=["String","User"] 两个 TypeInfo

    array_dimension:
        数组维度，例如：
            int[]     → 1
            int[][]   → 2

    is_primitive:
        是否是基本类型，如 int、double、boolean。

    is_fqn:
        是否是形如 "com.example.User" 的完全限定类名（即含有点号）。

    resolved_fqn:
        第二阶段类型解析后填充。
        最终解析出的类的完全限定名。
        如果该类型不是项目类或无法解析，则保持 None。

    ------------------------------------------------------------
    示例：

        对于代码：
            List<User[]> repo

        第一阶段生成的 TypeInfo 为：
            raw = "List<User[]>"
            base = "List"
            generics = [
                TypeInfo(raw="User[]", base="User", array_dimension=1)
            ]
            array_dimension = 0
            is_primitive = False
            resolved_fqn = None（第二阶段解析后可能填入 "java.util.List"）

    """

    raw: str
    base: str
    generics: List["TypeInfo"] = field(default_factory=list)
    array_dimension: int = 0
    is_primitive: bool = False
    is_fqn: bool = False

    resolved_fqn: Optional[str] = None

    def __repr__(self):
        return f"TypeInfo(raw={self.raw}, resolved={self.resolved_fqn})"