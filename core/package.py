# core/package.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional

from core.file import FileInfo
from core.clazz import ClassInfo


@dataclass
class PackageInfo:
    """
    表示一个 Java 包，存储该包下所有文件和类。

    ------------------------------------------------------------
    字段含义：

    name:
        包名，例如：
            "com.example"
            "org.apache.commons.io"
        若是默认包，则 name="".

    files:
        属于该包的所有 FileInfo。
        键为文件路径。

    classes:
        属于该包的所有 ClassInfo。
        键为类的简单名称。
    """

    name: str
    content: Optional[str] = None
    files: Dict[str, FileInfo] = field(default_factory=dict)
    classes: Dict[str, ClassInfo] = field(default_factory=dict)

    def __repr__(self):
        return f"PackageInfo(name={self.name}, classes={len(self.classes)})"