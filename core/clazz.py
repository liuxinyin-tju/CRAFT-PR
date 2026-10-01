# core/class.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from core.variables import FieldInfo
from core.method import MethodInfo
from core.types import TypeInfo


@dataclass
class ClassInfo:
    """
    表示一个 Java 类的完整静态语义模型。

    该结构分两阶段填充：

    ------------------------------------------------------------
    第一阶段（语法解析阶段）会填入：
        - name                 → 类的简单名，如 "UserService"
        - package              → 包名，如 "com.foo.service"
        - kind                 → "class" / "interface" / "enum" / "record"

        - superclass_name      → extends 后面的名字（仅名字，未解析）
        - interface_names      → implements 后面的名字列表（未解析）

        - fields               → 所有字段 FieldInfo（类型尚未解析）
        - methods              → 所有方法 MethodInfo（返回值和参数类型尚未解析）

        - outer_class          → 如果是内部类，这里为外部类；否则为 None
        - inner_classes        → 当前类包含的内部类（name → ClassInfo）

    ------------------------------------------------------------
    第二阶段（语义解析阶段）会填入：
        - superclass           → 解析后的父类 ClassInfo
        - interfaces           → 解析后的接口列表 ClassInfo
        - children             → 当前类的所有直接子类
        - interface_impls      → 当前接口被哪些类实现

        - field.type.resolved_fqn        → 字段类型解析后的 FQN
        - method.return_type.resolved_fqn → 返回值最终类型
        - method.parameters[i].type.resolved_fqn → 参数最终类型

    ------------------------------------------------------------
    字段说明（非常重要）：

    name:
        类的简单名称。如 "OrderService"。

    package:
        包名，如 "com.example.order"。
        若在 default package，为 None。

    kind:
        类的种类："class", "interface", "enum", "record"。

    superclass_name:
        extends 后原始出现的字符串，如 "BaseService"。
        这是源码形态，未做类型匹配。

    interface_names:
        implements 后原始出现的接口名列表，如 ["Runnable", "Serializable"]。

    fields:
        字段表。键是字段名，值是 FieldInfo。
        FieldInfo.type.raw 是源码类型，比如 "List<User>"（未解析）。

    methods:
        方法表。键是方法名，值是方法列表（因为同名重载）。
        方法类型信息（返回类型、参数类型）第二阶段才解析。

    outer_class:
        若本类是内部类，则此字段指向外部类。

    inner_classes:
        当前类所包含的内部类，以内部类的简单名作为键。

    superclass:
        解析后的父类 ClassInfo（若无继承关系，则为 None）。

    interfaces:
        当前类实现的所有接口（解析后）。

    children:
        所有直接继承自当前类的类（解析后）。

    interface_impls:
        若当前 ClassInfo 表示接口，则该字段存所有实现该接口的类。

    ------------------------------------------------------------
    """

    name: str
    package: Optional[str]
    kind: str = "class"
    content: Optional[str] = None

    superclass_name: Optional[str] = None
    interface_names: List[str] = field(default_factory=list)

    modifiers: Set[str] = field(default_factory=set)
    annotations: List[str] = field(default_factory=list)

    fields: Dict[str, FieldInfo] = field(default_factory=dict)
    methods: Dict[str, List[MethodInfo]] = field(default_factory=dict)

    span: Optional[object] = None

    outer_class: Optional["ClassInfo"] = None
    inner_classes: Dict[str, "ClassInfo"] = field(default_factory=dict)

    superclass: Optional["ClassInfo"] = None
    interfaces: List["ClassInfo"] = field(default_factory=list)
    children: List["ClassInfo"] = field(default_factory=list)
    interface_impls: List["ClassInfo"] = field(default_factory=list)

    @property
    def fqn(self) -> str:
        """
        构建类的完全限定名。
        对内部类使用：package.Outer.Inner 的形式。
        """
        pkg = f"{self.package}." if self.package else ""
        if self.outer_class:
            return f"{pkg}{self.outer_class.name}.{self.name}"
        return f"{pkg}{self.name}"

    def add_method(self, method: MethodInfo):
        """
        将方法加入当前类。
        """
        self.methods.setdefault(method.name, []).append(method)

    def __repr__(self):
        return f"ClassInfo(fqn={self.fqn})"