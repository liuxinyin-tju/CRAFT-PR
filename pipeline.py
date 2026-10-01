#!/usr/bin/env python3
# from llm_locate import Locater
from llm_agent.llm_gen import gen_with_LLM
from llm_agent.llm_repair import repair_with_LLM
from llm_agent.coverage_strengthen import coverage_strengthen_main
from typing import Dict, List, Any, Optional
from analyzer.auto_coverage_tool import run_coverage_analysis
from configs.openai_config import build_openai_client, get_openai_model, token_collector

import re
import subprocess
import json
import os
import sys
from pathlib import Path
import time
from shutil import copyfile


model_name = get_openai_model()

gradle_list = ["logstash", "jib", "mockito"]

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

def parse_failures_from_log(log_path: str) -> str:
    """
    从 fix-patch-run 日志中提取 Failures 和 Errors 的报错信息字符串。
    返回所有报错行的原始文本，每行以换行符分隔。
    如果没有报错，返回空字符串。
    """
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    results_line_idx = -1
    for idx, line in enumerate(lines):
        if '[INFO] Results:' in line:
            results_line_idx = idx
            break
    
    if results_line_idx == -1:
        print("[警告] 未找到 '[INFO] Results:' 行，无法按 Results 之后提取错误。", file=sys.stderr)
        return ""
    
    # 2. 从 Results 下一行开始扫描，收集错误行，直到遇到汇总行
    errors_raw = []
    for line in lines[results_line_idx + 1:]:
        stripped = line.strip()
        # 停止条件：遇到 '[ERROR] Tests run:' 开头的行
        if stripped.startswith('[ERROR] Tests run:'):
            break
        # 收集其他以 [ERROR] 开头的行
        if stripped.startswith('[ERROR]'):
            errors_raw.append(stripped)
            
    return "\n".join(errors_raw)
    
    

def analyze_run_log(analyzer, run_log_dir: str, output_file: str) -> Dict[str, Dict[str, Any]]:
    """
    只分析 fix-patch-run 开头的日志文件，统计每个文件对应测试类的测试用例信息。
    返回字典，键为日志文件相对路径（相对于 run_log_dir），值为：
    {
        'total': int,           # 该测试类的总用例数
        'passed': int,          # 通过用例数
        'failed': int,          # 失败用例数
        'failures_detail': list # 仅当 failed>0 时存在，包含失败详细信息
        'test_class': str,      # 测试类名（简单类名）
        'pr_number': str        # 从父目录名提取的 PR 号
    }
    """
    dir_path = Path(run_log_dir)
    with open(output_file, 'r') as f:
        output_content = json.load(f)

    result = {}  # key: 日志文件相对路径, value: 统计信息

    # 递归查找所有 fix-patch-run*.log 文件
    for fix_log in dir_path.glob('**/fix-patch-run*.log'):
        # 1. 获取相对路径作为字典键
        rel_path = str(fix_log.relative_to(dir_path))
        
        # 2. 从文件名提取待测类名（通过 output_content 映射）
        stem = fix_log.stem   # 例如 "fix-patch-run#com.fasterxml.jackson.databind.deser.NestedArrayUnwrapTest#testDeep"
        suffix = stem.replace('fix-patch-run_', '', 1)

        parts = suffix.split('#')
        package_class = parts[0].replace('_', '/')
        method_name = parts[1]
        java_path = f"{package_class[:-4]}.java"
        target_method_name = f"{java_path}#{method_name}"

        test_class_name = None
        for instance in output_content:
            if instance.get('method_name') == target_method_name:
                test_file_path = instance.get('test_file_path', '')
                test_class_name = Path(test_file_path).stem
                break
        if test_class_name is None:
            print(f"⚠️ 未找到映射的测试类: {target_method_name}, 文件: {rel_path}")
            continue

        # 3. 使用 analyzer 获取测试统计
        stats = analyzer.get_test_class_stats(str(fix_log), test_class_name)
        
        if stats is None:
            print(f"⚠️ 执行日志中未找到测试类")
            entry = {
                'total': 0,
                'passed': 0,
                'failed': 0,
                'test_class': test_class_name,
                'pr_number': fix_log.parent.name.split('-')[-1] if '-' in fix_log.parent.name else fix_log.parent.name,
                'failures_detail': "This test class has not been executed."
            }
            result[rel_path] = entry
            continue
            

        total = stats.get('total', 0)
        passed = stats.get('passed', 0)
        failed = stats.get('failed', 0)

        # 4. 构建结果条目
        entry = {
            'total': total,
            'passed': passed,
            'failed': failed,
            'test_class': test_class_name,
            'pr_number': fix_log.parent.name.split('-')[-1] if '-' in fix_log.parent.name else fix_log.parent.name
        }

        # 5. 若失败数 > 0，提取失败详情
        if failed > 0:
            failures_detail = parse_failures_from_log(str(fix_log))
            entry['failures_detail'] = failures_detail
            # 打印到控制台以便查看（可选）
            print(f"\n🔍 发现失败用例 ({failed}/{total}) 在 {rel_path}")

        else:
            print(f"✅ {rel_path}: 全部通过 ({passed}/{total})")

        result[rel_path] = entry

    # 可选：打印汇总统计
    total_cases = sum(v['total'] for v in result.values())
    total_passed = sum(v['passed'] for v in result.values())
    total_failed = sum(v['failed'] for v in result.values())
    print(f"\n📊 汇总: 共分析 {len(result)} 个日志文件, 总用例数 {total_cases}, 通过 {total_passed}, 失败 {total_failed}")
    
    return result
                
def exec_swe_bench(config_file, test_case_file, run_log_dir, mode):
    print(f"\n1. 执行 build_dataset.py")
    # 更新配置文件
    update_config(config_file, test_case_file, mode)
    # 清空原有日志
    clear_log_files(run_log_dir)
    # 执行 build_dataset.py
    cmd_build = f"python ./multi_swe_bench/harness/build_dataset.py "
    cmd_build += f"--config {config_file}"
    
    if run_command(cmd_build) != 0:
        print("build_dataset.py 执行失败")
    
def gen_test_case(model_name, project_name, output_file, root_dir, pr_list, info_list, strategy):
    print("="*50, f"\nLLM 生成测试用例 -> 生成 {output_file}")
    gen_with_LLM(
        model_name=model_name,
        project_name=project_name,
        output_file=output_file,
        root_dir=root_dir,
        strategy=strategy,
        pr_list=pr_list,
        info_list=info_list
    )
    gen_testcase_num = count_testcase_num(output_file)
    return gen_testcase_num

def repair_test_case(max_iterations: int, 
                     error_file: str, 
                     project_name: str, 
                     config_file: str, 
                     run_log_dir: str, 
                     root_dir: str, 
                     info_list: list[dict],
                     repair_output_file: str,
                     strategy: str,
                     compile_log_file: str,
                     ):
    print("="*50, f"\n开始LLM迭代编译修复")
    repair_run_time = 0
    repair_memory = {}
    iteration = max_iterations
    
    if os.path.exists(repair_output_file):
        with open(repair_output_file, 'r') as f:
            succeed_list = json.load(f)
    else:
        succeed_list = []
        with open(repair_output_file, 'w') as f:
            json.dump(succeed_list, f)
            
    # succeed_list = []
    # with open(repair_output_file, 'w') as f:
    #     json.dump(succeed_list, f)
            
    with open(error_file, 'r') as f:
        error_list = json.load(f)
        
    log = ""
    while iteration > 0 and error_list != []:

        print(f"\n{'='*60}\n", f"第 {max_iterations-iteration+1}/{max_iterations} 轮迭代修复\n", f"{'='*60}")
        log += f"\n{'='*60}\n 第 {max_iterations-iteration+1}/{max_iterations} 轮迭代修复\n"
        # 更新配置文件并执行 build_dataset.py
        exec_swe_bench(config_file, error_file, run_log_dir, "compile")
        # exit()

        start_repair = time.perf_counter()
        repair_memory = repair_with_LLM(
            model_name=model_name,
            project_name=project_name,
            error_file=error_file,
            success_file=repair_output_file,
            root_dir=root_dir,
            info_list=info_list,
            run_log_dir=run_log_dir,
            succeed_list=succeed_list,
            error_list=error_list,
            repair_memory=repair_memory,
            strategy=strategy
            )
        end_repair = time.perf_counter()
        run_time = end_repair - start_repair
        repair_run_time += run_time
        with open(error_file, 'r') as f:
            error_list = json.load(f)
        with open(repair_output_file, 'r') as f:
            succeed_list = json.load(f)
            
        log += f"编译通过的测试类数量：{len(succeed_list)}\n"
            
        iteration =  iteration - 1

    print("保存迭代修复结果")
    with open(repair_output_file, 'w') as f:
        json.dump(succeed_list, f, indent=2)
    with open(compile_log_file, 'a') as f:
        f.write(log)
    
    return repair_run_time

def get_f2p_testcase(filename, pr_list):
    with open(filename, 'r') as f:
        content = json.load(f)
    result = []
    for testcase in content:
        instance_id = testcase['instance_id']
        pr_num = instance_id.split('-')[-1]
        if pr_num in pr_list:
            result.append(testcase)
        
    return result

def main():

    model_name = get_openai_model()  # 可在 configs/openai_config.py 中统一修改
    pair_list = [('alibaba', 'fastjson2')]
    
    for pair in pair_list:
        # 修改参数
        org_name = pair[0]
        project_name = pair[1]
        strategy = "requirement" #requirement context simple
        
        root_dir = f"./multi_swe_bench/tmp/repos/{org_name}/{project_name}/"
        config_file = f"./multi_swe_bench/config/dataset_config_{project_name}.json"
        output_dir = f"./output/{model_name.split('/')[-1]}/testcases_with_{strategy}/"
        run_log_dir = f"./multi_swe_bench/tmp/workdir/{org_name}/{project_name}/instances/"
        info_list_file = f"./locate/results_with_requirement/{project_name}.json"
        os.makedirs(output_dir, exist_ok=True)
        result_list = []
        pr_list = set()
        
        with open(info_list_file, 'r') as f:
            info_list = json.load(f)
        
        max_iterations = 6 # 修复循环次数
        strength_iterations = 3 # 增强循环次数
        repeat = 1 # 重复执行次数
        
        for turn in range(repeat):
            log_file = f"./log/{model_name.split('/')[-1]}/{strategy}/{project_name}_{turn}.txt"
            compile_log_file = f"./log/{model_name.split('/')[-1]}/{strategy}/compile_{project_name}_{turn}.txt"
            final_output_file = output_dir + f'result/{project_name}_{turn}.json'
            os.makedirs(os.path.dirname(final_output_file), exist_ok=True)
            os.makedirs(os.path.dirname(compile_log_file), exist_ok=True)
            
            
            if os.path.exists(final_output_file):
                with open(final_output_file, 'r') as f:
                    round_result = json.load(f)
                result_list.extend(round_result)
                for instance in round_result:
                    pr_method_name = instance["instance_id"] + instance["method_name"]
                    pr_list.add(pr_method_name)
                print(f"第{turn+1}/{repeat}轮生成已完成", f"\n已生成{len(pr_list)}个合格测试")
                continue
                
            # try:
            run_time = 0
            token_collector.reset()
            print("开始自动化执行流程...")
            
            start_gen = time.perf_counter()
            # 生成初始测试用例
            gen_output_file = output_dir + f"{project_name}_{turn}.json"
            gen_test_case(model_name, project_name, gen_output_file, root_dir, pr_list, info_list, strategy)
            # exit()
            
            end_gen = time.perf_counter()
            gen_run_time = end_gen - start_gen
            run_time += gen_run_time
            print("\n[生成阶段] Token 消耗:")
            token_collector.print_summary()
            
            # 迭代修复
            error_file = output_dir + f"compile_error/{project_name}_{turn}.json"
            os.makedirs(os.path.dirname(error_file), exist_ok=True)
            copyfile(gen_output_file, error_file)
            
            repair_output_file = output_dir + f"compile_pass/{project_name}_{turn}.json"
            os.makedirs(os.path.dirname(repair_output_file), exist_ok=True)
            
            if not os.path.exists(repair_output_file):
                repair_run_time = repair_test_case(max_iterations, error_file, project_name, config_file, run_log_dir, root_dir, info_list, repair_output_file, strategy, compile_log_file)
            else:
                print(f"\n第{turn}轮生成的测试已修复结束")
            
            print("\n[修复阶段] Token 消耗:")
            token_collector.print_summary()

            # 运行收集结果
            result = run_coverage_analysis(repair_output_file, project_name, max_workers=4, skip_test=False)
            

            # 测试增强（提升覆盖率和通过率）
            for i in range(strength_iterations):
                strength_repair_file = output_dir + f"compile_pass/{project_name}_strength_{turn}_{i}.json"
                strength_success_file = output_dir + f"strengthen/success/{project_name}_{turn}_{i}.json"
                os.makedirs(os.path.dirname(strength_success_file), exist_ok=True)
                if not os.path.exists(strength_repair_file) or not os.path.exists(strength_success_file):
                    tmp_strength_input_file = output_dir + f"strengthen/tmp_{project_name}_strength.json"
                    if i == 0:
                        copyfile(repair_output_file, tmp_strength_input_file)
                    strength_output_file = output_dir + f"strengthen/{project_name}_{turn}_{i}.json"
                    print("="*50, f"\n开始LLM测试增强 -> {strength_output_file}")
                    
                    start_str = time.perf_counter()
                    success_list = coverage_strengthen_main(input_file=tmp_strength_input_file, output_file=strength_output_file, result=result, info_list=info_list, strategy=strategy)
                    end_str = time.perf_counter()
                    str_run_time = end_str - start_str
                    with open(strength_success_file, 'w') as f:
                        json.dump(success_list, f, indent=2, ensure_ascii=False)
                        
                    str_repair_time = repair_test_case(max_iterations, strength_output_file, project_name, config_file, run_log_dir, root_dir, info_list, strength_repair_file, strategy, compile_log_file)
                    run_time += str_repair_time + str_run_time
                    
                    copyfile(strength_repair_file, tmp_strength_input_file)
                else:
                    print(f"第{turn}轮第{i}次增强已完成")
                    with open(strength_success_file, 'r') as f:
                        success_list = json.load(f)
                    existing_keys = set(f"{item['instance_id']}_{item['method_name']}" for item in result_list)
                    for item in success_list:
                        key = f"{item['instance_id']}_{item['method_name']}"
                        if key not in existing_keys:
                            result_list.append(item)
                    continue

                # exit()
                # 运行收集结果
                result = run_coverage_analysis(strength_repair_file, project_name, max_workers=4, skip_test=False)
                existing_keys = set(f"{item['instance_id']}_{item['method_name']}" for item in result_list)
                for item in success_list:
                    key = f"{item['instance_id']}_{item['method_name']}"
                    if key not in existing_keys:
                        result_list.append(item)
                
                # 统计 result_list 中的信息
                total_testcases = 0
                passed_testcases = 0
                failed_testcases = 0
                pr_set = set()
                method_count = len(result_list)
                
                for item in result_list:
                    test_result = item.get("test_result", {})
                    total = test_result.get("total", 0)
                    passed = test_result.get("passed", 0)
                    failed = test_result.get("failed", 0)
                    instance_id = item.get("instance_id", "")
                    
                    total_testcases += total
                    passed_testcases += passed
                    failed_testcases += failed
                    if instance_id:
                        pr_set.add(instance_id)
                
                log_data = ""
                log_data += f"\n{'='*60}"
                log_data += f"\n第{turn}轮第{i}次增强结果统计:"
                log_data += f"\n  方法数量: {method_count}"
                log_data += f"\n  总测试用例数: {total_testcases}"
                log_data += f"\n  通过测试用例数: {passed_testcases}"
                log_data += f"\n  失败测试用例数: {failed_testcases}"
                log_data += f"\n  PR数量: {len(pr_set)}"
                log_data += f"\n  运行时间: {run_time}"
                log_data += f"\n{'='*60}"
                print(log_data)
                with open(log_file, "a") as f:
                    f.write(log_data)
            
            print("\n[增强阶段] Token 消耗:")
            token_collector.print_summary()

            with open(final_output_file, 'w') as f:
                json.dump(result_list, f, indent=2)
            
            # 保存 token 用量明细
            token_usage_file = output_dir + f'token_usage/{project_name}_{turn}.json'
            os.makedirs(os.path.dirname(token_usage_file), exist_ok=True)
            token_collector.save_to_file(token_usage_file)

if __name__ == "__main__":
    main()