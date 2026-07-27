# FDTD-skill

面向 Ansys Lumerical 2025 R1 的硅光子器件仿真技能，适用于 FDTD、MODE/FDE、EME、varFDTD、参数化结构组、优化、GDS 重建与版图导出等工作流。

## 主要内容

- SOI 波导、弯曲、MMI、PBS、耦合器和光栅耦合器建模
- FDTD、MODE/FDE、EME 与 varFDTD 仿真设置和结果分析
- 参数化结构组、扫描、优化及可复现仿真流程
- GDS 几何重建、版图检查与 LSF 导出
- 光源、模式、监视器、网格和边界条件的配置建议

## 目录结构

```text
SKILL.md                         主技能说明
agents/openai.yaml               Codex 元数据
references/                      专题参考资料
scripts/export_layout.lsf        版图导出脚本
```

## 使用方式

在 Codex 中提出具体的 Lumerical 仿真或版图任务即可触发本技能。例如：

```text
使用 jnu-mwp-fdtd，检查这个 GDS 的实际层和几何结构，并重建为 SOI FDTD 模型。
```

```text
使用 jnu-mwp-fdtd，设置参数化光栅耦合器并分析 1550 nm 附近的耦合效率。
```

## 环境要求

- Ansys Lumerical 2025 R1 或兼容版本
- Windows 环境
- Codex Desktop 与 PyLumerical MCP
- 需要运行实际求解器时，应先确认 Lumerical 会话和仿真参数

## 注意事项

仿真结果应通过实际求解器运行、结果提取和重新打开后的检查进行验证。GDS 导出前应独立确认最终 Layout FSP、几何结构、层信息和版图完整性。
