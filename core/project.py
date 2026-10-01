# core/project.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from loguru import logger

from core.file import FileInfo
from core.package import PackageInfo
from core.symbol_table import GlobalSymbolTable
from core.clazz import ClassInfo
from core.types import TypeInfo


@dataclass
class ProjectContext:
    """
    表示整个 Java 项目。
    支持 main 源代码与 test 源代码分开存储，
    但所有类都会统一注册到全局符号表中。
    """

    root_path: str

    # main/test 文件
    main_files: Dict[str, FileInfo] = field(default_factory=dict)
    test_files: Dict[str, FileInfo] = field(default_factory=dict)

    # main/test 包
    main_packages: Dict[str, PackageInfo] = field(default_factory=dict)
    test_packages: Dict[str, PackageInfo] = field(default_factory=dict)

    # 全局符号表：用于类型解析与继承解析
    symbols: GlobalSymbolTable = field(default_factory=GlobalSymbolTable)

    # =====================================================================
    # 文件注册（main/test）
    # =====================================================================
    def add_main_file(self, file_ctx: FileInfo):
        logger.debug(f"[main] 注册文件: {file_ctx.path}")

        self.main_files[file_ctx.path] = file_ctx

        pkg = self.main_packages.setdefault(
            file_ctx.package_name or "",
            PackageInfo(name=file_ctx.package_name or "")
        )

        pkg.files[file_ctx.path] = file_ctx

        for cls in file_ctx.classes:
            pkg.classes[cls.name] = cls
            self.symbols.register_class(cls)
            self.symbols.register_methods(cls)

    def add_test_file(self, file_ctx: FileInfo):
        logger.debug(f"[test] 注册文件: {file_ctx.path}")

        self.test_files[file_ctx.path] = file_ctx

        pkg = self.test_packages.setdefault(
            file_ctx.package_name or "",
            PackageInfo(name=file_ctx.package_name or "")
        )

        pkg.files[file_ctx.path] = file_ctx

        for cls in file_ctx.classes:
            pkg.classes[cls.name] = cls
            self.symbols.register_class(cls)
            self.symbols.register_methods(cls)

    # =====================================================================
    # 二阶段解析入口
    # =====================================================================
    def resolve_all(self):
        logger.info("【resolve】步骤 1/4：解析内部类结构 ...")
        self._resolve_inner_classes()
        logger.info("【resolve】步骤 1 完成")

        logger.info("【resolve】步骤 2/4：解析类型信息 ...")
        self._resolve_type_info()
        logger.info("【resolve】步骤 2 完成")

        logger.info("【resolve】步骤 3/4：解析继承关系 ...")
        self._resolve_inheritance()
        logger.info("【resolve】步骤 3 完成")

        logger.info("【resolve】步骤 4/4：解析方法调用（call graph） ...")
        self._resolve_method_calls()
        logger.info("【resolve】步骤 4 完成")

    # =====================================================================
    # 内部类结构
    # =====================================================================
    def _resolve_inner_classes(self):
        logger.debug("  正在处理内部类 ↔ 外部类 的绑定关系 ...")

        for cls in self.symbols.classes.values():
            parts = cls.fqn.split(".")
            if len(parts) <= 2:
                continue

            outer_name = parts[-2]
            simple = parts[-1]

            for candidate in self.symbols.classes.values():
                if candidate.name == outer_name and candidate.package == cls.package:
                    cls.outer_class = candidate
                    candidate.inner_classes[simple] = cls
                    logger.debug(f"    [内部类] {cls.fqn} 的外部类 = {candidate.fqn}")
                    break

    # =====================================================================
    # 类型解析
    # =====================================================================
    def _resolve_type_info(self):
        logger.debug("  开始为所有类的字段、方法、局部变量进行类型解析 ...")

        all_files = list(self.main_files.values()) + list(self.test_files.values())
        for fctx in all_files:
            for cls in fctx.classes:
                self._resolve_types_in_class(cls, fctx)

    def _resolve_types_in_class(self, cls: ClassInfo, file_ctx: FileInfo):
        package = file_ctx.package_name or ""
        imports = file_ctx.imports

        def resolve_type(t: Optional[TypeInfo]):
            if t is None:
                return
            if t.is_primitive:
                return
            if t.resolved_fqn:
                return

            base = t.base

            # 1) base 是全限定名
            if "." in base and self.symbols.get_class(base):
                t.resolved_fqn = base
                logger.debug(f"    [类型解析] {t.raw} 解析为 {base}")
                return

            # 2) 当前包
            candidate = f"{package}.{base}" if package else base
            if self.symbols.get_class(candidate):
                t.resolved_fqn = candidate
                logger.debug(f"    [类型解析] {t.raw} 解析为 {candidate}")
                return

            # 3) import 精确导入
            for imp in imports:
                if not imp.is_asterisk:
                    if imp.path.split(".")[-1] == base:
                        if self.symbols.get_class(imp.path):
                            t.resolved_fqn = imp.path
                            logger.debug(f"    [类型解析] {t.raw} 解析为 {imp.path}")
                            return

            # 4) import *
            for imp in imports:
                if imp.is_asterisk:
                    pkg = imp.path[:-2]
                    cand = f"{pkg}.{base}"
                    if self.symbols.get_class(cand):
                        t.resolved_fqn = cand
                        logger.debug(f"    [类型解析] {t.raw} 解析为 {cand}")
                        return

            # 5) java.lang 默认包
            jl = f"java.lang.{base}"
            if self.symbols.get_class(jl):
                t.resolved_fqn = jl
                logger.debug(f"    [类型解析] {t.raw} 解析为 {jl}")
                return

            logger.warning(f"    [类型解析失败] {t.raw} 无法解析为已知类")

        # 字段
        for field in cls.fields.values():
            resolve_type(field.type)

        # 方法
        for method_group in cls.methods.values():
            for m in method_group:
                resolve_type(m.return_type)
                for p in m.parameters:
                    resolve_type(p.type)
                for lv in m.local_variables:
                    resolve_type(lv.type)

    # =====================================================================
    # 继承链解析：extends & implements
    # =====================================================================
    def _resolve_inheritance(self):
        logger.debug("  开始为所有类建立 extends / implements 关系 ...")

        for cls in self.symbols.classes.values():

            # ----------------- superclass -----------------
            if cls.superclass_name:
                fq = self._resolve_fqn(cls, cls.superclass_name)
                sup = self.symbols.get_class(fq) if fq else None
                if sup:
                    cls.superclass = sup
                    sup.children.append(cls)
                    logger.debug(f"    [继承] {cls.fqn} extends {sup.fqn}")

            # ----------------- interfaces -----------------
            for name in cls.interface_names:
                fq = self._resolve_fqn(cls, name)
                itf = self.symbols.get_class(fq) if fq else None
                if itf:
                    cls.interfaces.append(itf)
                    itf.interface_impls.append(cls)
                    logger.debug(f"    [实现] {cls.fqn} implements {itf.fqn}")

    def _resolve_fqn(self, cls: ClassInfo, name: str) -> Optional[str]:
        """
        尝试把一个简单类名解析成全限定名。
        """
        # 如果 name 已经是 FQN
        if "." in name and self.symbols.get_class(name):
            return name

        # 当前包
        if cls.package:
            cand = f"{cls.package}.{name}"
            if self.symbols.get_class(cand):
                return cand

        # import 查找
        for fctx in list(self.main_files.values()) + list(self.test_files.values()):
            if cls in fctx.classes:
                for imp in fctx.imports:
                    if not imp.is_asterisk and imp.path.split(".")[-1] == name:
                        return imp.path

        return None

    def _resolve_method_calls(self):
        for cls_fqn, cls in self.symbols.classes.items():
            for _, mlist in cls.methods.items():
                for m in mlist:
                    caller_key = f"{cls_fqn}#{m.signature_key()}"

                    for call in m.method_calls:
                        target_fqn = None

                        # qualifier 处理
                        if call.qualifier:
                            if call.qualifier in cls.fields:
                                target_fqn = cls.fields[call.qualifier].type.resolved_fqn
                            else:
                                for lv in m.local_variables:
                                    if lv.name == call.qualifier:
                                        target_fqn = lv.type.resolved_fqn
                                        break

                        # 无 qualifier → 默认是当前类
                        if not target_fqn:
                            target_fqn = cls_fqn

                        call.resolved_fqn = target_fqn

                        # 找被调方法
                        candidates = []
                        for key in self.symbols.methods:
                            if key.startswith(f"{target_fqn}#{call.method_name}("):
                                candidates.append(key)

                        if len(candidates) == 1:
                            callee_key = candidates[0]
                            call.resolved_method_signature = callee_key.split("#", 1)[1]
                            self.symbols.add_method_call(caller_key, call)