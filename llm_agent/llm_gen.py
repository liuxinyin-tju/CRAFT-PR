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

gen_system_prompt = """You are an expert Java software engineer and test automation specialist. Your task is to generate unit tests for the provided patch.

### Condition:
You should strictly follow the conditions::
1. Cover the changes introduced by the patch.
2. Compile successfully. The generated test code must be syntactically correct and compatible with the existing codebase.
3. Pass after the patch is applied. The test should succeed once the patch is applied, demonstrating that the issue is fixed.

### Output
Provide the full source code of the test class(es) to be added. The test code must be enclosed in a java code block using ```java ``` format. Include:
1. The appropriate package declaration and imports.
2. The test class with a descriptive name (e.g., OriginalClassTest or Issue123Test).
3. Clear assertions that validate the expected behavior.

IMPORTANT TIPS: 
    * Your reply can only contain one ```java ``` block!
    * You should first check whether the resovled issue or structured requirements contains a reproduction method. If it does, just follow the method.
    * If the issue statements suggest you add some test cases, please omit them!
    * YOU CAN USE ASSERT IN YOUR REPRODUCE. YOU CAN USE ASSERT IN YOUR REPRODUCE. YOU CAN USE ASSERT IN YOUR REPRODUCE.
    * YOU MUST FOLLOW THE CONDITIONS. YOU MUST FOLLOW THE CONDITIONS. YOU MUST FOLLOW THE CONDITIONS. 
"""

gen_test_with_requirement_prompt_init = """The following are the patch, related code and other information.
## PATCH
{patch}

## CONTEXT
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

gen_test_prompt_init = """The following are the patch, related code and other information.
## PATCH
{patch}

## CONTEXT
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

simple_prompt_init = """The following are the patch and other information.
## PATCH
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

def get_call_method(data, call_method_key):
    methods_call = []
    if call_method_key in data.symbols.method_calls:
        methods_call = data.symbols.method_calls[call_method_key]
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

def gen_test(context_dict, model_name, output_file, strategy):
    
    messages = []
    system_message = {"role": "system", "content": gen_system_prompt}
    messages.append(system_message)
    
    if strategy == 'context':
        context_prompt = gen_test_prompt_init.format(
            patch=context_dict["patch"],
            package_name=context_dict["package_name"],
            focalmethod=context_dict["focal_method_context"], 
            pr=context_dict["pr"],
            resolved_issue=context_dict["resolved_issues"],
            imports=context_dict["import_context"], 
            focalclass=context_dict["class_name_context"], 
            field=context_dict["field_context"], 
            Adjacent_method=context_dict["neighbor_method_context"], 
            inner_method=context_dict["inner_method"],
            )
        user_message = {"role": "user", "content": context_prompt}
        messages.append(user_message)
        with open(output_file, 'a') as f:
            f.write('='*50 + "\n")
            f.write(gen_system_prompt + "\n")
            f.write(context_prompt + "\n")
            
    elif strategy == 'requirement':
        structured_requirements = context_dict["structured_requirements"]
        context_prompt = gen_test_with_requirement_prompt_init.format(
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
            f.write('='*50 + "\n")
            f.write(gen_system_prompt + "\n")
            f.write(context_prompt + "\n")
    elif strategy == "simple":
        simple_prompt = simple_prompt_init.format(
            patch=context_dict["patch"],
            pr=context_dict["pr"],
            resolved_issue=context_dict["resolved_issues"]
        )
        user_message = {"role": "user", "content": simple_prompt}
        messages.append(user_message)
        with open(output_file, 'a') as f:
            f.write('='*50 + "\n")
            f.write(gen_system_prompt + "\n")
            f.write(simple_prompt + "\n")
        

    print(f"Invoking the llm for test_case_generation")
    _t_start = time.perf_counter()
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.0,
    )
    _duration = time.perf_counter() - _t_start
    gen_test_response = response.choices[0].message.content
    token_collector.add_usage(
        stage="gen",
        instance_id=context_dict.get("instance_id", ""),
        method_name=context_dict.get("method_name", ""),
        usage=response.usage,
        model=model_name,
        duration=_duration,
    )
    # gen_test_case = extract_java_blocks(gen_test_response)
    with open(output_file, 'a') as f:
        f.write("Response:" + "\n" + gen_test_response + "\n" + "="*50 + "\n")
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
            # 如果已经有收集的 diff，保存它
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
            if child.type in ["class_declaration"]:
                class_name = child.child_by_field_name("name")
                return class_name.text.decode()
    print("NO TEST CLASS IN TEST CODE")
    return None



def gen_with_LLM(model_name, project_name, output_file, root_dir, strategy, pr_list, info_list):

    output_list = []
    index_list = []
    if os.path.exists(output_file):
        with open(output_file, 'r') as f:
            old_output = json.load(f)
        for output in old_output:
            index = output["instance_id"] + output["method_name"]
            index_list.append(index)
    try:
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
            patch_length = len(patch.split('\n'))
            if patch_length > 5000:
                print(f"Patch too long, skip gen for {repo} pr {number}")
                continue
            
            for context_info in context_list:
                file = context_info['file_path']
                method_name = context_info['function_name']
                focal_method_context = context_info['focal_method_context']
                # 跳过生成过的测试用例
                instance_id = f"mswebench/{org}_m_{repo}:pr-{number}"
                index = instance_id + file + '#' + method_name
                if index in index_list or index in pr_list:
                    print(f"{index}已生成")
                    continue
                
                context_info['pr'] = pr
                context_info['resolved_issues'] = resolved_issues
                context_info['patch'] = patch
                context_info['structured_requirements'] = info['structured_requirements']
                context_info['instance_id'] = instance_id
                context_info['method_name'] = file + '#' + method_name
                response_log_file = response_dir + 'gen/' + repo + '_' + number + '.txt'
                save_dict = dict()
                # 大模型生成
                gen_test_response = gen_test(context_info, model_name, response_log_file, strategy)
                test_code = extract_java_code_from_response(gen_test_response)
                # 根据测试类修改测试文件名
                class_name = class_name_parser(test_code)
                
                if 'guava/' in file:
                    test_path = file.replace('guava/', 'guava-tests/').replace('/src/', '/test/')
                else:
                    test_path = file.replace('/main/', '/test/')
                    
                if class_name is not None:
                    new_test_path = os.path.dirname(test_path) + '/' + class_name + '.java'
                
                save_dict["instance_id"] = f"mswebench/{org}_m_{repo}:pr-{number}"
                save_dict["method_name"] = file + '#' + method_name
                save_dict["focal_method"] = focal_method_context
                save_dict["test_file_path"] = '/home/' + project_name + '/' + new_test_path
                save_dict["test_code"] = test_code
                output_list.append(save_dict)
            
    finally:
        print("Save test cases LLM generated")
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                old_output = json.load(f)
                new_output = output_list + old_output
        else:
            new_output = output_list
        with open(output_file, 'w') as f:
            json.dump(new_output, f, indent=2)

response_dir = "/data/gaoshutao/liuxinyin/LLM4pr_new/history_data/"

client = build_openai_client()

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


    response_dir = "/data/LLM4case/history_data/"

    client = build_openai_client()
    model_name = get_openai_model()

    raw_dataset = Path("/data/multi-swe-bench/tmp/raw_dataset/")
    project_name = "fastjson2"
    root_dir = "/data/multi-swe-bench/tmp/repos/alibaba/fastjson2/"
    parser_file = "/data/LLM4case/project_full.pkl"
    config_file = "/data/multi-swe-bench/multi_swe_bench/dataset_config_fastjson2.json"
    output_dir = "/data/multi-swe-bench/tmp/testcases/"
    run_log_dir = "/data/multi-swe-bench/tmp/workdir/alibaba/fastjson2/instances/"

    parser = argparse.ArgumentParser(description="")

    parser.add_argument("--raw_dataset",  type=Path,  default=raw_dataset, help="原始数据集目录")
    parser.add_argument("--project_name",  type=str,  default=project_name, help="项目名")
    parser.add_argument("--root_dir",  type=str,  default=root_dir, help="项目所在本地根目录")
    parser.add_argument("--output_file",  type=str,  default=output_dir, help="测试用例输出文件路径")
    parser.add_argument("--parser_dir",  type=str,  default=parser_file, help="项目解析后文件目录")

    args = parser.parse_args()
    
    gen_with_LLM(
        raw_dataset_dir=args.raw_dataset,
        model_name=model_name,
        project_name=args.project_name,
        output_file=args.output_file,
        root_dir=args.root_dir,
        strategy="context",
        parser_dir=args.parser_dir
    )


