#!/usr/bin/env python3
"""
主分析脚本：整合所有功能，处理JSONL文件并输出文件-函数对
"""

import os
import json
import sys
from pathlib import Path
import argparse
import traceback
from datetime import datetime
import subprocess

# 导入我们的模块
sys.path.insert(0, str(Path(__file__).parent))

from git_operations import GitOperations
from patch_analyzer import PatchAnalyzer
from java_parser import JavaParser
from function_locator import ImprovedFunctionLocator


class MainAnalyzer:
    def __init__(self, project_path, output_dir=None):
        """
        初始化主分析器

        Args:
            project_path: 项目路径
            output_dir: 输出目录
        """
        self.project_path = Path(project_path).resolve()
        self.output_dir = Path(output_dir) if output_dir else self.project_path.parent / 'analysis_results'
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.final_path = self.output_dir / 'final_results.json'

        # 初始化组件
        self.git_ops = GitOperations(self.project_path)
        self.patch_analyzer = PatchAnalyzer()
        self.java_parser = JavaParser()
        self.function_locator = ImprovedFunctionLocator(self.project_path)

        # 结果存储
        self.results = []
        self.stats = {
            'total_entries': 0,
            'processed_entries': 0,
            'failed_entries': 0,
            'total_file_function_pairs': 0,
            'start_time': None,
            'end_time': None
        }

    def analyze_jsonl_file(self, jsonl_path, start_line=0, end_line=None, max_entries=None):
        """
        分析JSONL文件

        Args:
            jsonl_path: JSONL文件路径
            start_line: 起始行（0-based）
            end_line: 结束行
            max_entries: 最大处理条目数（用于测试）
        """
        jsonl_path = Path(jsonl_path).resolve()

        print(f"开始分析JSONL文件: {jsonl_path}")
        print(f"项目路径: {self.project_path}")
        print(f"输出目录: {self.output_dir}")
        print(f"起始行: {start_line}, 结束行: {end_line}, 最大条目: {max_entries}")
        print("-" * 80)

        self.stats['start_time'] = datetime.now()

        # 读取JSONL文件
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if end_line is None:
            end_line = len(lines)

        # 限制处理范围
        if max_entries:
            end_line = min(end_line, start_line + max_entries)

        # 保存当前git状态
        self.git_ops.save_current_state()

        try:
            original_state_saved = False
            original_branch = None
            original_head = None

            # 保存原始状态
            try:
                # 获取当前分支
                result = subprocess.run(
                    ['git', 'branch', '--show-current'],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True
                )
                # print(f"当前分支：{result.stdout.strip()}")
                original_branch = result.stdout.strip() or 'main'

                # 获取当前HEAD
                result = subprocess.run(
                    ['git', 'rev-parse', 'HEAD'],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True
                )
                original_head = result.stdout.strip()
                original_state_saved = True
                # print(f"保存原始状态: 分支={original_branch}, HEAD={original_head[:8]}")
            except Exception as e:
                print(f"保存状态失败: {e}")

            for i in range(start_line, min(end_line, len(lines))):
                self.stats['total_entries'] += 1
                entry_num = i + 1

                try:
                    # 在处理每个条目前重置到原始状态
                    if original_state_saved:
                        try:
                            subprocess.run(
                                ['git', 'checkout', original_branch],
                                cwd=self.project_path,
                                check=True,
                                capture_output=True,
                                text=True
                            )
                        except:
                            # 如果失败，尝试切换到master
                            try:
                                subprocess.run(
                                    ['git', 'checkout', 'main'],
                                    cwd=self.project_path,
                                    check=True,
                                    capture_output=True,
                                    text=True
                                )
                            except:
                                pass
                                
                    data = json.loads(lines[i])
                    # if data["number"] != 531:
                    #     print("skip")
                    #     continue
                    self._process_single_entry(data, entry_num)

                except json.JSONDecodeError as e:
                    print(f"[{entry_num}] JSON解析错误: {e}")
                    self.stats['failed_entries'] += 1

                except Exception as e:
                    print(f"[{entry_num}] 处理错误: {e}")
                    traceback.print_exc()
                    self.stats['failed_entries'] += 1

                # # 定期保存结果
                # if entry_num % 10 == 0:
                #     self._save_intermediate_results()

        finally:
            # 恢复git状态
            try:
                if original_state_saved and original_branch:
                    # print(f"恢复状态到分支: {original_branch}")
                    subprocess.run(
                        ['git', 'rev-parse', 'HEAD'],
                        cwd=self.project_path,
                        capture_output=True,
                        text=True
                    )
                    subprocess.run(
                        ['git', 'checkout', '-f', original_branch],
                        cwd=self.project_path,
                        check=True,
                        capture_output=True,
                        text=True
                    )
            except Exception as e:
                print(f"恢复状态失败: {e}")

            # 完成统计
            self.stats['end_time'] = datetime.now()
            self.stats['processed_entries'] = self.stats['total_entries'] - self.stats['failed_entries']

            # 保存最终结果
            self._save_final_results()
            return self.final_path

    def _process_single_entry(self, data, entry_num):
        """
        处理单个条目

        Args:
            data: JSON数据
            entry_num: 条目编号
        """
        # 提取基本信息
        pr_number = data.get('number', 'N/A')
        pr_title = data.get('title', 'N/A')
        base_sha = data.get('base', {}).get('sha')
        fix_patch = data.get('fix_patch', '')

        print('='*50)
        print(f"[{entry_num}] 处理PR #{pr_number}: {pr_title[:50]}...")

        if not base_sha:
            print(f"  [!] 缺少SHA，跳过")
            return

        if not fix_patch:
            print(f"  [!] 缺少fix_patch，跳过")
            return

        # 切换到指定SHA
        # print(f"  切换到SHA: {base_sha[:8]}")
        if not self.git_ops.checkout_sha(base_sha):
            print(f"  [!] 无法切换到SHA {base_sha[:8]}，跳过")
            return

        try:
            # 应用fix_patch到项目上
            # print(f"  应用fix_patch...")
            if not self.git_ops.apply_patch(fix_patch):
                print(f"  [!] 应用fix_patch失败，跳过")
                return

            # 分析patch并定位函数（使用应用patch后的状态）
            try:
                file_function_pairs = self.function_locator.analyze_functions_after_patch(
                    fix_patch, self.project_path
                )
            except Exception as e:
                print(f"  应用patch后分析方法失败，尝试备用方法: {e}")
                file_function_pairs = []

            # 如果没有找到，尝试备用方法
            if not file_function_pairs:
                print(f"没有找到，尝试备用方法")
                file_function_pairs = self._analyze_patch_backup(fix_patch)

            # 保存结果 - 保留原始数据中test_patch之前的所有字段，并添加file_function_pairs
            # 创建新的结果对象，复制原始数据中test_patch之前的所有字段
            entry_result = {}

            # test_patch之前的字段列表
            fields_before_test_patch = [
                'org', 'repo', 'number', 'state', 'title', 'body',
                'base', 'resolved_issues', 'fix_patch', 'hints'
            ]

            # 复制这些字段
            for field in fields_before_test_patch:
                if field in data:
                    entry_result[field] = data[field]

            # 添加我们分析的file_function_pairs
            entry_result['file_function_pairs'] = [
                {
                    'file_path': file_path,
                    'function_name': func_name,
                    'start_line': start_line
                }
                for file_path, func_name, start_line in file_function_pairs
            ]

            self.results.append(entry_result)
            self.stats['total_file_function_pairs'] += len(file_function_pairs)

            # print(f"  找到 {len(file_function_pairs)} 个文件-函数对")
            # for file_path, func_name in file_function_pairs[:5]:  # 显示前5个
            #     print(f"    ({file_path}, {func_name})")
            # if len(file_function_pairs) > 5:
            #     print(f"    ... 还有 {len(file_function_pairs) - 5} 个")

        except Exception as e:
            print(f"  分析patch失败: {e}")
            traceback.print_exc()
            raise

    def _analyze_patch_backup(self, patch_content):
        """
        备用方法分析patch（当主方法失败时使用）

        Args:
            patch_content: patch内容

        Returns:
            list: 文件-函数对列表
        """
        file_function_pairs = []

        # 解析patch获取文件信息
        files_info = self.patch_analyzer.parse_patch(patch_content)

        for file_info in files_info:
            file_path = file_info.get('file_b')
            if not file_path:
                continue

            full_path = self.project_path / file_path

            if not full_path.exists():
                print(f"  文件不存在: {file_path}")
                continue

            # 对每个hunk分析
            for hunk_info in file_info.get('hunks', []):
                # 获取修改的大致位置
                start_line = hunk_info.get('start_b', 1)

                # 查找该位置的函数
                function_info = self.java_parser.find_function_at_line(str(full_path), start_line)

                if function_info:
                    # 文件路径已经是相对路径，不需要再次转换为相对路径
                    # 但需要确保是字符串格式
                    rel_path = str(file_path)
                    if (rel_path, function_info['name']) not in file_function_pairs:
                        file_function_pairs.append((rel_path, function_info['name']))

        return file_function_pairs


    def _save_final_results(self):
        """保存最终结果"""
        # 保存完整结果
        with open(self.final_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)


        # 保存统计摘要
        stats_file = self.output_dir / 'statistics.txt'
        with open(stats_file, 'w', encoding='utf-8') as f:
            self._write_statistics(f)

        print(f"\n" + "=" * 80)
        print("分析完成!")
        print(f"完整结果已保存到: {self.final_path}")
        print(f"统计信息已保存到: {stats_file}")

        # 打印摘要
        # self._print_statistics()

    def _write_statistics(self, file_obj):
        """写入统计信息"""
        duration = None
        if self.stats['end_time'] and self.stats['start_time']:
            duration = self.stats['end_time'] - self.stats['start_time']

        file_obj.write("分析统计信息\n")
        file_obj.write("=" * 80 + "\n")
        file_obj.write(f"开始时间: {self.stats['start_time']}\n")
        file_obj.write(f"结束时间: {self.stats['end_time']}\n")
        file_obj.write(f"总耗时: {duration}\n" if duration else "总耗时: 未知\n")
        file_obj.write(f"总条目数: {self.stats['total_entries']}\n")
        file_obj.write(f"成功处理: {self.stats['processed_entries']}\n")
        file_obj.write(f"失败条目: {self.stats['failed_entries']}\n")
        file_obj.write(f"成功率: {self.stats['processed_entries'] / self.stats['total_entries'] * 100:.1f}%\n")
        file_obj.write(f"总文件-函数对数: {self.stats['total_file_function_pairs']}\n")
        file_obj.write(f"平均每条目对数: {self.stats['total_file_function_pairs'] / max(1, self.stats['processed_entries']):.1f}\n")


    def _print_statistics(self):
        """打印统计信息"""
        duration = None
        if self.stats['end_time'] and self.stats['start_time']:
            duration = self.stats['end_time'] - self.stats['start_time']

        print(f"\n统计信息:")
        print(f"  总条目数: {self.stats['total_entries']}")
        print(f"  成功处理: {self.stats['processed_entries']}")
        print(f"  失败条目: {self.stats['failed_entries']}")
        print(f"  成功率: {self.stats['processed_entries'] / self.stats['total_entries'] * 100:.1f}%")
        print(f"  总文件-函数对数: {self.stats['total_file_function_pairs']}")
        print(f"  平均每条目对数: {self.stats['total_file_function_pairs'] / max(1, self.stats['processed_entries']):.1f}")
        if duration:
            print(f"  总耗时: {duration}")
            print(f"  平均每条目耗时: {duration / max(1, self.stats['processed_entries'])}")

        # 文件统计
        file_counts = {}
        for entry in self.results:
            for pair in entry.get('file_function_pairs', []):
                file_path = pair.get('file_path', 'unknown')
                file_counts[file_path] = file_counts.get(file_path, 0) + 1

        if file_counts:
            print(f"\n最常修改的文件:")
            for file_path, count in sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"  {file_path}: {count} 次")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='分析fastjson2项目的patch，定位修改的文件和函数名')
    parser.add_argument('--project', default='fastjson2', help='项目路径')
    parser.add_argument('--jsonl', default='alibaba__fastjson2_dataset.jsonl', help='JSONL文件路径')
    parser.add_argument('--start', type=int, default=0, help='起始行数（0-based，默认0）')
    parser.add_argument('--end', type=int, default=None, help='结束行数（默认到文件末尾）')
    parser.add_argument('--max-entries', type=int, default=None, help='最大处理条目数（用于测试）')
    parser.add_argument('--output-dir', default=None, help='输出目录')

    args = parser.parse_args()

    # 创建分析器
    analyzer = MainAnalyzer(args.project, args.output_dir)

    # 分析JSONL文件
    analyzer.analyze_jsonl_file(
        jsonl_path=args.jsonl,
        start_line=args.start,
        end_line=args.end,
        max_entries=args.max_entries
    )


if __name__ == '__main__':
    main()