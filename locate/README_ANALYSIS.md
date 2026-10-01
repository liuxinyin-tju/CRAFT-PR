# Patch Analysis Tool

This tool analyzes project patches, precisely locates the modified files and functions, and outputs a list of file-function pairs.

## Features

1. **Automatic version switching**: automatically checks out the corresponding version based on the SHA in the JSONL file
2. **Patch parsing**: parses the diff/patch format and identifies modified files
3. **Function localization**: uses heuristic methods to find the function name corresponding to each modified location
4. **Result output**: generates a list of file-function pairs in the form `(file_path, function_name)`

## Files

- `run_analysis.py` - main entry script (recommended)
- `main_analyzer.py` - main analyzer integrating all functionality
- `analyze_patches.py` - basic analysis script (early version)
- `git_operations.py` - Git operations module
- `patch_analyzer.py` - patch parsing and file localization module
- `java_parser.py` - Java code parser (with heuristic support)

## Usage

### Basic usage

```bash
# Analyze the first 10 records (recommended for testing)
python run_analysis.py --max-entries 10 --output-dir results

# Analyze a specific range of records (line numbers start from 0)
python run_analysis.py --start 100 --end 200 --output-dir results

# Analyze all records (takes a long time)
python run_analysis.py --all --output-dir full_analysis  
```

### Arguments

- `--project`: project path
- `--jsonl`: path to the JSONL file
- `--start`: start line
- `--end`: end line
- `--max-entries`: maximum number of entries to process
- `--all`: process all records
- `--output-dir`: output directory, defaults to `analysis_results`

### Output files

The following files are generated after running:

1. `final_results.json` - complete result data (JSON format)
2. `statistics.txt` - statistics


## Algorithm

### 1. SHA switching and patch application
- Uses Git operations to automatically switch to the specified SHA version
- Saves and restores the original state to ensure the current working tree is not corrupted

### 2. Patch parsing
- Parses the diff/patch format and extracts modified file paths
- Recognizes hunk headers (`@@ -start,lines +start,lines @@`)
- Extracts context information for precise localization

### 3. File localization (heuristic)
- Searches the file for matching positions using the context lines in the patch
- Takes features such as code indentation and keywords into account
- Uses a similarity algorithm to find the best matching position

### 4. Function name resolution
- **Primary method**: Java syntax analysis to recognize function definitions
- **Pattern matching**: finds the nearest function definition (public/protected/private modifier + return type + function name + parameter list)
- **Scope analysis**: determines the enclosing class and nesting relationships of the function

### 5. Edge-case handling
- Missing SHA or patch: skip the record
- File not found: log the error and continue
- Function name cannot be determined: use the `"unknown_function"` placeholder
