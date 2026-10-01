import re
import logging
from collections import defaultdict
import json
from pathlib import Path
import os
import pickle
import time

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser
import argparse

from configs.openai_config import build_openai_client, get_openai_model, token_collector


JAVA_LANGUAGE = Language(tsjava.language(), name='java')

parser = Parser()
parser.language = JAVA_LANGUAGE

gradle_list = ["logstash", "jib", "mockito"]


repair_system_prompt = """You are an expert Java software engineer and test automation specialist. Your task is to analyze compilation errors from test code and fix them so that the tests compile successfully while preserving their original intent.
### Goal:
Fix the provided test code so that:
1. All compilation errors are resolved. The test code must compile without errors against the current codebase.
2. The test logic remains intact. The changes should only address compilation issues (e.g., missing imports, incorrect method signatures, type mismatches) and not alter the intended assertions or test coverage.
3. The tests maintain their purpose. The fixed tests should still validate the original functionality or bug fix that the tests were designed to verify.

### Important Tips:
Provide the corrected test code with:
1. The full source code of the fixed test class(es).
2. Your reply can only contain one ```java ``` block!
"""

repair_with_requirement_prompt_init = """
The following are the patch, related code and other information.
### PATCH
{patch}

### CONTEXT
Here is the focal method that you need to generate test cases for:
{focalmethod}

Here is the structured requirement related to the patch, generated based on the developer's description and the project code:
Method Summary:
{method_summary}
Requirement description:
{requirement_description}
Trigger scenario:
{trigger_scenario}
Expected outcome:
{expected_outcome}
Solution:
{solution}

The following is the relative information about the focal method:
<Package name>
{package_name}
</Package name>

<Imports>
{imports}
</Imports>

<Focal class>
{focalclass}
</Focal class>

<Field>
{field}
</Field>

<Adjacent methods>
{Adjacent_method}
</Adjacent methods>

<Inner methods>
{inner_method}
</Inner methods>
"""

repair_prompt_init = """
The following are the patch, related code and other information.
### PATCH
{patch}

### CONTEXT
Here is the focal method that you need to generate test cases for:
{focalmethod}

Here is the PR about the patch:
{pr}

Here is the resovled issue about the patch:
{resolved_issue}

The following is the relative information about the focal method:
<Package name>
{package_name}
</Package name>

<Imports>
{imports}
</Imports>

<Focal class>
{focalclass}
</Focal class>

<Field>
{field}
</Field>

<Adjacent methods>
{Adjacent_method}
</Adjacent methods>

<Inner methods>
{inner_method}
</Inner methods>
"""

simple_repair_prompt_init = """
The following are the patch and other information.
### PATCH
{patch}

Here is the PR about the patch:
{pr}

Here is the resovled issue about the patch:
{resolved_issue}

"""

def get_imports(mainfile):
    import_context = ""
    for importInFo in mainfile.imports:
        import_context = import_context + '\n' + importInFo.content
    return import_context

def get_package(mainfile):
    package_name = ""
    package_name = mainfile.package_name
    return package_name

def get_syntax_context(mainfile, method_name):
    focal_method_context = ''
    field_context = ''
    class_name_context = ''
    neighbor_method_context = ''
    call_method_key = ''
    for classInfo in mainfile.classes:
        for methodname in list(classInfo.methods.keys()):
            if methodname == method_name:
                methodInfo = classInfo.methods[method_name]
                focal_method_context = methodInfo[0].content
                # print("="*50, "focal method: \n", focal_method_context)

                class_name_context = classInfo.name
                # print("="*50, "class name: \n", class_name_context)

                for value in classInfo.fields.values():
                    field_context = field_context + '\n' + value.content
                # print("="*50, "field: \n", field_context)

                # 获取兄弟方法签名
                for value in classInfo.methods.values():
                    method_parameter = ''
                    method_signature = ''
                    for parameter in value[0].parameters:
                        if method_parameter == '':
                            method_parameter = parameter.type.raw
                        else:
                            method_parameter = method_parameter + ',' + parameter.type.raw 
                    if value[0].name != methodname:
                        method_signature = value[0].name + '(' + method_parameter + ')'
                    else:
                        focal_method_signature = methodInfo[0].signature_key()
                    if method_signature != '':
                        neighbor_method_context = neighbor_method_context + '\n' + method_signature
                # print("="*50, "neighbor_method_context: \n", neighbor_method_context)
                
                # 获取调用链标识符
                package_name = mainfile.package_name
                call_method_key = package_name + '.' + class_name_context + '#' + focal_method_signature
                # print("="*50, "call_method_key: \n", call_method_key)


                return focal_method_context, class_name_context, field_context, neighbor_method_context, call_method_key
            
    return None

def get_call_method(data, callmethod_key):
    methods_call = []
    if callmethod_key in data.symbols.method_calls:
        methods_call = data.symbols.method_calls[callmethod_key]
    methods_call_context = ''
    for method_call in methods_call:
        methods_call_context = method_call.content + '\n' + methods_call_context
    return methods_call_context

def get_inner_method(data, call_method_key):
    all_inner_method = ""
    inner_method_key_list = []
    methods_call = []
    if call_method_key in data.symbols.method_calls:
        methods_call = data.symbols.method_calls[call_method_key]
    for MethodCallInfo in methods_call:
        inner_method_key = MethodCallInfo.resolved_fqn + '#' + MethodCallInfo.resolved_method_signature
        if inner_method_key not in inner_method_key_list:
            inner_method_code = data.symbols.methods[inner_method_key].content
            all_inner_method = all_inner_method + "\n" + inner_method_code
            inner_method_key_list.append(inner_method_key)
    return all_inner_method

def load_pkl_safe(pkl_file_path, main_file_path, method_name):
    """
    安全加载 pickle 文件，包含错误处理
    """
    # 检查文件是否存在
    if not os.path.exists(pkl_file_path):
        print(f"❌ 文件不存在: {pkl_file_path}")
        return None
    
    with open(pkl_file_path, 'rb') as f:
        data = pickle.load(f)
    print(f"✅ 成功加载: {pkl_file_path}")
        

    main_files = data.main_files[main_file_path]
    import_context = get_imports(main_files)
    package_name = get_package(main_files)
    focal_method_context, class_name_context, field_context, neighbor_method_context, call_method_key = get_syntax_context(main_files, method_name)
    # methods_call = get_call_method(data, call_method_key)
    inner_method = get_inner_method(data, call_method_key)

    return package_name, import_context, focal_method_context, class_name_context, field_context, neighbor_method_context, inner_method


def extract_java_blocks(text):
    """
    提取文本中被```java和```包裹的代码块
    """
    # 正则表达式模式：匹配```java和```之间的所有内容（包括换行）
    pattern = r'```java(.*?)```'
    
    # 使用re.DOTALL标志使.匹配包括换行符在内的所有字符
    blocks = re.findall(pattern, text, re.DOTALL)

    return blocks[0]

def repair_test(context_dict, model_name, output_file, repair_memory_list, strategy):
    
    messages = []
    system_content = repair_system_prompt + '\n\n'
    
    content = 'The following failed testcase code is written by your colleagues.'
    for repair_memory_bad in repair_memory_list:
        system_content += f"But the test file did not compile successfully and encountered the following errors:\n {repair_memory_bad['compilation_error']} \n. The incorrect file content is: \n {repair_memory_bad['fail_test_case']}.\n Please don't make such a compilation error again! \nPlease don't make such a compilation error again! \nPlease don't make such a compilation error again!\n"
    system_message = {"role": "system", "content": system_content}
    messages.append(system_message)

    number = context_dict["pr"]
    print(f"LLM正在进行代码修复 {output_file}···")
    if strategy == "context":
        context_prompt = repair_prompt_init.format(
            patch=context_dict["patch"],
            package_name=context_dict["package_name"],
            focalmethod=context_dict["focal_method_context"], 
            pr=context_dict["pr"],
            resolved_issue =  context_dict["resolved_issues"],
            imports=context_dict["import_context"], 
            focalclass=context_dict["class_name_context"], 
            field=context_dict["field_context"], 
            Adjacent_method=context_dict["neighbor_method_context"], 
            inner_method=context_dict["inner_method"],
        )
        user_message = {"role": "user", "content": context_prompt}
        messages.append(user_message)
        with open(output_file, 'a') as f:
            f.write('='*50 + '\n')
            f.write(repair_system_prompt + "\n")
            f.write(content + "\n")
            f.write(context_prompt + "\n")
    elif strategy == "requirement":
        structured_requirements = context_dict["structured_requirements"]
        context_prompt = repair_with_requirement_prompt_init.format(
            patch=context_dict["patch"],
            package_name=context_dict["package_name"],
            focalmethod=context_dict["focal_method_context"], 
            method_summary=structured_requirements["method_summary"],
            requirement_description=structured_requirements["requirement_description"],
            trigger_scenario=structured_requirements["trigger_scenario"],
            expected_outcome=structured_requirements["expected_outcome"],
            solution=structured_requirements["solution"],
            imports=context_dict["import_context"], 
            focalclass=context_dict["class_name_context"], 
            field=context_dict["field_context"], 
            Adjacent_method=context_dict["neighbor_method_context"], 
            inner_method=context_dict["inner_method"],
        )
        user_message = {"role": "user", "content": context_prompt}
        messages.append(user_message)
        with open(output_file, 'a') as f:
            f.write('='*50 + '\n')
            f.write(repair_system_prompt + "\n")
            f.write(content + "\n")
            f.write(context_prompt + "\n")
    elif strategy == "simple":
        context_prompt = simple_repair_prompt_init.format(
            patch=context_dict["patch"],
            pr=context_dict["pr"],
            resolved_issue =  context_dict["resolved_issues"],
        )
        user_message = {"role": "user", "content": context_prompt}
        messages.append(user_message)
        with open(output_file, 'a') as f:
            f.write('='*50 + '\n')
            f.write(repair_system_prompt + "\n")
            f.write(content + "\n")
            f.write(context_prompt + "\n")

    print(f"Invoking the llm for test_case_repair")
    _t_start = time.perf_counter()
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.0,
    )
    _duration = time.perf_counter() - _t_start
    gen_test_response = response.choices[0].message.content
    token_collector.add_usage(
        stage="repair",
        instance_id=context_dict.get("instance_id", ""),
        method_name=context_dict.get("method_name", ""),
        usage=response.usage,
        model=model_name,
        duration=_duration,
    )
    # gen_test_case = extract_java_blocks(gen_test_response)
    with open(output_file, 'a') as f:
        f.write('-'*50 + '\n' + context_dict["patch"] + "\n")
        f.write("Response:" + "="*50 + "\n" + gen_test_response + "\n" + "="*50 + "\n")
    print(f"Get the response for test_case")

    return gen_test_response

def split_diff_patch(patch_text):
    """
    将包含多个 diff 的 patch 分割成单独的 diff 列表
    """
    diffs = []
    current_diff = []
    
    lines = patch_text.strip().split('\n')
    
    for line in lines:
        if line.startswith('diff --git'):
            if current_diff:
                diffs.append('\n'.join(current_diff))
                current_diff = []
        current_diff.append(line)
    
    # 添加最后一个 diff
    if current_diff:
        diffs.append('\n'.join(current_diff))
    return diffs

def extract_function_names_precise(diff_content):
    """
    精确提取 @@ 行中括号 ( 和空格之间的函数名
    """
    function_names = []
    lines = diff_content.split('\n')
    
    for line in lines:
        if line.startswith('@@'):
            # 找到 @@ @@ 之后的部分
            if '@@' in line:
                # 分割出函数签名部分
                parts = line.split('@@')
                if len(parts) > 2:
                    signature = parts[2].strip()  # static boolean isValid(String text) {
                    
                    # 查找 ( 的位置
                    paren_index = signature.find('(')
                    if paren_index != -1:
                        # 找到 ( 之前最后一个空格
                        before_paren = signature[:paren_index]
                        
                        # 从后往前找第一个空格
                        last_space_index = before_paren.rfind(' ')
                        if last_space_index != -1:
                            # 提取函数名
                            func_name = before_paren[last_space_index+1:].strip()
                            if func_name and func_name not in function_names:
                                function_names.append(func_name)
    
    return function_names


def extract_java_code_from_response(response_text):
    """
    从大模型的 response 中提取 ```java 和 ``` 之间的 Java 代码
    """
    # 方法1: 使用正则表达式匹配多个代码块
    pattern = r'```java\s*(.*?)\s*```'
    matches = re.findall(pattern, response_text, re.DOTALL)
    
    if matches:
        # 合并所有匹配到的代码块
        java_code = '\n\n'.join(matches)
        return java_code


def class_name_parser(code):
    tree = parser.parse(code.encode("utf-8"))
    root = tree.root_node

    for child in root.children:
        if child.type in ("class_declaration"):
            class_name = child.child_by_field_name("name")
            return class_name.text.decode()
    print("NO TEST CLASS IN TEST CODE")
    return None



def extract_error_precise(text):
    """精确提取错误信息块（支持多个错误）"""
    lines = text.split('\n')
    result = []
    in_error_block = False
    
    for i, line in enumerate(lines):
        # 检查是否开始错误块
        if '[ERROR] COMPILATION ERROR :' in line:
            in_error_block = True
        
        if in_error_block:
            result.append(line)
            
            # 检查是否到达错误块结尾（支持多个错误）
            # 模式匹配: [INFO] X error 或 [INFO] X errors
            error_pattern = r'^\[INFO\] \d+ error(s)?$'
            if re.match(error_pattern, line.strip()):
                # 加上下一行（分隔线），如果存在
                if i + 1 < len(lines) and lines[i + 1].strip().startswith('[INFO]'):
                    # 检查是否是分隔线（通常包含多个连字符）
                    if '---' in lines[i + 1]:
                        result.append(lines[i + 1])
                break
    
    return '\n'.join(result) if result else ""

import re

def extract_gradle_compile_error(text):
    """精确提取 Gradle 编译错误信息块（支持多个错误）"""
    lines = text.split('\n')
    result = []
    in_error_block = False
    
    for i, line in enumerate(lines):
        # 检查是否开始错误块：包含 "compileJava FAILED" 的行
        if 'compileJava FAILED' in line and '> Task ' in line:
            in_error_block = True
        
        if in_error_block:
            result.append(line)
            
            # 检查是否到达错误块结尾：匹配 "X error" 或 "X errors" 的行
            error_count_pattern = r'^\s*\d+ error(s)?\s*$'
            if re.match(error_count_pattern, line.strip()):
                break
    
    return '\n'.join(result) if result else ""

def repair_with_LLM(model_name, project_name, info_list, run_log_dir, error_file, success_file, root_dir, succeed_list, error_list, repair_memory, strategy):

    new_error_list = []
        

    # 遍历生成的测试文件
    for test_case in error_list:
        print('-'*30, '分隔符', '-'*30)
        skip = 0
        for success_case in succeed_list:
            if test_case["method_name"] == success_case["method_name"] and test_case["instance_id"] == success_case["instance_id"]:
                print(f"The instance {test_case['instance_id']} {test_case['method_name']} has already been repaired successfully")
                skip = 1
                break
        if skip:
            continue
        id = test_case["instance_id"]
        failed_method_name = test_case["method_name"].split('#')[-1]
        failed_method_path = test_case["method_name"].split('#')[0]
        dirname = id.split(':')[-1]
        index = test_case["method_name"].replace('/', '_').replace('.', '')
        run_log_file = os.path.join(run_log_dir, dirname, f'fix-patch-run_{index}.log')
        compilation_error = ""
        patch_error = ""
        if not os.path.exists(run_log_file):
            print(f"The instance {dirname} {failed_method_name} doesn't find compile result")
        if os.path.exists(run_log_file):
            # 从log文件查找是否有编译错误
            with open(run_log_file, 'r') as f:
                run_log = f.read()
                if project_name in gradle_list:
                    compilation_error = extract_gradle_compile_error(run_log)
                else:
                    compilation_error = extract_error_precise(run_log)
                # 太短的返回信息不是编译信息
                if len(run_log.splitlines()) < 5:
                    patch_error = run_log
            # 没有compilation_error的测试说明此次迭代修复成功
            if compilation_error == "" and patch_error == "":
                print(f"The instance {dirname} {failed_method_name} has no compilation error")
                succeed_list.append(test_case)
            else:
                tmp_dict = {}
                tmp_dict["fail_test_case"] = test_case["test_code"]
                tmp_dict["compilation_error"] = compilation_error if compilation_error != "" else patch_error
                key = id + test_case["method_name"]
                if key not in repair_memory.keys():
                    repair_memory[key] = [tmp_dict]
                else:
                    repair_memory[key].append(tmp_dict)
                # 从原始数据集和静态解析的调用图中搜索上下文
                for info in info_list:
                    context_list = info['file_function_pairs']
                    org = info['org']
                    repo = info['repo']
                    number = str(info['number'])
                    if info['body'] is not None:
                        pr = info['title'] + '\n' + info['body'] + '\n'
                    else:
                        pr = info['title'] + '\n'
                    resolved_issues = ""
                    for resolve_issue_info in info['resolved_issues']:
                        resolved_issues += resolve_issue_info['title'] + '\n' + resolve_issue_info['body'] + '\n'
                    patch = info['fix_patch']
                    
                    for context_info in context_list:
                        file = context_info['file_path']
                        method_name = context_info['function_name']
                        focal_method_context = context_info['focal_method_context']
                        if method_name == failed_method_name and number == dirname.split('-')[-1] and file == failed_method_path:
                            context_info['pr'] = pr
                            context_info['resolved_issues'] = resolved_issues
                            context_info['patch'] = patch
                            context_info['structured_requirements'] = info['structured_requirements']
                            context_info['instance_id'] = id
                            context_info['method_name'] = test_case["method_name"]
                            
                            response_log_file = response_dir + 'repair/' + repo + '_' + number + '.txt'
                            save_dict = dict()
                            gen_test_response = repair_test(context_info, model_name, response_log_file, repair_memory[key], strategy)
                            test_code = extract_java_code_from_response(gen_test_response)

                            class_name = class_name_parser(test_code)
                            test_path = file.replace('/main/', '/test/')
                            
                            if '/guava/' in test_path:
                                test_path = file.replace('/guava/', '/guava-tests/').replace('/src/', '/test/')
                            else:
                                test_path = file.replace('/main/', '/test/')
                            
                            new_test_path = ""
                            if class_name is not None:
                                # LLM结果中解析到测试类
                                new_test_path = os.path.dirname(test_path) + '/' + class_name + '.java'
                            
                                save_dict["instance_id"] = f"mswebench/{org}_m_{repo}:pr-{number}"
                                save_dict["method_name"] = test_case["method_name"]
                                save_dict["focal_method"] = focal_method_context
                                save_dict["test_file_path"] = '/home/' + project_name + '/' + new_test_path
                                save_dict["test_code"] = test_code
                            else:
                                # 如果没有测试类就仍用原来的测试用例
                                class_name = class_name_parser(test_case["test_code"])
                                save_dict["instance_id"] = f"mswebench/{org}_m_{repo}:pr-{number}"
                                save_dict["method_name"] = test_case["method_name"]
                                save_dict["focal_method"] = focal_method_context
                                save_dict["test_file_path"] = '/home/' + project_name + '/' + test_path
                                save_dict["test_code"] = test_case["test_code"]

                            new_error_list.append(save_dict)
                    

    with open(error_file, 'w') as f:
        json.dump(new_error_list, f, indent=2)
    with open(success_file, 'w') as f:
        json.dump(succeed_list, f, indent=2)
    return repair_memory


client = build_openai_client()

response_dir = "/data/gaoshutao/liuxinyin/LLM4pr_new/history_data/"

# Configure logger
logger = logging.getLogger('current_file_logger')
logger.setLevel(logging.DEBUG)  # 设置日志级别

# 创建handler，用于输出到控制台
console_handler = logging.StreamHandler()
# console_handler = logging.FileHandler(log_file)
console_handler.setLevel(logging.DEBUG)

# 创建formatter，并添加到handler
formatter = logging.Formatter('[%(asctime)s - %(filename)s - %(funcName)s] - %(message)s')
console_handler.setFormatter(formatter)

if __name__ == "__main__":

    response_dir = "/data/gaoshutao/liuxinyin/LLM4case_new/history_data/"
    
    client = build_openai_client()
    model_name = get_openai_model()


    parser = argparse.ArgumentParser(description="演示 type 和 default 的用法")

    parser.add_argument("--raw_dataset",  type=Path,  help="原始数据集目录")
    parser.add_argument("--project_name",  type=str,  help="项目名")
    parser.add_argument("--root_dir",  type=str,  help="项目所在本地根目录")
    parser.add_argument("--output_file",  type=str,  help="测试用例输出文件路径")
    parser.add_argument("--parser_dir",  type=str,  help="项目解析后文件目录")
    parser.add_argument("--test_case_file",  type=str,  help="测试用例文件")
    parser.add_argument("--run_log_dir",  type=str,  help="测试运行日志文件夹")

    args = parser.parse_args()

    # repair_with_LLM(
    #     raw_dataset_dir=args.raw_dataset,
    #     model_name=model_name,
    #     project_name=args.project_name,
    #     error_file=args.output_file,
    #     root_dir=args.root_dir,
    #     parser_dir=args.parser_dir,
    #     test_case_file=args.test_case_file,
    #     run_log_dir=args.run_log_dir,
    # )
