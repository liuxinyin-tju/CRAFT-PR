import re
import os
import sys
from typing import Dict, List, Tuple, Optional


class TestLogAnalyzer:
    """
    测试日志分析器

    用于分析Java项目Maven运行日志，提取测试执行结果。
    """

    def __init__(self):
        # 正则表达式模式，用于匹配测试执行结果行
        # 两种格式：
        # 1. 标准格式：Tests run: 10, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.139 sec - in com.fasterxml.jackson.databind.util.TestTokenBuffer
        # 2. run.log格式：Tests run: 11, Failures: 0, Errors: 1, Skipped: 0, Time elapsed: 0.181 sec <<< FAILURE!
        self.test_pattern = re.compile(
            r'Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+).*?(?:-\s*in\s*(.+))?'
        )

        # 正则表达式模式，用于匹配Running行（run.log格式）
        # 格式：Running com.google.gson.DefaultDateTypeAdapterTest
        self.running_pattern = re.compile(r'Running\s+(.+)')


        # 正则表达式模式，用于匹配编译错误
        # 格式：[ERROR] COMPILATION ERROR 或 [ERROR] Failure 等
        self.compilation_error_pattern = re.compile(r'\[ERROR\].*COMPILATION ERROR', re.IGNORECASE)

    def parse_log_file(self, log_path: str) -> Dict[str, Dict[str, int]]:
        """
        解析日志文件，提取所有测试类的执行结果

        Args:
            log_path: 日志文件路径

        Returns:
            字典，键为测试类全名，值为包含测试结果的字典
        """
        if not os.path.exists(log_path):
            print(f"错误：日志文件不存在: {log_path}")
            return {}

        test_results = {}

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
            current_test_class = None  # 跟踪当前测试类名（用于run.log格式）

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # 移除行号前缀（如果存在）
                if line.startswith('[') or '\t' in line:
                    # 尝试分割
                    parts = line.split('\t')
                    if len(parts) > 1:
                        line = parts[-1]

                # 先尝试匹配Running行（run.log格式）
                running_match = self.running_pattern.search(line)
                if running_match:
                    current_test_class = running_match.group(1).strip()
                    continue  # 继续下一行，期望下一行是测试结果

                # 匹配测试结果行
                match = self.test_pattern.search(line)
                if match:
                    tests_run = int(match.group(1))
                    failures = int(match.group(2))
                    errors = int(match.group(3))
                    skipped = int(match.group(4))

                    # 获取测试类名
                    if match.group(5):  # 有类名（原格式）
                        test_class = match.group(5).strip().split('.')[-1]
                    elif current_test_class:  # 没有类名，但有当前跟踪的测试类（run.log格式）
                        test_class = current_test_class.strip().split('.')[-1]
                    else:
                        # 无法确定测试类名，跳过
                        continue

                    test_results[test_class] = {
                        'total': tests_run,
                        'passed': tests_run - failures - errors,  # 计算通过的测试数
                        'failed': failures + errors,  # 计算失败的测试数
                        'failures': failures,
                        'errors': errors,
                        'skipped': skipped
                    }

                    # 重置当前测试类名
                    current_test_class = None

        except Exception as e:
            print(f"解析日志文件时出错: {e}")
            return {}

        return test_results

    def get_test_class_stats(self, log_path: str, test_class_name: str) -> Optional[Dict[str, int]]:
        """
        获取指定测试类的统计信息

        Args:
            log_path: 日志文件路径
            test_class_name: 测试类名称（支持部分匹配）
        """
        test_results = self.parse_log_file(log_path)
        if test_results != {} and test_class_name in test_results:
            return test_results[test_class_name]
        else:
            return None

    def is_compilation_success(self, log_path: str) -> bool:
        """
        检查日志文件中的编译是否成功

        Args:
            log_path: 日志文件路径

        Returns:
            bool: 编译是否成功
        """

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


            lines = content.splitlines()

            # 检查是否有编译错误或BUILD FAILURE
            has_compilation_error = False

            for line in lines:
                line_stripped = line.strip()

                # 检查编译错误
                if self.compilation_error_pattern.search(line_stripped):
                    has_compilation_error = True

            # 判断编译是否成功
            if has_compilation_error:
                return False
            else:
                return True

        except Exception as e:
            return False


def main():
    """
    主函数
    """
    # 创建分析器实例
    analyzer = TestLogAnalyzer()

    # 分析单个文件中的指定测试类
    log_path = sys.argv[1]
    test_class_name = sys.argv[2]

    stats = analyzer.get_test_class_stats(log_path, test_class_name)
    if stats:
        print(f"\n测试类: {test_class_name}")
        print(f"测试用例总数: {stats['total']}")
        print(f"通过的测试用例数: {stats['passed']}")
        print(f"未通过的测试用例数: {stats['failed']}")
        print(f"跳过的测试用例数: {stats['skipped']}")




if __name__ == "__main__":
    main()