import json
import os
import pickle
from pathlib import Path


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
        # print(classInfo.name)
        for methodname in list(classInfo.methods.keys()):
            for full_method in classInfo.methods[methodname]:
                param_types = [p.type.raw for p in full_method.parameters]
                full_method_name = f"{methodname}({','.join(param_types)})"
                # full_method_name = full_method.signature_key()
                # print('='*20)
                # print(full_method_name)
                # print(method_name)
                # print('='*20)
                if full_method_name == method_name:
                    methodInfo = full_method
                    focal_method_context = methodInfo.content
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
                            focal_method_signature = methodInfo.signature_key()
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
        

    
    if not data.main_files.get(main_file_path):
        return None
    main_files = data.main_files[main_file_path]
    import_context = get_imports(main_files)
    package_name = get_package(main_files)
    focal_method_context, class_name_context, field_context, neighbor_method_context, call_method_key = get_syntax_context(main_files, method_name)
    # methods_call = get_call_method(data, call_method_key)
    inner_method = get_inner_method(data, call_method_key)
    context = dict()
    context['package_name'] = package_name
    context['import_context'] = import_context
    context['focal_method_context'] = focal_method_context
    context['class_name_context'] = class_name_context
    context['field_context'] = field_context
    context['neighbor_method_context'] = neighbor_method_context
    context['inner_method'] = inner_method

    return context

def add_context(input_file):
    project_root = Path(__file__).resolve().parent.parent
    
    with open(input_file, 'r') as f:
        info_list = json.load(f)

    results = []
    for info in info_list:
        entry_result = {}
        fields = [
                    'org', 'repo', 'number', 'state', 'title', 'body',
                    'base', 'resolved_issues', 'fix_patch', 'hints'
                ]

        # 复制这些字段
        for field in fields:
            if field in info:
                entry_result[field] = info[field]
        
        org = info['org']
        repo = info['repo']
        number = info['number']
        base_dir = f"multi_swe_bench/tmp/repos/{org}/{repo}/"
        parser_file = str(project_root / f"context_graph/{repo}_{number}.pkl")
        
        entry_result['file_function_pairs'] = []
        for file_function in info['file_function_pairs']:
            file_path = file_function['file_path']
            main_file_path = base_dir + file_path
            method_name = file_function['function_name']
            context = load_pkl_safe(parser_file, main_file_path, method_name)
            if context is not None:
                file_function['package_name'] = context['package_name']
                file_function['import_context'] = context['import_context']
                file_function['focal_method_context'] = context['focal_method_context']
                file_function['class_name_context'] = context['class_name_context']
                file_function['field_context'] = context['field_context']
                file_function['neighbor_method_context'] = context['neighbor_method_context']
                file_function['inner_method'] = context['inner_method']
                entry_result['file_function_pairs'].append(file_function)
        
        results.append(entry_result)
        
    output_dir = project_root / "locate" / "results_with_context"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = str(output_dir / f"{repo}.json")
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    return output_file
    
if __name__ == '__main__':
    project_name = "fastjson2" #commons-lang guava fastjson2 dubbo logstash jackson-databind jackson-core jackson-dataformat-xml gson jib mockito nacos skywalking

    input_file = f"locate/analysis_results/{project_name}/final_results.json"
    add_context(input_file)