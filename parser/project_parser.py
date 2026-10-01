# parser/project_parser.py
from __future__ import annotations
from pathlib import Path
from typing import Optional
from loguru import logger

from tree_sitter import Parser
from configs.config import JAVA_LANGUAGE

from core.project import ProjectContext
from core.file import FileInfo
from parser.file_parser import parse_file
import pickle


class JavaProjectParser:
    """
    支持 main/test 分别解析的项目解析器。
    """

    def __init__(self):
        self.parser = Parser()
        self.parser.language = JAVA_LANGUAGE

    def parse_project(self, project_root: str, main_src: str, test_src: str) -> ProjectContext:
        logger.info("开始解析 Java 项目 ...")
        logger.info(f"项目根路径: {project_root}")
        logger.info(f"业务代码路径（main）: {main_src}")
        logger.info(f"测试代码路径（test）: {test_src}")

        project = ProjectContext(root_path=project_root)

        # ---------- 解析 main ----------
        logger.info("开始扫描业务代码文件（main） ...")
        main_files = list(Path(main_src).rglob("*.java"))
        logger.info(f"共找到 {len(main_files)} 个 main 源文件")

        for f in main_files:
            logger.debug(f"[main] 解析文件: {f}")
            file_ctx = self.parse_java_file(str(f))
            if file_ctx:
                project.add_main_file(file_ctx)

        # ---------- 解析 test ----------
        logger.info("开始扫描测试代码文件（test） ...")
        test_files = list(Path(test_src).rglob("*.java"))
        logger.info(f"共找到 {len(test_files)} 个 test 源文件")

        for f in test_files:
            logger.debug(f"[test] 解析文件: {f}")
            file_ctx = self.parse_java_file(str(f))
            if file_ctx:
                project.add_test_file(file_ctx)

        logger.info("文件解析完成，开始执行二阶段语义解析 resolve_all() ...")
        project.resolve_all()
        logger.info("项目语义解析全部完成！")

        return project

    def parse_java_file(self, file_path: str) -> Optional[FileInfo]:
        try:
            code = Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"文件读取失败: {file_path}, 错误: {e}")
            return None

        return parse_file(file_path, code, self.parser)