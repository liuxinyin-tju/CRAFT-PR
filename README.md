# CRAFT-PR: An LLM-based Approach for Automatic Test Generation for PRs

Built on top of the real-world Java PR data and Docker execution environment provided by [multi-swe-bench](multi_swe_bench/), this project automates the entire workflow of **PR patch analysis → focal-method localization → context & requirement construction → LLM-based test generation → iterative compilation repair → coverage strengthening**.

Evaluated projects (`org / repo`):

| org | repo |
| --- | --- |
| alibaba | fastjson2, nacos |
| apache | dubbo |
| google | gson, guava |
| fasterxml | jackson-core, jackson-databind, jackson-dataformat-xml |

---

## 1. Workflow Overview

The workflow consists of three stages. **All commands must be run from the project root directory `/data/gaoshutao/liuxinyin/LLM4pr_final`** (all paths used inside the scripts are `./...` paths relative to this directory).

```
Stage 0  Docker image build
         python multi_swe_bench/harness/build_dataset.py --config <config> --mode image
Stage 1  Data preparation (run in order; edit org_name / project_name inside each script)
         (1) python checkout_and_parser.py
         (2) python locate/run_analysis.py
         (3) python -m locate.add_context
         (4) python -m llm_agent.llm_req
Stage 2  Test generation
         python pipeline.py
```

Inputs and outputs of each stage:

| Stage | Input | Output |
| --- | --- | --- |
| 0 Image build | `multi_swe_bench/tmp/raw_dataset/{org}__{repo}_dataset.jsonl` | A Docker image per PR; repository clones under `tmp/repos/` |
| 1-(1) | Raw dataset jsonl | `context_graph/{repo}_{pr}.pkl` |
| 1-(2) | jsonl + repository source | `locate/analysis_results/{repo}/final_results.json` |
| 1-(3) | Output of (2) + `context_graph/*.pkl` | `locate/results_with_context/{repo}.json` |
| 1-(4) | Output of (3) + LLM | `locate/results_with_requirement/{repo}.json` |
| 2 Generation | Output of (4) + Docker images | `output/{model}/testcases_with_{strategy}/result/{repo}_{turn}.json` |

---

## 2. Environment Setup

1. **Docker**: used to build and run the PR execution images. On startup, `build_dataset.py` automatically checks for and starts the `mswebench/nix_swe:v1.0` container (container name `nix_swe`). Make sure the current user has access to the Docker daemon.
2. **Python environment**:

   ```bash
   pip install -r requirements.txt
   ```
3. **LLM API configuration**: edit the three constants at the top of [configs/openai_config.py](configs/openai_config.py):
   - `OPENAI_API_KEY`: API key
   - `OPENAI_BASE_URL`: endpoint of an OpenAI-compatible service (defaults to SiliconFlow)
   - `OPENAI_MODEL`: model name (defaults to `deepseek-ai/DeepSeek-V3.2`); this name also determines the output directory `output/{model}/...`
4. **Raw dataset**: make sure `multi_swe_bench/tmp/raw_dataset/{org}__{repo}_dataset.jsonl` exists (the PR dataset exported by multi-swe-bench, one PR per line, with fields such as `repo`, `number`, `base.sha`, `fix_patch`, `resolved_issues`).
5. **Project config files**: each project has a corresponding `multi_swe_bench/config/dataset_config_{repo}.json` declaring parameters such as `workdir`, `raw_dataset_files`, `repo_dir`, `need_clone`, `log_dir`, `max_workers`, and `test_case_files`. `build_dataset.py` reads it via `--config` (command-line arguments with the same names can override the config values).

---

## 3. Stage 0: Build Docker Images

Before processing a project for the first time, build the execution images for all PRs involved in that project:

```bash
python ./multi_swe_bench/harness/build_dataset.py \
    --config ./multi_swe_bench/config/dataset_config_fastjson2.json \
    --mode image
```

---

## 4. Stage 1: Data Preparation

The four scripts must be run **strictly in order**. Whenever you switch to another project, update `org_name` / `project_name` in the `__main__` block of the corresponding script (`dataset_list` in `llm_req.py`). The examples below use `alibaba / fastjson2`.

### (1) Checkout and parse the code structure

```bash
python checkout_and_parser.py
```

### (2) Analyze the patch and locate focal methods

```bash
python locate/run_analysis.py
```

### (3) Enrich with context

```bash
python -m locate.add_context
```

### (4) Generate structured requirement documents with the LLM

```bash
python -m llm_agent.llm_req
```

This completes the **data preparation stage**.

---

## 5. Stage 2: Test Generation (pipeline.py)

```bash
python pipeline.py
```

Edit the following in `main()` of [pipeline.py](pipeline.py):

```python
pair_list = [('alibaba', 'fastjson2')]   # list of (org, repo) pairs to run
strategy  = "requirement"                # requirement / context / simple
max_iterations      = 6                  # max iterations of compilation repair
strength_iterations = 3                  # number of coverage-strengthening rounds
repeat              = 1                  # number of overall repetitions (turns)
```

---


## 6. Directory Structure

```
LLM4pr_final/
├── Build prerequisites and data
│   ├── multi_swe_bench/
│   │   ├── harness/build_dataset.py   # entry for Docker image build and in-container compile/execution
│   │   ├── config/dataset_config_*.json
│   │   └── tmp/                       # raw_dataset(datasets) / repos(clones) / workdir(logs)
│   ├── checkout_and_parser.py         # Stage 1-(1): checkout + parsing
│   ├── parser/ parser_main.py         # Java project parser (tree-sitter symbol table)
│   └── context_graph/                 # output of Stage 1-(1): {repo}_{pr}.pkl
├── locate/                            # Stage 1-(2)(3)(4): patch analysis and context/requirement construction
│   ├── run_analysis.py  add_context.py
│   ├── analysis_results/ results_with_context/ results_with_requirement/
├── llm_agent/                         # LLM calls: requirement / test generation / repair / strengthening
│   ├── llm_req.py  llm_gen.py  llm_repair.py  coverage_strengthen.py
├── analyzer/                          # in-container test execution and coverage analysis
├── configs/openai_config.py           # LLM API key / base URL / model configuration
├── requirements.txt                   # Python dependencies (pip install -r)
├── pipeline.py                        # Stage 2: main orchestration of generate-repair-strengthen
├── output/                            # all intermediate and final artifacts of Stage 2
├── evaluate/                          # Stage 3: F2P / coverage / CAR evaluation
└── log/                               # pipeline run logs and token statistics
```
