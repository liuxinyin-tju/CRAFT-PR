#!/usr/bin/env python3
"""
运行分析的简化脚本
使用示例：
  python run_analysis.py --max-entries 10     # 分析前10条记录
  python run_analysis.py --start 100 --end 200  # 分析100-200条记录
  python run_analysis.py --all                 # 分析所有记录（需要很长时间）
"""

import sys
import os
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

def patch_analysis(org_name, project_name):
    """主函数"""

    project_dir =  f"./multi_swe_bench/tmp/repos/{org_name}/{project_name}/"
    jsonl = f"./multi_swe_bench/tmp/raw_dataset/{org_name}__{project_name}_dataset.jsonl"
    output_dir = f"./locate/analysis_results/{project_name}/"
    # output_dir = "./test"


    # 导入主分析器
    from main_analyzer import MainAnalyzer

    # 创建分析器
    analyzer = MainAnalyzer(project_dir, output_dir)

    # 运行分析
    final_path = analyzer.analyze_jsonl_file(
        jsonl_path=jsonl,
        start_line=0,
        end_line=None,
        max_entries=None
    )

    # print("\n分析完成!")
    # print("输出文件:")
    # output_dir = Path(output_dir if output_dir else 'analysis_results')
    # for file in output_dir.iterdir():
    #     if file.is_file():
    #         print(f"  - {file.name}")
    return final_path

if __name__ == '__main__':
    org_name = "alibaba" #apache google alibaba apache elastic fasterxml fasterxml fasterxml google googlecontainertools mockito alibaba apache
    project_name = "fastjson2" #commons-lang guava fastjson2 dubbo logstash jackson-databind jackson-core jackson-dataformat-xml gson jib mockito nacos skywalking
    patch_analysis(org_name, project_name)
