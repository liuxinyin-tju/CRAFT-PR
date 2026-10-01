# core/method.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Set

from core.types import TypeInfo
from core.variables import ParameterInfo, LocalVariableInfo


@dataclass
class MethodCallInfo:
    """
    表示一次方法调用。

    ------------------------------------------------------------
    字段含义：

    qualifier:
        方法调用的前缀；
        例如 foo.bar() → qualifier="foo"

    method_name:
        调用的方法名，例如 "add" 或 "save"。

    argument_types:
        调用参数的类型列表（TypeInfo 列表）。
        第一阶段通常为空，第二阶段做类型推断后填入。

    span:
        在源代码中的具体位置。

    resolved_fqn:
        第二阶段中推断出的调用目标类的完全限定名。

    resolved_method_signature:
        推断出的唯一方法签名键，例如
        "save(com.example.User)"

    ------------------------------------------------------------
    示例：

        repo.save(user);

        第一阶段生成：
            qualifier="repo"
            method_name="save"

        第二阶段再推断：
            resolved_fqn="com.example.UserRepo"
    """

    qualifier: Optional[str]
    method_name: str
    content: Optional[str] = None
    argument_types: List[TypeInfo] = field(default_factory=list)
    span: Optional[object] = None

    resolved_fqn: Optional[str] = None
    resolved_method_signature: Optional[str] = None


@dataclass
class MethodInfo:
    """
    表示 Java 方法或构造器（构造器 is_constructor=True）。

    ------------------------------------------------------------
    字段含义：

    name:
        方法名，例如 "save" 或 "run"。
        对构造器，name 与类名一致。

    return_type:
        返回值类型（TypeInfo）。
        构造器为 None。

    parameters:
        方法参数列表 ParameterInfo。

    modifiers:
        方法修饰符，例如 {"public", "static"}。

    annotations:
        方法上的注解列表。

    local_variables:
        方法内部定义的局部变量列表。

    method_calls:
        方法内部所有方法调用的列表。

    is_constructor:
        若为构造器，则此值为 True。

    span / body_span:
        该方法在源码中的起止位置。

    override_parent:
        若此方法是 override 的方法，则指向父类的方法。

    override_children:
        所有 override 当前方法的子类方法。
    """

    name: str
    return_type: Optional[TypeInfo]
    content: Optional[str] = None
    parameters: List[ParameterInfo] = field(default_factory=list)

    modifiers: Set[str] = field(default_factory=set)
    annotations: List[str] = field(default_factory=list)

    local_variables: List[LocalVariableInfo] = field(default_factory=list)
    method_calls: List[MethodCallInfo] = field(default_factory=list)

    is_constructor: bool = False

    span: Optional[object] = None
    body_span: Optional[object] = None

    override_parent: Optional["MethodInfo"] = None
    override_children: List["MethodInfo"] = field(default_factory=list)

    def signature_key(self) -> str:
        """
        根据解析后的参数类型构建方法的唯一识别键。
        """
        arg_types = ",".join(
            [p.type.resolved_fqn or p.type.base for p in self.parameters]
        )
        return f"{self.name}({arg_types})"

    def __repr__(self):
        return f"MethodInfo(name={self.name}, return={self.return_type})"