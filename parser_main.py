from __future__ import annotations
import argparse
import os
from loguru import logger
import json
import re
import pickle

from parser.project_parser import JavaProjectParser


def print_project_summary(project):
    """
    中文输出项目解析结果概览。
    """
    logger.info("========== 项目解析摘要 ==========")
    logger.info(f"项目根路径: {project.root_path}")

    # main 代码统计
    logger.info("【业务代码（main）】")
    logger.info(f"  文件数量: {len(project.main_files)}")
    logger.info(f"  包数量: {len(project.main_packages)}")
    logger.info(f"  类数量: {len([c for p in project.main_packages.values() for c in p.classes.values()])}")

    # test 代码统计
    logger.info("【测试代码（test）】")
    logger.info(f"  文件数量: {len(project.test_files)}")
    logger.info(f"  包数量: {len(project.test_packages)}")
    logger.info(f"  类数量: {len([c for p in project.test_packages.values() for c in p.classes.values()])}")

    # 全局类数量（符号表）
    logger.info("【全局符号表】")
    logger.info(f"  已注册类数量: {len(project.symbols.classes)}")
    logger.info("==================================")


def print_some_details(project, max_classes=5):
    """
    显示一些类的详细结构，方便检查解析是否正确。
    """
    logger.info("展示部分类的详细解析结果（仅展示前几个类）：")

    count = 0
    for fpath, fctx in project.main_files.items():
        for cls in fctx.classes:
            logger.info(f"[类] {cls.fqn}")
            logger.info(f"  类型: {cls.kind}")
            logger.info(f"  父类: {cls.superclass_name}")
            logger.info(f"  实现接口: {cls.interface_names}")
            logger.info(f"  字段: {list(cls.fields.keys())}")
            logger.info(f"  方法: {list(cls.methods.keys())}")

            count += 1
            if count >= max_classes:
                logger.info("（展示结束，仅显示部分类）")
                return


def parser_main(root_dir, raw_data_path, output_file_path, pr_number):
    # 从patch中获取解析路径
    fix_patch = ''
    main_src = ''
    test_src = ''
    with open(raw_data_path, 'r') as f:
        for line in f:
            content = json.loads(line)
            if pr_number == content["number"]:
                fix_patch = content["fix_patch"]
    
    pattern = r'diff --git a/(\S+) b/\1'
    matches = re.findall(pattern, fix_patch)
    for match in matches:
        if 'src' not in match:
            continue
        result = match.split('src')
        project_root = root_dir + result[0]
        if '/guava' in project_root:
            main_src = project_root + 'src'
            test_src = project_root + 'test'
            test_src = test_src.replace('/guava/test', '/guava-tests/test')
        else:
            main_src = project_root + 'src/main'
            test_src = project_root + 'src/test'
        break
    # 基本路径检查
    if not os.path.exists(main_src):
        logger.error(f"业务代码路径不存在: {main_src}")
        return

    if not os.path.exists(test_src):
        logger.error(f"测试代码路径不存在: {test_src}")
        return

    logger.info("初始化解析器 ...")
    project_parser = JavaProjectParser()

    logger.info("开始解析 Java 项目 ...")
    project = project_parser.parse_project(
        project_root=project_root,
        main_src=main_src,
        test_src=test_src
    )

    logger.info("解析完成。")

    with open(output_file_path, 'wb') as f:
        pickle.dump(project, f)
    
    # 打印摘要
    print_project_summary(project)

    # 展示部分详细结果
    print_some_details(project)


if __name__ == "__main__":
    # 项目的根目录和数据集的路径
    raw_data_path = "/data/multi-swe-bench/tmp/raw_dataset/apache__dubbo_dataset.jsonl"
    root_dir = "/data/multi-swe-bench/tmp/repos/apache/dubbo/"
    output_file = "/data/Java-Parser/output/dubbo_7041.pkl"
    parser_main(root_dir, raw_data_path, output_file)