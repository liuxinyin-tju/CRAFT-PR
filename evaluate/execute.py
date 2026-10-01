#!/usr/bin/env python3
from ResultParser import TestResultParser

import subprocess
import json
import os
import sys
from pathlib import Path
import time
from LogAnalyzer import TestLogAnalyzer

def run_command(cmd):
    """执行命令"""
    print(f"\n执行命令: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(f"退出码: {result.returncode}")
    if result.stdout:
        print(f"输出:\n{result.stdout}...")
    if result.stderr:
        print(f"错误:\n{result.stderr}...")
    return result.returncode

def update_config(config_file, test_case_file, run_mode):
    """更新配置文件"""
    print(f"\n更新配置文件: {config_file}")
    with open(config_file, 'r') as f:
        config = json.load(f)
    config['test_case_files'] = str(test_case_file)
    config['mode'] = run_mode
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"test_case_files 已更新为: {test_case_file}\n"
          f"mode 已更新为: {run_mode}\n")


def clear_log_files(folder_path):
    folder_path = Path(folder_path)
    
    if not folder_path.exists() or not folder_path.is_dir():
        print("文件夹不存在或不是目录")
        return
    print(f"清空日志记录: {folder_path}")
    for root, dirs, files in os.walk(folder_path):
        root_path = Path(root)
        # 跳过根目录本身
        if root_path == folder_path:
            continue
            
        # print(f"处理目录: {root_path}")
        for file in files:
            file_path = root_path / file
            file_path.unlink()

def count_testcase_num(input_file):
    # 统计测试用例个数（字符串匹配）
    with open(input_file,'r') as f:
        files = json.load(f)
    testcase_num = 0   
    for file in files:
        test_code = file["test_code"]
        testcase_num += test_code.count("@Test")
    return testcase_num

def analyze_run_log(run_log_dir, output_file):
    dir_path = Path(run_log_dir)
    with open(output_file, 'r') as f:
        output_content = json.load(f)
    f2p_num = 0
    error_num = 0
    total_num = 0
    pr_list = set()
    pass_list = set()
    compile_pass_set = set()
    analyzer = TestLogAnalyzer()
    for folder in dir_path.iterdir():
        if folder.is_dir:
            run_list = list(folder.glob('run*.log'))
            for run_log in run_list:
                log_name = run_log.stem
                if '#' not in log_name:
                    method_name = log_name.split('_')[-1]
                else:
                    method_token = log_name.replace('_', '/')[4:]
                    file_token = method_token.split('#')[0]
                    method_name = file_token[:-4] + '.java#' + method_token.split('#')[1]
                test_class_name = ""
                for instance in output_content:
                    if  method_name == instance['method_name']:
                        test_class_name = instance['test_file_path'].split('/')[-1][:-5]
                        break
                fix_run_log = str(run_log).replace("run","fix-patch-run")
                if not os.path.exists(fix_run_log):
                    continue
                with open(fix_run_log, 'r') as f:
                    content = f.read()
                    if 'COMPILATION ERROR' not in content and len(content.splitlines()) > 5:
                        compile_pass_set.add(folder.name)
                run_stats = analyzer.get_test_class_stats(str(run_log), test_class_name)
                fix_run_stats = analyzer.get_test_class_stats(fix_run_log, test_class_name)
                if run_stats is not None and fix_run_stats is not None:
                    print("===========================日志解析成功")
                    total_num += fix_run_stats['total']
                    error_num += fix_run_stats['failed']
                    
                    run_failed = run_stats['failed']
                    fix_failed = fix_run_stats['failed']
                    if fix_run_stats['total'] > 0 and fix_failed == 0:
                        folder_name = folder.name
                        pr_num = folder_name.split('-')[-1]
                        pass_list.add(pr_num)
                    if fix_failed < run_failed:
                        f2p_num += run_failed - fix_failed
                        folder_name = folder.name
                        pr_num = folder_name.split('-')[-1]
                        pr_list.add(pr_num)
                        print(f"✅ f2p 日志路径：{fix_run_log}")
                elif run_stats is None and fix_run_stats is not None:
                    total_num += fix_run_stats['total']
                    error_num += fix_run_stats['failed']
                    
                    fix_passed = fix_run_stats['passed']
                    if fix_run_stats['total'] > 0 and fix_run_stats['failed'] == 0:
                        folder_name = folder.name
                        pr_num = folder_name.split('-')[-1]
                        pass_list.add(pr_num)
                    if fix_passed > 0:
                        f2p_num += fix_passed
                        folder_name = folder.name
                        pr_num = folder_name.split('-')[-1]
                        pr_list.add(pr_num)
                        print(f"✅ f2p 日志路径：{fix_run_log}")
                else:
                    print(f"日志解析失败: {fix_run_log}")
                
                
    return total_num, f2p_num, error_num, pr_list, compile_pass_set, pass_list
                
def exec_swe_bench(config_file, test_case_file, run_log_dir, mode):
    print(f"\n1. 执行 build_dataset.py")
    # 更新配置文件
    update_config(config_file, test_case_file, mode)
    # 清空原有日志
    clear_log_files(run_log_dir)
    # 执行 build_dataset.py
    cmd_build = f"python /data/gaoshutao/liuxinyin/multi-swe-bench/multi_swe_bench/harness/build_dataset.py "
    cmd_build += f"--config {config_file}"
    
    if run_command(cmd_build) != 0:
        print("build_dataset.py 执行失败")
    
    

def main():

    # 修改参数
    baseline_name = "ours" #ours ours_wo_con ours_wo_re ours_wo_str ours_qwen ours_gpt
    pair_list = [('fasterxml', 'jackson-dataformat-xml'), ('google', 'gson'), ('apache', 'dubbo'), ('alibaba', 'fastjson2'), ('fasterxml', 'jackson-core'), ('fasterxml', 'jackson-databind'), ('google', 'guava'), ('alibaba', 'nacos')]
    # pair_list = [('google', 'guava')]

    for org_name, project_name in pair_list:
    # org_name = "alibaba" #alibaba apache elastic fasterxml fasterxml fasterxml google googlecontainertools mockito
    # project_name = "fastjson2" # fastjson2 dubbo logstash jackson-databind jackson-core jackson-dataformat-xml gson jib mockito
    
        config_file = f"../multi_swe_bench/config/dataset_config_{project_name}.json"
        output_dir = f"./{baseline_name}/"
        run_log_dir = f"../multi_swe_bench/tmp/workdir/{org_name}/{project_name}/instances/" 
        
        summary_path_list = []
        if baseline_name == "ours":
            summary_path_list.append(output_dir + f"{project_name}.json")
        elif baseline_name == "ours_wo_con":
            summary_path_list.append(output_dir + f"{project_name}_0.json")
        elif baseline_name == "ours_wo_re":
            summary_path_list.append(output_dir + f"{project_name}_0.json")
        elif baseline_name == "ours_wo_str":
            summary_path_list.append(output_dir + f"{project_name}.json")
        elif baseline_name == "ours_qwen":
            summary_path_list.append(output_dir + f"{project_name}_0.json")
        elif baseline_name == "ours_gpt":
            summary_path_list.append(output_dir + f"{project_name}_0.json")
        
        log_file = f"./log/{baseline_name}_{project_name}.txt"
        for summary_path in summary_path_list:
            if os.path.exists(log_file):
                print(log_file, "has been evaluated")
                continue
            exec_swe_bench(config_file, summary_path, run_log_dir, "instance_only")
            total_num, f2p_num, error_num, pr_list, com_pass_list, pass_list = analyze_run_log(run_log_dir, summary_path)
            log_data = ""
            log_data += f"\n{'='*60}"
            log_data += f"\n编译通过样例个数：{len(com_pass_list)}"
            log_data += f"\n编译通过id: {com_pass_list}"
            log_data += f"\n编译通过测试用例个数：{total_num}"
            log_data += f"\n失败转通过个数：{f2p_num}"
            log_data += f"\n剩余失败个数：{error_num}"
            log_data += f"\n全部通过个数：{len(pass_list)}"
            log_data += f"\nf2p_id: {pr_list}"
            log_data += f"\nf2p_num: {len(pr_list)}"
            log_data += f"\n{'='*60}"
            
            print(log_data)
            with open(log_file, 'a') as f:
                f.write(log_data)
        
    

if __name__ == "__main__":
    main()