#!/usr/bin/env python3
"""
基于覆盖率信息的测试增强工具

根据 result 中每条数据的 total 和 fail 设计三个不同的 prompt：
1. total == 0: 测试未被执行但编译成功，提供原测试代码和相关信息重新生成
2. total > 0 and fail > 0: 提供报错信息、未覆盖行代码和相关信息优化测试
3. fail == 0: 测试通过，提供未覆盖代码让大模型判断测试是否有效验证 patch

如果模型认为测试不需要优化则输出 SUCCESS，否则生成新测试代码
"""

import re
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from tqdm import tqdm

from configs.openai_config import build_openai_client, get_openai_model, token_collector

client = build_openai_client()
model_name = get_openai_model()


# ==================== Prompt 模板 ====================

STRENGTHEN_SYSTEM_PROMPT = """You are an expert Java software engineer and test automation specialist. 
Your task is to optimize test cases based on coverage and execution results from the given patch.
Follow the specific instructions for your case."""

# 场景1: total == 0, 测试未被执行
PROMPT_NOT_EXECUTED = """### Task
The test case compiled successfully but was not executed. Compilation may not succeed. Please analyze the provided test code and related context, regenerate a test case that can be effectively executed.

### PATCH
{patch}

### Original Test Code
{test_code}

### Target Function
{focal_method}

### Requirements Information
{requirement_description}

### Context
Please generate a test case that can correctly execute and validate the target function based on the above information.
The test must:
1. Correctly import required dependencies
2. Use proper test framework annotations (@Test, etc.)
3. Be discoverable and executable by JUnit test framework
4. Compile successfully and run

### Output Requirements
Provide a complete Java test class code, wrapped in ```java code block."""

# 场景2: total > 0 and fail > 0, 测试执行但有失败
PROMPT_HAS_FAILURES = """### Task
The test case compiled successfully but failed after execution. Please analyze the error information, code coverage and related context to optimize the test case.

### PATCH
{patch}

### Original Test Code
{test_code}

### Uncovered Lines Code (Target function marked with '//UNCOVERED' for uncovered lines)
{uncovered_code}

### Error Information
{failures_detail}

### Requirements Information
{requirement_description}

### Analysis Requirements
1. Analyze the error reason
2. Analyze uncovered lines to understand what changes the patch introduces
3. Based on patch changes and error information, optimize the test case to:
   - Cover more code paths
   - Correctly validate the changes introduced by the patch
   - Fix existing assertion failures(If necessary, you can delete failing tests that you find difficult to fix, or directly generate new test code.)

### Output Requirements
Provide a complete Java test class code, wrapped in ```java code block."""

# 场景3: fail == 0, 测试通过但需验证有效性
PROMPT_ALL_PASSED = """### Task
All test cases passed. Please analyze the uncovered lines to determine if the current test can effectively validate the changes introduced by the patch and whether requirements are satisfied.

### PATCH Information
{patch}

### Original Test Code
{test_code}

### Uncovered Lines Code (Target function marked with '//UNCOVERED' for uncovered lines)
{uncovered_code}

### Requirements Information
{requirement_description}

### Analysis Requirements
1. Analyze uncovered lines to understand what changes the patch introduces
2. Determine if the current test can effectively test the changes to the function introduced by the patch
3. Determine if the current test can effectively validate that requirements are satisfied
4. If the test is sufficient to validate patch changes and requirements, output SUCCESS directly
5. If the test has deficiencies, provide an optimized test code

### Output Requirements
- If the test does not need optimization: Output 'SUCCESS' directly.
- If optimization is needed: provide a complete Java test class code, wrapped in ```java code block"""

# ==================== Prompt 模板 消融 ====================

PROMPT_NOT_EXECUTED_N = """### Task
The test case compiled successfully but was not executed. Compilation may not succeed. Please analyze the provided test code and related context, generate a test case that can be effectively executed.

### PATCH
{patch}

### Original Test Code
{test_code}

### Target Function
{focal_method}

### PR Info
{patch_info}

### Issue Info:
{issue_info}

### Context
Please generate a test case that can correctly execute and validate the target function based on the above information.
The test must:
1. Correctly import required dependencies
2. Use proper test framework annotations (@Test, etc.)
3. Be discoverable and executable by JUnit test framework
4. Compile successfully and run

### Output Requirements
Provide a complete Java test class code, wrapped in ```java code block."""

# 场景2: total > 0 and fail > 0, 测试执行但有失败
PROMPT_HAS_FAILURES_N = """### Task
The test case compiled successfully but failed after execution. Please analyze the error information, code coverage and related context to optimize the test case.

### PATCH
{patch}

### Original Test Code
{test_code}

### Uncovered Lines Code (Target function marked with '//UNCOVERED' for uncovered lines)
{uncovered_code}

### Error Information
{failures_detail}

### PR Info
{patch_info}

### Issue Info:
{issue_info}

### Analysis Requirements
1. Analyze the error reason
2. Analyze uncovered lines to understand what changes the patch introduces
3. Based on patch changes and error information, optimize the test case to:
   - Cover more code paths
   - Correctly validate the changes introduced by the patch
   - Fix existing assertion failures(You can delete failing tests that you find difficult to fix, or directly generate new test code.)

### Output Requirements
Provide a complete Java test class code, wrapped in ```java code block."""

# 场景3: fail == 0, 测试通过但需验证有效性
PROMPT_ALL_PASSED_N = """### Task
All test cases passed. Please analyze the uncovered lines to determine if the current test can effectively validate the changes introduced by the patch and whether requirements are satisfied.

### PATCH Information
{patch}

### Original Test Code
{test_code}

### Uncovered Lines Code (Target function marked with '//UNCOVERED' for uncovered lines)
{uncovered_code}

### PR Info
{patch_info}

### Issue Info:
{issue_info}

### Analysis Requirements
1. Analyze uncovered lines and patch to understand what changes the patch introduces
2. Determine if the current test can effectively test the changes to the function introduced by the patch
3. Determine if the current test can effectively validate that requirements are satisfied
4. If the test is sufficient to validate patch changes and requirements, output 'SUCCESS' directly
5. If the test has deficiencies, provide an optimized test code

### Output Requirements
- If the test does not need optimization: Output 'SUCCESS' directly.
- If optimization is needed: provide a complete Java test class code, wrapped in ```java code block"""


def get_timestamp():
    """获取当前时间戳"""
    timestamp = time.time()
    local_time = time.localtime(timestamp)
    return time.strftime("%Y-%m-%d %H:%M:%S", local_time)


def parser_out_java_code(response_text: str) -> Optional[str]:
    """从响应中提取 Java 代码"""
    pattern = r'```java\s*(.*?)\s*```'
    matches = re.findall(pattern, response_text, re.DOTALL)
    if matches:
        return '\n\n'.join(matches)
    return None


def get_info_from_result(result: Dict, info_list: List[Dict], case: Dict):
    """
    从 result 和 info_list 中获取需要的信息
    
    Returns:
        (patch_info, structured_requirements, pr_body)
    """
    instance_id = case.get("instance_id", "")
    method_name = case.get("method_name", "")
    pr_num = instance_id.split('-')[-1] if instance_id else ""
    
    # 从 info_list 中查找对应的 patch 和需求信息
    for info in info_list:
        info_pr_num = str(info.get('number', ''))
        if info_pr_num == pr_num:
            code_diff = info.get('fix_patch', '')
            patch_info = info.get('title', '') + '\n' + (info.get('body') if info.get('body') else '') + '\n'
            issue_info = ""
            for resolve_issue_info in info['resolved_issues']:
                issue_info += resolve_issue_info['title'] + '\n' + resolve_issue_info['body'] + '\n'
            
            structured_requirements = None
            if 'structured_requirements' in info:
                structured_requirements = info['structured_requirements']
            
            return patch_info, structured_requirements, issue_info, code_diff
    
    return None, None, None, None


def build_prompt_by_result_requirement(
    case: Dict,
    result_entry: Dict,
    info_list: List[Dict],
    uncovered_code: str = ""
) -> str:
    """
    根据 result 中的 total 和 fail 构建不同的 prompt
    
    Args:
        case: 原始测试用例信息
        result_entry: run_coverage_analysis 返回的结果条目
        info_list: 包含 patch 和需求信息的列表
        uncovered_code: 未覆盖行代码（带 UNCOVERED 标记）
    
    Returns:
        构造好的 prompt 字符串
    """
    test_code = case.get("test_code", "")
    focal_method = case.get("focal_method", "")
    test_file_path = case.get("test_file_path", "")
    
    total = result_entry.get("total", 0)
    failed = result_entry.get("failed", 0)
    
    # 获取 patch 信息
    patch_info, structured_requirements, issue_info, code_diff = get_info_from_result(result_entry, info_list, case)

    structured_requirement_description = f"""
Method Summary:
{structured_requirements.get('method_summary', '')}

Requirement description:
{structured_requirements.get('requirement_description', '')}

Trigger scenario:
{structured_requirements.get('trigger_scenario', '')}

Expected outcome:
{structured_requirements.get('expected_outcome', '')}

Solution:
{structured_requirements.get('solution', '')}
"""
    
    # 场景1: total == 0, 测试未被执行
    if total == 0:
        prompt = PROMPT_NOT_EXECUTED.format(
            patch=code_diff,
            test_code=test_code,
            focal_method=focal_method,
            requirement_description=structured_requirement_description
        )
        return prompt
    
    # 场景2: total > 0 and fail > 0, 测试执行但有失败
    if failed > 0:
        failures_detail = result_entry.get("failures_detail")
        prompt = PROMPT_HAS_FAILURES.format(
            patch=code_diff,
            test_code=test_code,
            focal_method=focal_method,
            uncovered_code=uncovered_code,
            failures_detail=failures_detail,
            requirement_description=structured_requirement_description
        )
        return prompt
    

    # 场景3: fail == 0, 测试通过
    prompt = PROMPT_ALL_PASSED.format(
        patch=code_diff,
        test_code=test_code,
        focal_method=focal_method,
        uncovered_code=uncovered_code,
        requirement_description=structured_requirement_description
    )
    return prompt

def build_prompt_by_result_context(
    case: Dict,
    result_entry: Dict,
    info_list: List[Dict],
    uncovered_code: str = ""
) -> str:
    """
    根据 result 中的 total 和 fail 构建不同的 prompt
    
    Args:
        case: 原始测试用例信息
        result_entry: run_coverage_analysis 返回的结果条目
        info_list: 包含 patch 和需求信息的列表
        uncovered_code: 未覆盖行代码（带 UNCOVERED 标记）
    
    Returns:
        构造好的 prompt 字符串
    """
    test_code = case.get("test_code", "")
    focal_method = case.get("focal_method", "")
    test_file_path = case.get("test_file_path", "")
    
    total = result_entry.get("total", 0)
    failed = result_entry.get("failed", 0)
    
    # 获取 patch 信息
    patch_info, structured_requirements, issue_info, code_diff = get_info_from_result(result_entry, info_list, case)

    
    # 场景1: total == 0, 测试未被执行
    if total == 0:
        prompt = PROMPT_NOT_EXECUTED_N.format(
            patch=code_diff,
            test_code=test_code,
            focal_method=focal_method,
            patch_info=patch_info,
            issue_info=issue_info
        )
        return prompt
    
    # 场景2: total > 0 and fail > 0, 测试执行但有失败
    if failed > 0:
        failures_detail = result_entry.get("failures_detail")
        prompt = PROMPT_HAS_FAILURES_N.format(
            patch=code_diff,
            test_code=test_code,
            focal_method=focal_method,
            uncovered_code=uncovered_code,
            failures_detail=failures_detail,
            patch_info=patch_info,
            issue_info=issue_info
        )
        return prompt
    

    # 场景3: fail == 0, 测试通过
    prompt = PROMPT_ALL_PASSED_N.format(
        patch=code_diff,
        test_code=test_code,
        focal_method=focal_method,
        uncovered_code=uncovered_code,
        patch_info=patch_info,
        issue_info=issue_info
    )
    return prompt


def strengthen_single_case(
    case: Dict,
    result_entry: Dict,
    info_list: List[Dict],
    strategy: str,
    response_dir: str
) -> Tuple[str, str]:
    """
    对单个测试用例进行增强
    
    Returns:
        (new_test_code, status)
        status: "success" 表示测试通过不需要优化, "generated" 表示生成了新代码
    """
    instance_id = case.get("instance_id", "")
    method_name = case.get("method_name", "")
    test_code = case.get("test_code", "")
    
    total = result_entry.get("total", 0)
    failed = result_entry.get("failed", 0)
    missed_line = result_entry["coverage_info"].get("missed_lines")
    if total > 0 and failed == 0:
        return test_code, "success"
    
    # 获取未覆盖代码
    coverage_info = result_entry.get("coverage_info", {})
    annotated_code = coverage_info.get("annotated_code", "")
    
    # 构建 prompt
    if strategy == "requirement" or strategy == "simple":
        prompt = build_prompt_by_result_requirement(case, result_entry, info_list, annotated_code)
    elif strategy == "context":
        prompt = build_prompt_by_result_context(case, result_entry, info_list, annotated_code)
    
    # 调用大模型
    messages = [
        {"role": "system", "content": STRENGTHEN_SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]
    
    # 保存日志
    response_log_file = os.path.join(response_dir, f"{instance_id.split('/')[-1]}.txt")
    with open(response_log_file, 'a', encoding='utf-8') as f:
        f.write(f"{get_timestamp()}\n")
        f.write("=" * 60 + "\n")
        f.write(f"total: {total}, failed: {failed}\n")
        f.write(f"Prompt:\n{prompt}\n")
        f.write("=" * 60 + "\n")

    
    print(f"调用大模型增强测试: {instance_id} - {method_name}")
    _t_start = time.perf_counter()
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.0,
    )
    _duration = time.perf_counter() - _t_start
    
    strengthen_response = response.choices[0].message.content
    token_collector.add_usage(
        stage="strengthen",
        instance_id=instance_id,
        method_name=method_name,
        usage=response.usage,
        model=model_name,
        duration=_duration,
    )
    
    with open(response_log_file, 'a', encoding='utf-8') as f:
        f.write(f"Response:\n{strengthen_response}\n")
        f.write("=" * 60 + "\n")
    
    # 解析响应
    if strengthen_response and "SUCCESS" in strengthen_response.strip():
        return test_code, "success"
    
    new_test_code = parser_out_java_code(strengthen_response)
    if new_test_code:
        return new_test_code, "generated"
    
    # 如果解析失败，返回原测试代码
    return test_code, "parse_failed"


def coverage_strengthen_main(
    input_file: str,
    result: Dict,
    info_list: List[Dict],
    output_file: str,
    strategy: str,
    response_dir: str = "/data/gaoshutao/liuxinyin/LLM4pr_new/history_data/strengthen/"
):
    """
    基于覆盖率结果对测试用例进行增强
    
    Args:
        input_file: 输入的测试用例文件路径 (repair_output_file)
        result: run_coverage_analysis 返回的结果字典
        info_list: 包含 patch 和需求信息的列表
        output_file: 增强后的输出文件路径
        response_dir: 响应日志保存目录
    """
    os.makedirs(response_dir, exist_ok=True)
    
    # 读取输入文件
    with open(input_file, 'r', encoding='utf-8') as f:
        testcases = json.load(f)
    
    unsuccess_list = []
    success_count = 0
    generated_count = 0
    failed_count = 0
    
    success_list = []
    for case in tqdm(testcases, desc="增强测试用例"):
        instance_id = case.get("instance_id", "")
        method_name = case.get("method_name", "")
        key = f"{instance_id.split(':')[-1]}_{method_name}" if ':' in instance_id else f"{instance_id}_{method_name}"
        
        # 查找对应的 result
        result_entry = result.get(key)
        if not result_entry:
            print(f"警告: 未找到 {key} 的结果，跳过")
            continue
        
        # # 检查是否有 coverage_info
        coverage_info = result_entry.get("coverage_info")
        if not coverage_info:
            print(f"警告: {key} 无 coverage_info，跳过")
            continue
        
        try:
            new_test_code, status = strengthen_single_case(
                case=case,
                result_entry=result_entry,
                info_list=info_list,
                response_dir=response_dir,
                strategy=strategy
            )
            
            # 构建输出
            output_case = {
                "instance_id": instance_id,
                "method_name": method_name,
                "focal_method": case.get("focal_method", ""),
                "test_file_path": case.get("test_file_path", ""),
                "test_code": new_test_code,
                "status": status,
                "original_test_code": case.get("test_code", ""),
                "coverage_info": {
                    "instruction_coverage": coverage_info.get("instruction_coverage", 0),
                    "branch_coverage": coverage_info.get("branch_coverage", 0),
                    "line_coverage": coverage_info.get("line_coverage", 0),
                    "start_line": coverage_info.get("start_line", 0),
                    "end_line": coverage_info.get("end_line", 0),
                    "total_lines_num": coverage_info.get("total_lines_num", 0),
                    "missed_lines_num": coverage_info.get("missed_lines_num", 0),
                    "missed_lines": coverage_info.get("missed_lines"),
                },
                "test_result": {
                    "total": result_entry.get("total", 0),
                    "passed": result_entry.get("passed", 0),
                    "failed": result_entry.get("failed", 0),
                }
            }
            
            if status == "success":
                success_list.append(output_case)
                success_count += 1
            elif status == "generated":
                unsuccess_list.append(output_case)
                generated_count += 1
            else:
                unsuccess_list.append(output_case)
                failed_count += 1
                
        except Exception as e:
            print(f"处理 {key} 时出错: {e}")
            failed_count += 1
            continue
    
    # 写入输出文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(unsuccess_list, f, indent=2, ensure_ascii=False)
    
    print(f"\n增强完成:")
    print(f"  - 不需要优化 (SUCCESS): {success_count}")
    print(f"  - 生成新代码: {generated_count}")
    print(f"  - 处理失败: {failed_count}")
    print(f"输出文件: {output_file}")

    return success_list



if __name__ == "__main__":
    # 测试用参数
    project_name = "fastjson2"
    input_file = "/data/gaoshutao/liuxinyin/LLM4pr_new/coverage/fastjson2.json"
    result_file = f"/data/gaoshutao/liuxinyin/LLM4pr_new/{project_name}_coverage.json"  # run_coverage_analysis 返回的结果
    info_list_file = "/data/gaoshutao/liuxinyin/LLM4pr/locate/results_with_requirement/output/fastjson2.json"
    output_file = "/data/gaoshutao/liuxinyin/LLM4pr_new/output/coverage_strengthen/fastjson2_strengthened.json"
    
    # 加载 result
    with open(result_file, 'r') as f:
        result = json.load(f)
    
    # 加载 info_list
    with open(info_list_file, 'r') as f:
        info_list = json.load(f)
    
    # 执行增强
    coverage_strengthen_main(
        input_file=input_file,
        result=result,
        info_list=info_list,
        output_file=output_file
    )