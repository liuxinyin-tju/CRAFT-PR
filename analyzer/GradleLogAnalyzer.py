import re
import os
import sys
from typing import Dict, List, Tuple, Optional


class GradleLogAnalyzer:
    """
    Gradle测试日志分析器

    用于分析Gradle项目运行日志，提取测试执行结果。
    支持格式: org.example.TestClass > testMethod PASSED/FAILED
    """

    def __init__(self):
        # 正则表达式模式，用于匹配单个测试用例执行结果
        # 格式: org.logstash.instrument.metrics.timer.ConcurrentLiveTimerMetricTest > testReturnValue PASSED
        self.test_case_pattern = re.compile(
            r'^([\w\.]+)\s*>\s*([\w_]+)\s+(PASSED|FAILED|SKIPPED)$'
        )

        # 正则表达式模式，用于匹配汇总统计行
        # 格式: 79 tests completed, 2 failed, 2 skipped
        self.summary_pattern = re.compile(
            r'(\d+)\s+tests\s+completed,\s*(\d+)\s+failed,\s*(\d+)\s+skipped'
        )

        # 匹配更详细的汇总格式: Results: FAILURE (79 tests, 75 successes, 2 failures, 2 skipped)
        self.detail_summary_pattern = re.compile(
            r'Results:\s+\w+\s*\((\d+)\s+tests,\s*(\d+)\s+successes,\s*(\d+)\s+failures,\s*(\d+)\s+skipped\)'
        )

        # 正则表达式模式，用于匹配Gradle编译结果
        # 格式：BUILD SUCCESSFUL 或 BUILD FAILED
        self.build_pattern = re.compile(r'(BUILD SUCCESSFUL|BUILD FAILED)', re.IGNORECASE)

        # 正则表达式模式，用于匹配编译错误
        self.compilation_error_pattern = re.compile(r'COMPILATION ERROR', re.IGNORECASE)
        self.build_failure_pattern = re.compile(r'FAILURE:', re.IGNORECASE)

    def parse_log_file(self, log_path: str) -> Dict[str, Dict[str, int]]:
        """
        解析Gradle日志文件，提取所有测试类的执行结果

        Args:
            log_path: 日志文件路径

        Returns:
            字典，键为测试类全名(或简单类名)，值为包含测试结果的字典
        """
        if not os.path.exists(log_path):
            print(f"错误：日志文件不存在: {log_path}")
            return {}

        test_results = {}

        # 用于追踪每个测试类的统计结果
        class_stats = {}

        try:
            # 尝试不同编码读取文件
            encodings = ['utf-8', 'gbk', 'latin-1']
            content = None

            for encoding in encodings:
                try:
                    with open(log_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue

            if content is None:
                # 如果所有编码都失败，使用二进制模式
                with open(log_path, 'rb') as f:
                    content = f.read().decode('utf-8', errors='ignore')

            lines = content.splitlines()

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # 移除行号前缀等无关字符
                line = line.strip(' \t\r\n')

                # 尝试匹配测试用例执行结果
                test_case_match = self.test_case_pattern.search(line)
                if test_case_match:
                    test_class_full = test_case_match.group(1)
                    test_method = test_case_match.group(2)
                    test_result = test_case_match.group(3)

                    # 提取简单类名（最后一个点之后的部分）
                    test_class_simple = test_class_full.split('.')[-1] if '.' in test_class_full else test_class_full

                    # 使用完整类名作为键，避免类名重复
                    if test_class_full not in class_stats:
                        class_stats[test_class_full] = {
                            'simple_name': test_class_simple,
                            'total': 0,
                            'passed': 0,
                            'failed': 0,
                            'skipped': 0
                        }

                    # 更新统计
                    class_stats[test_class_full]['total'] += 1
                    if test_result == 'PASSED':
                        class_stats[test_class_full]['passed'] += 1
                    elif test_result == 'FAILED':
                        class_stats[test_class_full]['failed'] += 1
                    elif test_result == 'SKIPPED':
                        class_stats[test_class_full]['skipped'] += 1

                # 尝试匹配详细的汇总统计行（用于验证）
                detail_summary_match = self.detail_summary_pattern.search(line)
                if detail_summary_match:
                    total_tests = int(detail_summary_match.group(1))
                    successes = int(detail_summary_match.group(2))
                    failures = int(detail_summary_match.group(3))
                    skipped = int(detail_summary_match.group(4))
                    print(f"找到详细汇总: 总测试数={total_tests}, 成功={successes}, 失败={failures}, 跳过={skipped}")

                # 尝试匹配简单汇总统计行（用于验证）
                summary_match = self.summary_pattern.search(line)
                if summary_match:
                    total_tests = int(summary_match.group(1))
                    failed = int(summary_match.group(2))
                    skipped = int(summary_match.group(3))
                    print(f"找到汇总: 总测试数={total_tests}, 失败={failed}, 跳过={skipped}")

            # 转换格式：使用简单类名作为键
            # 注意：可能会有同名的测试类（在不同包中），这里使用完整类名作为键
            for class_full, stats in class_stats.items():
                test_results[class_full] = {
                    'total': stats['total'],
                    'passed': stats['passed'],
                    'failed': stats['failed'],
                    'skipped': stats['skipped']
                }

        except Exception as e:
            print(f"解析日志文件时出错: {e}")
            return {}

        return test_results

    def get_test_class_stats(self, log_path: str, test_class_name: str) -> Optional[Dict[str, int]]:
        """
        获取指定测试类的统计信息（支持完整类名或简单类名）

        Args:
            log_path: 日志文件路径
            test_class_name: 测试类名称（支持完整类名或简单类名）
        """
        test_results = self.parse_log_file(log_path)

        if not test_results:
            return None

        # 如果直接匹配完整类名
        if test_class_name in test_results:
            return test_results[test_class_name]

        # 尝试匹配简单类名
        for class_full, stats in test_results.items():
            simple_name = class_full.split('.')[-1] if '.' in class_full else class_full
            if test_class_name.lower() == simple_name.lower():
                return stats

        # 尝试部分匹配
        for class_full, stats in test_results.items():
            if test_class_name.lower() in class_full.lower():
                return stats

        return None

    def get_all_classes_stats(self, log_path: str) -> Dict[str, Dict[str, int]]:
        """
        获取所有测试类的统计信息

        Args:
            log_path: 日志文件路径

        Returns:
            字典，键为测试类名，值为统计信息
        """
        return self.parse_log_file(log_path)

    def is_compilation_success(self, log_path: str) -> Tuple[bool, str]:
        """
        检查日志文件中的Gradle编译是否成功

        Args:
            log_path: 日志文件路径

        Returns:
            Tuple[bool, str]: (是否编译成功, 状态信息)
            - 如果编译成功，返回 (True, "BUILD SUCCESSFUL")
            - 如果编译失败，返回 (False, "BUILD FAILED")
            - 如果无法确定，返回 (False, "UNKNOWN")
        """
        if not os.path.exists(log_path):
            return (False, "LOG FILE NOT FOUND")

        try:
            encodings = ['utf-8', 'gbk', 'latin-1']
            content = None

            for encoding in encodings:
                try:
                    with open(log_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue

            if content is None:
                with open(log_path, 'rb') as f:
                    content = f.read().decode('utf-8', errors='ignore')

            lines = content.splitlines()

            has_compilation_error = False
            has_build_failure = False
            build_success_found = False
            build_failure_found = False

            for line in lines:
                line_stripped = line.strip()

                if self.compilation_error_pattern.search(line_stripped):
                    has_compilation_error = True

                build_match = self.build_pattern.search(line_stripped)
                if build_match:
                    if "BUILD SUCCESSFUL" in build_match.group(1).upper():
                        build_success_found = True
                    elif "BUILD FAILED" in build_match.group(1).upper():
                        build_failure_found = True

                if self.build_failure_pattern.search(line_stripped):
                    has_build_failure = True

            if has_compilation_error:
                return (False, "COMPILATION ERROR")
            elif has_build_failure:
                return (False, "BUILD FAILED")
            elif build_success_found:
                return (True, "BUILD SUCCESSFUL")
            elif build_failure_found:
                return (False, "BUILD FAILED")
            else:
                return (False, "UNKNOWN")

        except Exception as e:
            return (False, f"ERROR: {e}")


def main():
    """
    主函数
    """

    # 创建分析器实例
    analyzer = GradleLogAnalyzer()
    log_path = sys.argv[1]

    if len(sys.argv) == 3:
        # 分析单个文件中的指定测试类
        test_class_name = sys.argv[2]
        stats = analyzer.get_test_class_stats(log_path, test_class_name)

        if stats:
            print(f"\n测试类: {test_class_name}")
            print(f"测试用例总数: {stats['total']}")
            print(f"通过的测试用例数: {stats['passed']}")
            print(f"未通过的测试用例数: {stats['failed']}")
            print(f"跳过的测试用例数: {stats['skipped']}")
        else:
            print(f"未找到测试类 '{test_class_name}' 的统计信息")
    else:
        # 显示所有测试类的统计信息
        all_stats = analyzer.get_all_classes_stats(log_path)

        if all_stats:
            print("\n所有测试类统计信息:")
            print("-" * 80)
            print(f"{'测试类名':<60} {'总数':<6} {'通过':<6} {'失败':<6} {'跳过':<6}")
            print("-" * 80)

            for class_name, stats in all_stats.items():
                print(f"{class_name:<60} {stats['total']:<6} {stats['passed']:<6} {stats['failed']:<6} {stats['skipped']:<6}")

            # 计算总数
            total_tests = sum(stats['total'] for stats in all_stats.values())
            total_passed = sum(stats['passed'] for stats in all_stats.values())
            total_failed = sum(stats['failed'] for stats in all_stats.values())
            total_skipped = sum(stats['skipped'] for stats in all_stats.values())

            print("-" * 80)
            print(f"{'总计':<60} {total_tests:<6} {total_passed:<6} {total_failed:<6} {total_skipped:<6}")
        else:
            print("未找到任何测试类统计信息")


if __name__ == "__main__":
    main()