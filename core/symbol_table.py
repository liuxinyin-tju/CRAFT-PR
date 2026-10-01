from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, List

from core.clazz import ClassInfo
from core.method import MethodInfo, MethodCallInfo


@dataclass
class GlobalSymbolTable:
    """
    全局符号表：类表 + 方法表 + 调用图
    """
    classes: Dict[str, ClassInfo] = field(default_factory=dict)
    methods: Dict[str, MethodInfo] = field(default_factory=dict)
    method_calls: Dict[str, List[MethodCallInfo]] = field(default_factory=dict)

    # 注册类
    def register_class(self, cls: ClassInfo):
        self.classes[cls.fqn] = cls

    def get_class(self, fqn: str) -> Optional[ClassInfo]:
        return self.classes.get(fqn)

    # 注册类中的方法
    def register_methods(self, cls: ClassInfo):
        for _, method_list in cls.methods.items():
            for m in method_list:
                key = f"{cls.fqn}#{m.signature_key()}"
                self.methods[key] = m
                if key not in self.method_calls:
                    self.method_calls[key] = []

    def get_method(self, key: str):
        return self.methods.get(key)

    def add_method_call(self, caller_key: str, call_info: MethodCallInfo):
        if caller_key not in self.method_calls:
            self.method_calls[caller_key] = []
        self.method_calls[caller_key].append(call_info)

    def get_callers_of(self, callee_key: str):
        return [
            caller
            for caller, calls in self.method_calls.items()
            if any(call.resolved_method_signature == callee_key for call in calls)
        ]