# core/file.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from core.clazz import ClassInfo


@dataclass
class ImportInfo:
    """
    Java import 语句的信息。

    path:
        导入的路径，例如：
            "java.util.List"
            "com.example.repo.*"

    is_asterisk:
        是否是 ".*" 形式的通配导入。

    static_import:
        是否为 static import，例如：
            import static java.lang.Math.*;
    """

    path: str
    content: Optional[str] = None
    is_asterisk: bool = False
    static_import: bool = False

    def __repr__(self):
        return f"ImportInfo(path={self.path})"


@dataclass
class FileInfo:
    """
    表示一个 Java 源文件。

    ------------------------------------------------------------
    字段含义：

    path:
        文件在磁盘中的绝对路径。

    package_name:
        文件声明的 package 名。
        若没有 package 声明，值为 None。

    imports:
        文件中所有 import 的列表（ImportInfo）。

    classes:
        当前文件中所有顶级 class/interface/enum/record。
        每个节点都是一个 ClassInfo。
    """

    path: str
    package_name: Optional[str]
    imports: List[ImportInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    content: Optional[str] = None

    def __repr__(self):
        return f"FileInfo(path={self.path}, classes={len(self.classes)})"