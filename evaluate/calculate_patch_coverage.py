#!/usr/bin/env python3
"""
统计 patch 修改代码的行覆盖率

根据测试结果文件和 patch 信息文件，统计每个 focal_method 的修改行覆盖率。
"""

import argparse
import json
import re
from typing import Dict, List, Tuple, Optional
from pathlib import Path


def parse_focal_method_range(focal_method: str) -> int:
    """
    解析 focal_method 代码，返回函数的行数

    Args:
        focal_method: 函数代码字符串

    Returns:
        函数的行数
    """
    lines = focal_method.strip().split('\n')
    return len(lines)


def parse_diff_for_modified_lines(fix_patch: str, file_path: str, start_line: int, end_line: int) -> List[int]:
    """
    解析 fix_patch，找到指定文件和行范围内的修改行号

    Args:
        fix_patch: git diff 格式的 patch 字符串
        file_path: 目标文件路径
        start_line: 函数起始行号
        end_line: 函数结束行号

    Returns:
        修改后的代码的行号列表（绝对行号）
    """
    modified_lines = []

    # 提取文件路径（去除开头的 /）
    target_file = file_path.lstrip('/')

    # 按 hunk 分割 diff
    lines = fix_patch.split('\n')
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # 查找文件头
        if line.startswith('+++ b/'):
            current_file = line[6:]
            if current_file != target_file:
                i += 1
                continue

            # 找到目标文件，解析后续的 hunk
            i += 1
            while i < n:
                line = lines[i]

                # 查找 hunk 头 @@ -old_start,old_count +new_start,new_count @@
                if line.startswith('@@'):
                    match = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', line)
                    if match:
                        new_start = int(match.group(1))
                        new_count = int(match.group(2)) if match.group(2) else 1

                        # 解析 hunk 内容
                        i += 1
                        current_line = new_start

                        while i < n and not lines[i].startswith('@@') and not lines[i].startswith('diff'):
                            hunk_line = lines[i]

                            # 只关注新增的行（+ 开头），且不是 +++ 开头的行
                            if hunk_line.startswith('+') and not hunk_line.startswith('+++'):
                                # 检查是否在函数范围内
                                if start_line <= current_line <= end_line:
                                    modified_lines.append(current_line)
                                current_line += 1
                            elif hunk_line.startswith('-'):
                                # 删除的行不计入修改后的行号
                                pass
                            elif hunk_line.startswith('\\'):
                                # 处理 \ No newline at end of file
                                pass
                            else:
                                # 上下文行，行号递增
                                current_line += 1

                            i += 1

                            # 如果遇到下一个 hunk 或 diff，继续外层循环
                            if i < n and (lines[i].startswith('@@') or lines[i].startswith('diff')):
                                break
                        continue

                # 如果遇到下一个文件，停止解析
                if line.startswith('diff'):
                    break

                i += 1

        i += 1

    return modified_lines


def calculate_patch_coverage(
    test_result_file: str,
    patch_info_file: str
) -> Dict:
    """
    计算 patch 修改代码的行覆盖率

    Args:
        test_result_file: 测试结果文件路径
        patch_info_file: patch 信息文件路径

    Returns:
        包含覆盖率统计的字典
    """
    # 读取测试结果文件
    with open(test_result_file, 'r', encoding='utf-8') as f:
        test_results = json.load(f)

    # 读取 patch 信息文件
    with open(patch_info_file, 'r', encoding='utf-8') as f:
        patch_info_list = json.load(f)

    # 创建 instance_id 到 patch_info 的映射
    patch_info_map = {}
    for patch_info in patch_info_list:
        instance_id = f"mswebench/{patch_info['org']}_m_{patch_info['repo']}:pr-{patch_info['number']}"
        patch_info_map[instance_id] = patch_info

    print(patch_info_map.keys())
    # 统计结果
    results = []
    total_modified_lines = 0
    total_missed_modified_lines = 0
    method_count = 0

    for test_case in test_results:
        instance_id = test_case.get('instance_id')
        method_name = test_case.get('method_name')
        focal_method = test_case.get('focal_method')
        coverage_info = test_case.get('coverage_info')

        start_line = coverage_info.get('start_line')
        missed_lines = coverage_info.get('missed_lines')

        # 计算函数行范围
        focal_method_lines = parse_focal_method_range(focal_method)
        end_line = start_line + focal_method_lines - 1

        # 获取 patch 信息
        patch_info = patch_info_map.get(instance_id)
        if not patch_info:
            print(f"⚠️ 跳过 {method_name}: 未找到 patch 信息")
            continue

        fix_patch = patch_info.get('fix_patch')

        # 解析修改行号
        print(start_line, end_line)
        modified_lines = parse_diff_for_modified_lines(
            fix_patch,
            method_name.split('#')[0],  # 提取文件路径
            start_line,
            end_line
        )

        if not modified_lines:
            print(f"⚠️ 跳过 {method_name}: 未找到修改行")
            continue

        # 计算未覆盖的修改行
        # missed_lines 是相对行号，需要转换为绝对行号
        missed_absolute_lines = {line + start_line for line in missed_lines}
        missed_modified_lines = [line for line in modified_lines if line in missed_absolute_lines]

        # 计算覆盖率
        modified_count = len(modified_lines)
        missed_modified_count = len(missed_modified_lines)
        covered_modified_count = modified_count - missed_modified_count
        coverage_rate = (covered_modified_count / modified_count * 100) if modified_count > 0 else 0

        # 记录结果
        result = {
            'instance_id': instance_id,
            'method_name': method_name,
            'start_line': start_line,
            'end_line': end_line,
            'modified_lines': modified_lines,
            'modified_count': modified_count,
            'missed_modified_lines': missed_modified_lines,
            'missed_modified_count': missed_modified_count,
            'covered_modified_count': covered_modified_count,
            'coverage_rate': round(coverage_rate, 2)
        }
        results.append(result)

        # 累计统计
        total_modified_lines += modified_count
        total_missed_modified_lines += missed_modified_count
        method_count += 1

        print(f"✅ {method_name}: 修改行 {modified_count}, 未覆盖 {missed_modified_count}, 覆盖率 {coverage_rate:.2f}%")

    # 计算平均覆盖率
    avg_coverage = 0
    if total_modified_lines > 0:
        avg_coverage = ((total_modified_lines - total_missed_modified_lines) / total_modified_lines * 100)

    summary = {
        'method_count': method_count,
        'total_modified_lines': total_modified_lines,
        'total_missed_modified_lines': total_missed_modified_lines,
        'total_covered_modified_lines': total_modified_lines - total_missed_modified_lines,
        'average_coverage_rate': round(avg_coverage, 2),
        'details': results
    }

    return summary


def main():
    all_line = 0
    cov_line = 0
    repo_name_list = ['fastjson2']
    for project_name in repo_name_list:
        test_result = f"./ours/{project_name}.json"
        patch_info = f"../locate/results_with_requirement/{project_name}.json"


        print(f"开始统计 patch 修改代码的行覆盖率...")
        print(f"patch 信息文件: {patch_info}")
        print()

        summary = calculate_patch_coverage(
            test_result_file=test_result,
            patch_info_file=patch_info
        )

        # # 保存结果
        # with open(args.output_file, 'w', encoding='utf-8') as f:
        #     json.dump(summary, f, indent=2, ensure_ascii=False)
        if summary['total_modified_lines'] == 0:
            continue

        print()
        print("=" * 60)
        print("汇总统计:")
        print("=" * 60)
        print(f"  方法数量: {summary['method_count']}")
        print(f"  总修改行数: {summary['total_modified_lines']}")
        print(f"  未覆盖修改行数: {summary['total_missed_modified_lines']}")
        print(f"  已覆盖修改行数: {summary['total_covered_modified_lines']}")
        print(f"  平均覆盖率: {summary['average_coverage_rate']}%")
        print("=" * 60)
        
        all_line += summary['total_modified_lines']
        cov_line += summary['total_covered_modified_lines']
        # print(f"结果已保存到: {args.output_file}")
    print(f"  总的平均覆盖率: {cov_line/all_line*100}%")


if __name__ == "__main__":
    main()