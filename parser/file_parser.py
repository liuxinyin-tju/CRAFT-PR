# parser/file_parser.py
from __future__ import annotations

from core.file import FileInfo, ImportInfo
from parser.class_parser import parse_classes
from parser.utils import query_captures

PACKAGE_QUERY = """
(package_declaration) @package
"""

IMPORT_QUERY = """
(import_declaration) @import
"""


def parse_file(path: str, code: str, parser) -> FileInfo:
    """
    解析 Java 文件得到 FileInfo：
        - package
        - imports
        - classes（含内部类）
    """
    tree = parser.parse(code.encode("utf-8"))
    root = tree.root_node

    # ---------- package ----------
    pkg_nodes = query_captures(PACKAGE_QUERY, "package", root)
    package_name = None
    if pkg_nodes:
        txt = pkg_nodes[0].text.decode("utf-8")
        package_name = txt.split()[1].rstrip(";")

    # ---------- imports ----------
    imports = []
    import_nodes = query_captures(IMPORT_QUERY, "import", root)
    for node in import_nodes:
        txt = node.text.decode("utf-8").replace(";", "").strip()
        parts = txt.split()
        is_static = False
        path_str = ""

        if len(parts) == 2:                   # import a.b
            path_str = parts[1]
        elif len(parts) >= 3 and parts[1] == "static":  # import static a.b
            is_static = True
            path_str = parts[2]

        if path_str:
            imports.append(
                ImportInfo(
                    path=path_str,
                    is_asterisk=path_str.endswith(".*"),
                    static_import=is_static,
                    content=node.text.decode("utf-8"),
                )
            )

    # ---------- classes ----------
    classes = parse_classes(root, code)
    for c in classes:
        c.package = package_name

    return FileInfo(
        path=path,
        package_name=package_name,
        imports=imports,
        classes=classes,
        content=code,
    )