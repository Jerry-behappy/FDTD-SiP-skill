# FDTD-SiP-Simulation

FDTD-SiP-Simulation 是面向 Ansys Lumerical 2025 R1 的通用硅光子器件仿真技能，覆盖 FDTD、MODE/FDE、EME、varFDTD、参数化结构组、原生 Sweep/Optimization、GDS 重建与结果审计。

本仓库的脚本坚持三个边界：不直接实例化 `lumapi`，不把 `runsetup()` 当作求解，不在没有明确授权时调用 `run()`、`runsweep()`、`emesweep()`、`findmodes()` 或 `switchtolayout()`。

## 能力范围

- FDTD、MODE/FDE、EME 与 varFDTD 的 Layout 设置、对象回读和原生结果摘要
- 参数化 structure group、monitor/solver 联动、Parameter Sweep 和 Optimization 配置
- 可复现的 PyLumerical MCP scenario、fresh working FSP、结果包和 SHA-256 审计
- GDSII 层级/层号/坐标/边界框检查、原生 `gdsimport` 重建脚本生成和 LSF 截面导出
- SOI 波导、弯曲、MMI、PBS、耦合器、光栅耦合器和模式转换器工作流

## 目录结构

```text
SKILL.md                              主技能规范与执行门禁
agents/openai.yaml                    Codex 技能元数据
references/                           器件与求解器专题规范
scripts/                              可复用脚本
```

## 可复用脚本

### FDTD、MODE/FDE、EME 与 varFDTD

| 文件 | 清晰用途 | 启动求解器 | 写入工程 |
|---|---|---:|---:|
| [`scripts/pylumerical_mcp_stdio_runner.py`](scripts/pylumerical_mcp_stdio_runner.py) | 按 scenario 顺序调用 PyLumerical MCP；支持 `code_file` 与 JSON `code_context`，并生成紧凑执行 envelope | 由 scenario 决定 | 由 scenario 决定 |
| [`scripts/configure_lumerical_project_via_mcp.py`](scripts/configure_lumerical_project_via_mcp.py) | 设置 solver、source、port、monitor、mesh 和 structure group 属性；可执行 Layout `runsetup()`、`setexpansion()` 和 readback | 否 | 仅在显式提供 fresh `save_as` 时 |
| [`scripts/audit_lumerical_project_via_mcp.py`](scripts/audit_lumerical_project_via_mcp.py) | 跨产品读取 named object、global source/monitor、Sweep 设置和 `getresult()`；对大数组输出 shape、有限值计数、范围、均值与样本 | 否 | 否 |
| [`scripts/configure_native_sweep_via_mcp.py`](scripts/configure_native_sweep_via_mcp.py) | 创建原生 Parameter Sweep 或 Optimization，保留 Lumerical 原生参数/结果 struct 字段并回读设置 | 否，不调用 `runsweep()`/`emesweep()` | 仅在显式提供 fresh `save_as` 时 |

这些 worker 由 PyLumerical MCP 的 `execute_python_code` 执行，运行环境提供 `_lum_get()` 与 `_lum_print_json()`。它们不包含器件专用 FOM，也不预设 transmission、模式映射或带宽聚合定义；这些物理定义必须由具体项目给出。

### GDS 几何重建、检查与导出

| 文件 | 清晰用途 | 输入 | 输出 |
|---|---|---|---|
| [`scripts/audit_gds_geometry.py`](scripts/audit_gds_geometry.py) | 标准库 GDSII 只读解析；报告 DBU、cell、layer/datatype、SREF 展平、TEXT、bbox、面积、warning 与 SHA-256 | `.gds` | JSON 审计 |
| [`scripts/generate_gds_import_lsf.py`](scripts/generate_gds_import_lsf.py) | 从明确的 cell/process-layer/material/Z 映射生成原生 `gdsimport` LSF；不猜工艺参数 | JSON layer map | `.lsf` |
| [`scripts/export_layout.lsf`](scripts/export_layout.lsf) | 用 `polystencil()` 提取最终 Layout FSP 的真实材料截面，并用 `gdsaddpoly()` 导出 GDS | Layout `.fsp` | `.gds` |

`audit_gds_geometry.py` 支持 BOUNDARY、BOX、PATH、TEXT 和常见 SREF 变换。AREF 会被明确标为 warning，不会被静默当成完整几何。需要逐顶点证据时使用 `--include-elements`；日常快速审计保留默认紧凑报告。

### 结果包、Optimization 与清单

| 文件 | 清晰用途 |
|---|---|
| [`scripts/audit_lumerical_result_bundle.py`](scripts/audit_lumerical_result_bundle.py) | 只读审计 FSP、GPU H5 sidecar 和可选 p0 成功日志 |
| [`scripts/preserve_lumerical_result_bundle.py`](scripts/preserve_lumerical_result_bundle.py) | 清理代目录前原子保存 FSP + 相对 H5 sidecar，并校验 SHA-256 |
| [`scripts/audit_native_optimization.py`](scripts/audit_native_optimization.py) | 检查原生 Optimization 的 candidate/generation 文件完整性，不把文件计数冒充原生 FOM/history |
| [`scripts/build_sha256_manifest.py`](scripts/build_sha256_manifest.py) | 为交付文件或目录生成可复核 SHA-256 manifest |
| [`scripts/_artifact_utils.py`](scripts/_artifact_utils.py) | 为上述脚本提供 atomic JSON、流式 SHA-256、p0 与 sidecar 解析 |

## 典型用法

### 1. 快速检查 GDS

```powershell
python -X utf8 scripts\audit_gds_geometry.py device.gds --output data\device_gds_audit.json
```

如需让 AREF、循环引用或缺失引用等 warning 直接导致非零退出码：

```powershell
python -X utf8 scripts\audit_gds_geometry.py device.gds --strict
```

### 2. 生成 GDS 重建 LSF

先创建 UTF-8 JSON process map；材料和 Z 范围必须来自项目工艺，不得照搬示例：

```json
{
  "source_gds": "device.gds",
  "cell": "TOP",
  "layers": [
    {
      "layer": "1:0",
      "material": "Si (Silicon) - Palik",
      "z_min_m": 0.0,
      "z_max_m": 2.2e-7,
      "description": "示例硅层；实际值按项目工艺填写"
    }
  ]
}
```

```powershell
python -X utf8 scripts\generate_gds_import_lsf.py process_map.json --output scripts\reconstruct_layout.lsf
```

生成器只写 LSF，不打开 Lumerical。生成的脚本只做 Layout `gdsimport()`，不运行求解器、不保存 FSP。

### 3. 用同一 worker 配置不同求解器

在 MCP scenario 的 `execute_python_code` 调用中，通过 `code_context` 描述对象和属性：

```json
{
  "label": "configure_layout",
  "tool": "execute_python_code",
  "arguments": {
    "code_file": "configure_lumerical_project_via_mcp.py",
    "code_context": {
      "session": "working_layout",
      "named_settings": [
        {
          "path": "::model::FDTD",
          "properties": {
            "mesh accuracy": 2
          }
        }
      ],
      "global_source_settings": {
        "wavelength start": 1.3e-6,
        "wavelength stop": 1.32e-6
      },
      "global_monitor_settings": {
        "frequency points": 10
      },
      "expansion_bindings": [
        {
          "expansion": "expansion for T1",
          "monitor": "T1"
        }
      ],
      "runsetup": true,
      "readback_named": [
        {
          "path": "::model::FDTD",
          "properties": ["mesh accuracy", "x min", "x max"]
        }
      ]
    }
  }
}
```

MODE/FDE、EME 和 varFDTD 使用同一脚本，只需把对象路径和属性改成该工程实际存在的名称。不要照搬示例中的 `::model::FDTD`。

### 4. 创建但不运行原生 Sweep/Optimization

`configure_native_sweep_via_mcp.py` 直接接受 Lumerical 原生 struct 字段。例如 Parameter Sweep 参数使用 `Name/Parameter/Type/Units/Start/Stop`，Optimization 参数通常使用 `Name/Parameter/Type/Units/Min/Max`；结果使用 `Name/Result`，Optimization FOM 结果再按项目需要添加 `Optimize`。

配置脚本结束时明确返回：

```text
runsweep_called = false
emesweep_called = false
solver_called = false
```

真正启动 Sweep/Optimization 必须是后续独立步骤，并再次确认用户授权与可见 `hide=false` Lumerical 窗口。

### 5. 先 dry-run，再执行 scenario

```powershell
python -X utf8 scripts\pylumerical_mcp_stdio_runner.py project_scenario.json --dry-run
python -X utf8 scripts\pylumerical_mcp_stdio_runner.py project_scenario.json --output logs\project_mcp_envelope.json
```

`--dry-run` 只验证 call、`code_file` 和 `code_context`，不连接 Lumerical。

## 可复现仿真闭环

1. 记录源 FSP/GDS 的 SHA-256，保持 baseline/pre-run 不可变。
2. 用 `configure_lumerical_project_via_mcp.py` 创建 fresh Layout working FSP，并对参数最小值、基线值、最大值做 `runsetup()` readback。
3. 用 `configure_native_sweep_via_mcp.py` 配置原生 Sweep/Optimization，但不在配置阶段启动。
4. 只有获得明确授权后，才从可见 `hide=false` 会话启动实际求解；求解调用应留在项目专用 scenario 中。
5. 运行结束后立即读取原生 result/history；GPU 结果同时保留 working/best FSP 与其准确相对路径 H5 sidecar。
6. 用 `audit_lumerical_project_via_mcp.py` 独立重开检查 native result，再生成 manifest。

## 环境要求

- Windows 与 Python 3.11+；中文路径建议使用 `python -X utf8`
- Ansys Lumerical 2025 R1 或经过项目验证的兼容版本
- Codex Desktop 与 PyLumerical MCP
- 实际求解时使用可见 Lumerical 会话；纯 Layout 建模和只读审计可隐藏运行

## 安全边界

- 脚本不使用 `lumapi`/`ansys.lumerical.core`，也不把 PyLumerical MCP 握手当成求解证据。
- `runsetup()` 只刷新参数化 Layout，不产生 FDTD/FDE/EME/varFDTD 求解结果。
- `configure_*` worker 拒绝 Analysis mode，也不会自动调用 `switchtolayout()`。
- 保存工程时必须显式提供与源文件不同的 `save_as`；默认拒绝覆盖已有目标。
- `audit_lumerical_project_via_mcp.py` 的数值摘要是通用数据质量检查，不替代器件专用物理指标和验收公式。

## 致谢

感谢周务飞同学对本人的仿真教学和帮助
