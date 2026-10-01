# core/variables.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Set

from core.types import TypeInfo


@dataclass
class FieldInfo:
    """
    表示 Java 类的字段。

    ------------------------------------------------------------
    字段含义：

    name:
        字段名称。例如 "repo" 或 "count"。

    type:
        字段的类型（TypeInfo）。
        第一阶段仅解析原文，第二阶段解析后会填入 resolved_fqn。

    modifiers:
        字段修饰符，如 {"private", "static"}。

    annotations:
        字段上的注解。

    initializer_src:
        字段初始化代码的原文字符串。
        例如： "= new ArrayList<>()"

    span:
        字段在源码中的位置，可选。
    """

    name: str
    type: TypeInfo
    content: Optional[str] = None
    modifiers: Set[str] = field(default_factory=set)
    annotations: List[str] = field(default_factory=list)
    initializer_src: Optional[str] = None
    span: Optional[object] = None


@dataclass
class LocalVariableInfo:
    """
    表示方法体中的局部变量。

    ------------------------------------------------------------
    字段含义：

    name:
        变量名，例如 "temp"、"user"。

    type:
        变量类型 TypeInfo。

    span:
        变量声明所在源码位置。

    scope_start_byte, scope_end_byte:
        可选，用于表示局部变量作用域范围。

    """

    name: str
    type: TypeInfo
    content: Optional[str] = None
    span: Optional[object] = None

    scope_start_byte: Optional[int] = None
    scope_end_byte: Optional[int] = None


@dataclass
class ParameterInfo:
    """
    表示方法或构造器的参数。

    ------------------------------------------------------------
    字段含义：

    name:
        参数名称，如 "user" 或 "count"。

    type:
        参数类型（TypeInfo）。

    annotations:
        参数级注解，如 @NotNull。

    span:
        参数在代码中的位置。
    """

    name: str
    type: TypeInfo
    content: Optional[str] = None
    annotations: List[str] = field(default_factory=list)
    span: Optional[object] = None