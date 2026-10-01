#!/usr/bin/env python3
"""
统计函数覆盖率提升的PR个数

比较 fastjson2_1.json 和 origin_coverage 中函数的 missed_lines，
如果一个PR中任意一个函数的missed_lines减少了，则该PR算作提升。
"""

import json
import re
from typing import Dict, List, Set
import glob


def parse_instance_id(instance_id: str) -> int:
    """
    从instance_id中提取pr_number
    格式: mswebench/alibaba_m_fastjson2:pr-2285
    """
    match = re.search(r'pr-(\d+)', instance_id)
    if match:
        return int(match.group(1))
    return None


def parse_method_name(method_name: str) -> tuple:
    """
    从method_name中提取file_path和function_name
    格式: core/src/main/java/com/alibaba/fastjson2/writer/ObjectWriterBaseModule.java#getBeanInfo(BeanInfo,Class)
    """
    if '#' in method_name:
        parts = method_name.split('#', 1)
        file_path = parts[0]
        func_name = parts[1]
        return file_path, func_name
    return None, None


def main():
    
    project_list = ['fastjson2', 'dubbo', 'jackson-databind', 'jackson-core', 'jackson-dataformat-xml', 'gson', 'nacos', 'guava']
    # project_list = ['nacos', 'guava']
    strategy = 'ours' # ours ours_wo_re ours_wo_con ours_wo_str
    for project_name in project_list:
        print(f"Processing project: {project_name}")
        # 读取文件
        with open(f'./{strategy}/{project_name}.json', 'r') as f:
            after_data = json.load(f)

        with open(f'./before/{project_name}_coverage.json', 'r') as f:
            before_data = json.load(f)

        # 构建before_data的索引: {(pr_num, file_path, func_name): missed_lines}
        before_index = {}
        for key, value in before_data.items():
            # key格式: 2775_core/src/main/java/...#parseObject(String,Type,...)
            match = re.match(r'(\d+)_(.+)#(.+)', key)
            if match:
                pr_num = int(match.group(1))
                file_path = match.group(2)
                func_name = match.group(3)
                missed_lines = value.get('missed_lines', [])
                before_index[(pr_num, file_path, func_name)] = missed_lines

        # print(f"Before data index size: {len(before_index)}")
        # print("Sample before keys:", list(before_index.keys())[:3])

        # 比较after_data中的每个函数
        improved_prs = set()
        pr_details = []

        for case in after_data:
            instance_id = case.get('instance_id', '')
            method_name = case.get('method_name', '')
            coverage_info = case.get('coverage_info', {})

            pr_num = parse_instance_id(instance_id)
            if pr_num is None:
                continue

            file_path, func_name = parse_method_name(method_name)
            if file_path is None or func_name is None:
                continue

            after_missed_lines = coverage_info.get('missed_lines', [])

            # 在before中查找匹配的函数
            before_key = (pr_num, file_path, func_name)
            before_missed_lines = before_index.get(before_key, None)

            # print(f"\nChecking PR-{pr_num}, func={func_name[:30]}...")
            # print(f"  Before key exists: {before_key in before_index}")
            # if before_key in before_index:
            #     print(f"  Before missed: {len(before_missed_lines)}, After missed: {len(after_missed_lines)}")

            if before_missed_lines is not None:
                before_count = len(before_missed_lines)
                after_count = len(after_missed_lines)

                if after_count < before_count:
                    improved_prs.add(pr_num)
                    pr_details.append({
                        'pr_number': pr_num,
                        'function_name': func_name,
                        'file_path': file_path,
                        'before_missed_lines_count': before_count,
                        'after_missed_lines_count': after_count,
                        'improved_count': before_count - after_count
                    })
                    # print(f"  --> IMPROVED!")

        # 输出结果
        print("\n" + "=" * 60)
        print("覆盖率提升统计")
        print("=" * 60)
        print(f"覆盖率提升的PR个数: {len(improved_prs)}")
        print(f"提升的PR列表: {sorted(improved_prs)}")
        print()



if __name__ == "__main__":
    main()
