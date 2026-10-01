import re


class TestResultParser:
    """测试结果解析器"""
    
    @staticmethod
    def parse(text: str) -> dict:
        """
        解析测试结果，返回包含统计信息和错误详情的字典
        
        支持格式：
        [INFO] Results:
        [ERROR] Errors: 
        [ERROR]   <错误详情>
        [ERROR] Tests run: X, Failures: X, Errors: X, Skipped: X
        """
        result = {
            'total': 0,
            'failures': 0,
            'errors': 0,
            'skipped': 0,
            'error_details': []
        }
        
        # 尝试匹配完整的统计行
        stats_match = re.search(
            r'(?:\[(?:ERROR|INFO)\]\s?)?Tests run:\s*(\d+),\s*'
            r'Failures:\s*(\d+),\s*'
            r'Errors:\s*(\d+),\s*'
            r'Skipped:\s*(\d+)',
            text
        )
        
        if stats_match:
            result['total'] = int(stats_match.group(1))
            result['failures'] = int(stats_match.group(2))
            result['errors'] = int(stats_match.group(3))
            result['skipped'] = int(stats_match.group(4))
        
        # 提取错误详情
        # 匹配 [ERROR] 后面不是"Tests run"或"Errors:"的内容
        error_pattern = r'\[ERROR\]\s+(?!Tests run:)(?!Errors:\s*)(?!Failures:\s*)(.+?)(?=\n\[(?:INFO|ERROR)\]|\Z)'
        error_matches = re.findall(error_pattern, text, re.DOTALL)
        
        for error in error_matches:
            error = error.strip()
            if error:
                result['error_details'].append(error)
        
        return result
    
    @staticmethod
    def extract_from_full_log(log_text: str) -> dict|None:
        """
        从完整的日志中提取测试结果部分
        """
        # 查找最后一个Results部分
        start_pattern = r'Results\s?:\n'
        start_matches = list(re.finditer(start_pattern, log_text, re.DOTALL))
        if list(start_matches) == []:
            # 如果没有找到开始标记
            return None
        start_match = list(start_matches)[-1]
        
        
        stats_pattern = r'(?:\[(?:ERROR|INFO)\]\s?)?Tests run:\s*\d+,\s*Failures:\s*\d+,\s*Errors:\s*\d+,\s*Skipped:\s*\d+'
        # 从开始位置向后搜索统计行
        remaining_text = log_text[start_match.start():]
        stats_match = re.search(stats_pattern, remaining_text)
        
        if not stats_match:
            # 如果没有找到统计行，返回从开始到结尾的部分
            results_section = remaining_text
        else:
            end_pos = stats_match.end()
            results_section = remaining_text[:end_pos]
        
        result = TestResultParser.parse(results_section)
        
        return result

if __name__ == "__main__":
    file = "/data/gaoshutao/liuxinyin/multi-swe-bench/tmp/workdir/alibaba/fastjson2/instances_compile_pass/pr-82/run0.log" #test-patch fix-patch
    with open(file, 'r') as f:
        log_text = f.read()

    parser = TestResultParser()
    result = parser.extract_from_full_log(log_text)
    
    if result is not None:

        print("解析结果:")
        print(f"总计: {result['total']}")
        print(f"失败: {result['failures']}")
        print(f"错误: {result['errors']}")
        print(f"跳过: {result['skipped']}")
        print(f"错误详情: {result['error_details']}")