# 偏振器件仿真：通用建模、测量、运行与交付规范

## 1. 适用范围与边界

本规范适用于 SOI 平台上的偏振分束器（PBS/PSR）、TE/TM 起偏器、偏振旋转器，以及 TM0→TE0 等模式转换器。它定义可复现的 FDTD/MODE FDE 建模、最小测量、GPU 运行和结果交付流程；不把某个项目的器件尺寸、工艺层号、波段或网格参数作为通用默认值。

- 通过 PyLumerical MCP 控制 Lumerical；先读取 `workflow`、`fdtd_workflow`、`fdtd_sources_monitors`、`fdtd_run_and_results` 和按需的 FDE 指南，再打开会话。
- 每个 `run()`、`runsweep()`、`runsetup()`、`switchtolayout()`、删除结果或覆盖工程，均需要对应的明确授权。用户只要求建立 pre-run 文件时，不启动任何求解器。
- 不在 MCP 代码片段内重新导入或实例化 `lumapi`；以 MCP 已打开的 `fdtd`/`mode` 会话句柄操作。
- 每个项目独立审计自身 FSP、GDS、层叠、几何、波段、采样、mesh 与端口；不得从 1310 nm/1550 nm 或其他项目照搬器件尺寸、材料、层号或波段。
- “FDTD Port”仅在确有端口求解需求时使用；此时逐个显式设定 `frequency dependent profile=0`。宽带激励通常使用 mode source 与输出 DFT + mode expansion。

## 2. 工程分层、来源与可追溯性

任何建模或运行前先建立以下语义分层，禁止以运行副本替代基线：

```text
原始 FSP / GDS（只读）
  -> pre-run 基线（可编辑，未运行）
  -> source-specific working copy（仅一个源启用，solver 实际写入此副本）
  -> 原始 expansion 数据 + CSV/图/manifest
```

- 原始 FSP/GDS 保存 SHA256；运行前后的 SHA256、创建脚本版本、MCP/引擎信息、波段和采样写入 manifest。
- pre-run 是唯一不可变的无结果基线。每次求解都从它复制新的 working copy；绝不直接运行、保存覆盖或 `switchtolayout()` 该基线。
- 本流程以完成求解的 **working FSP** 为结果真值：它在 Analysis mode 中提供 monitor/expansion 数据。若产生外部 `.h5`，working FSP 与其 `.h5`、引擎日志必须作为不可拆分的一组保存、移动和归档。已有 pre-run 时，不要求额外创建或交付 Analysis FSP。
- 从 working FSP 提取原生数据、CSV、图和 manifest 后，working copy 不可再用于编辑/重跑；重跑必须从 pre-run 重新复制。这样避免 `switchtolayout()` 丢弃单次结果或新运行覆盖旧结果。
- 从 GDS 重建时，先审计 TOP cell、DBU、layer/datatype、BOUNDARY/PATH/TEXT、bbox 和层语义。端口标记、文字、轮廓参考层不应自动导入为硅几何。
- GDS 的 layer 号没有跨项目通用工艺含义。无法唯一确定硅、刻蚀、BOX、top cladding 或 substrate 语义时，记录阻塞项，不臆测层叠。
- 参数化结构组只重建几何；材料、仿真区域、source、monitor、mesh 和测量映射由独立对象管理。所有命名包含器件、端口、模式和方向语义。
- 若用户需在 GUI 直接修改仿真参数，FDTD、source、monitor 与 mesh 的最终设置必须保存在其实际对象上；model/setup script 不得在打开、运行或保存时隐式覆盖这些位置、span、模式或网格。structure group 的脚本只负责几何重建。

## 3. SOI 层叠、几何与边界检查

- 显式建立 Si、BOX、top cladding 和需要时的 substrate，并审计材料、z 范围、`override mesh order from material database`、mesh order 与 `subtract` 语义。
- 若要求透明显示，top cladding 的 `alpha` 按用户指定；例如要求为 0.2 时，仅对 top cladding 设为 0.2，不默认改变 BOX 或 substrate 的透明度。
- 最终 Si 几何、接入直波导、source、DFT monitor 和 expansion 截面必须在 FDTD 内；BOX/top cladding 的 x/y 范围至少覆盖“最终硅几何 ∪ FDTD”，再预留工艺/边界余量。
- 输入/输出接入波导与主器件在同一中心线和材料层连续。直波导应穿过对应 PML 的合理距离，但不得超出 BOX/top cladding。
- GDS 导入后，重叠的同层波导必须先合并为最终 Si 轮廓；不得用重叠重复对象代替几何布尔，避免 mesh/材料优先级造成伪边界。宽度不一致的级联接入波导必须以已审计长度的 taper 连接。
- source、DFT monitor、mode expansion 和 port 都置于均匀直波导截面；不得放在 taper、分束结、GDS 边缘、PML 或材料交界面。
- 保存前后递归读取 structure group 内启用子对象的全局 bbox；不能只看 group 的局部坐标或 Layout 视图。

## 4. 网格与资源门禁

- 先在固定几何、边界、波段、source/monitor 和结果定义下进行网格敏感性比较；不可仅凭单一 mesh 档称为收敛。
- 全局 mesh accuracy 主要控制均匀、低散射区域；局部 mesh 覆盖分束/耦合/亚波长结构、窄间隙、强场变化或材料突变区域。避免把局部细网格无差别铺满长直波导和低影响区域。
- 局部 mesh 的 bbox、步长、优先级、覆盖对象和预期物理目的写入 manifest。删除、移动或降精度局部 mesh 后，重新做显存评估。
- 正式 3D GPU FDTD 前：保存并关闭 pre-run，独立重开并审计空结果、几何、source/monitor、网格和资源；再调用 `runsystemcheck("FDTD","GPU")` 并读取当前空闲显存。
- 显存不满足时停止并报告估算依据。只有用户授权后，才按“先降低全局精度、保留关键区局部 20–40 nm mesh、重新估算”的顺序调整；不得静默转 CPU 或降低关键区精度。
- 用户要求显示运行时，使用可见 GUI 会话（例如 `open_session(..., hide=False)`），并保持 `LUMERICAL_HIDE_GUI=0`；每次仅运行一个 FDTD 会话以避免 GPU 显存竞争。
- 对长器件、强反射或曾发生空 expansion 的工程，正式网格前先做一次**不保存**的时间窗口验证：临时移除 local mesh、设较低全局 mesh accuracy，并在各目标输出直波导放小型 point time monitor。经运行授权后确认脉冲到达输出、传播延迟合理且未在到达前停止；再把正式 `simulation time` 写回实际 FDTD 对象。该低成本验证不替代正式仿真，也不保存为 pre-run/working 文件。

## 5. 物理 TE0/TM0 预检与端口方向

对每一个源/测量截面，在 FDTD 正式运行前做 FDE 预检：

1. 使用实际截面、材料层叠、网格和波段，求解候选模式。
2. 按主场分量、偏振分数、场形状、neff 与传播方向确认物理 TE0/TM0；不要只相信 mode list 的编号。
3. 将确认后的 mode selection、source injection axis/direction、monitor normal 与 forward/backward 符号写入 manifest。
4. 若模式退化、模式排序变化、候选不唯一或 source/expansion 物理偏振不一致，停止该批次，先修正横截面或选择规则。

对于模式转换器，必须分别记录“输入偏振”“目标输出偏振”和“是否为同偏振泄露”。所有源方向以器件的真实传播方向为准；不得为了沿用旧命名而将右端 source 误设为反向输入。

## 6. 通用测量约定：无输入 DFT，输出最小 expansion

输入端不添加 DFT monitor，以减少计算量。每个输出测量平面保留一个 DFT monitor，并为实际关注的模式创建相应 mode expansion，显式调用：

```python
fdtd.setexpansion(expansion_name, dft_name)
```

每个 source-specific working copy 只能启用一个 source（`src_TE0` 或 `src_TM0`）。基线中所有 source 可保留但均禁用；working copy 中删除未使用 expansion，保留输出 DFT。删除仅限运行副本，绝不修改不可变 pre-run 基线。

| 器件 | 输入源 | 激活 expansion | 交付曲线与语义 |
|---|---|---|---|
| MMI PBS/PSR | TE0 | `T1_TE0`、`T2_TE0` | T1 TE 损耗（目标）与 T2 TE 损耗（另一输出端） |
| MMI PBS/PSR | TM0 | `T2_TM0`、`T1_TM0` | T2 TM 损耗（目标）与 T1 TM 损耗（另一输出端） |
| TE/TM 起偏器 | TE0 | 输出 `*_TE0` | 仅该 TE0 的损耗 |
| TE/TM 起偏器 | TM0 | 输出 `*_TM0` | 仅该 TM0 的损耗 |
| TM0→TE0 转换器 | TM0 | 右端 `P_right_TE0` | TM0→TE0 转换损耗 |
| TM0→TE0 转换器 | TE0 | 右端 `P_right_TE0` | TE0 到右端 TE0 的泄露损耗 |

同偏振的另一 PBS 输出端是**端口隔离**，不是跨偏振串扰。转换器的 TE0 输入曲线是 TE0 泄露，TM0 输入曲线是 TM0→TE0 转换；不默认创建或报告 `P_right_TM0`。如用户明确要求完整散射矩阵、偏振串扰或残余模式，再扩展相应 expansion；不可把未要求的 expansion 当作默认必算项目。

## 7. 工况、运行与结果读取

1. 复制 source-specific working copy，设置唯一 source 启用、其余 source 禁用；核验没有输入 DFT，输出 DFT 与激活 expansion 均启用且已绑定。所有 source 使用器件真实输入端的 Forward 方向。
2. 核对波长范围、采样点数、PML、FDTD span、mesh、source 方向与 FDE 预检记录。波段和点数由本项目需求决定，不从 1550 nm 项目继承到 1310 nm 项目。
3. 保存并关闭 working copy，独立重开后完成空结果、几何、source/monitor、mesh 审计，再调用 `runsystemcheck("FDTD","GPU")`。通过后顺序执行 GPU FDTD；一次仅允许一个可见 FDTD 会话。
4. 仅 `run()` 返回、working 会话进入 Analysis mode，且能读到实际结果时才算成功。立即从该 working FSP 导出原生 expansion 数据；无需另存 Analysis FSP。
5. 失败、空结果、频点数不符、异常 auto-shutoff、GPU 资源错误或模式结果不完整时，立即停止后续批次，并保留 working copy、其 `.h5`、引擎日志、错误文件和已完成数据。
6. 关闭并重新打开 **working FSP**，再读取 source 状态、对象表、绑定关系、Analysis result 和结果数组，作为运行成功证据；配置成功或进程退出不构成运行证据。

宽带 mode expansion 的归一化前向透射率优先使用原生结果中的 `T_forward`（仅在已确认 schema 时使用等义字段）。Lumerical JSON 可能同时含大小写不同的 `n`/`N` 字段；读取原始 JSON 时使用 Python 标准库 `json`，避免大小写字段冲突造成解析失败。

## 8. 指标、CSV 与作图

令 `T_target` 为目标 expansion 的前向、源归一化功率。为避免对数零值，令 `T_plot=max(T_forward,1e-12)`，并在 manifest 中写明下限。

- 损耗光谱：`L_dB = 10*log10(T_plot)`，曲线应为非正 dB；不将其与正损耗符号混用。
- 如需摘要正插损：`IL = -10*log10(T_target)`。
- 如需交叉偏振串扰：`XT = 10*log10(T_cross)`，并明确 `T_cross` 的端口及模式求和规则。
- PBS 若需总串扰或完整 S 矩阵，应逐端口、逐输入偏振保存原始模态功率及组合规则；不能用单端口结果代替。
- 每个输入偏振独立作图；图仅包含本规范第 6 节对应的关注曲线。用户要求仅负 dB 时，只输出 `10*log10(T_plot)`，统一将 `ylim` 上限固定为 0 dB；只有用户要求时才额外输出线性图。
- 推荐的紧凑布局为：MMI PBS 的 TE/TM 输入各一张图；TM0→TE0 转换器将 TE 输入泄露与 TM 输入转换置于同一张图；每种起偏器各一张 `subplot(2,1,x)`，上图只放 TE 输入、下图只放 TM 输入。不得把两种起偏器合并到同一张分图中。
- 图例/标题必须区分“目标转换、同偏振端口隔离、TE 泄露、TM 泄露”等物理语义，不能把同偏振另一端口称为 cross-polarization crosstalk。颜色语义在同一批图中保持一致（例如 TE 输入蓝色实线、TM 输入红色虚线）。

每个工况至少输出逐波长 CSV、中心波长摘要 CSV、原始 expansion 数据、曲线 PNG/SVG（如要求）和 manifest。所有文件记录波长单位、点数、曲线名称、颜色语义、数据下限与公式。

## 9. 交付检查表

- [ ] 原始输入与 pre-run 基线 SHA256 未被运行副本改变。
- [ ] Si/BOX/top cladding/substrate、mesh order、subtract 语义和全局 bbox 已读回审计。
- [ ] 所有波导、source、DFT、expansion 和 port 位于 FDTD 与包层范围内，且截面均匀。
- [ ] 每个工况只有一个 source 启用；输入端无 DFT；激活 expansion 与输出 DFT 已用 `setexpansion` 绑定。
- [ ] FDE 已确认物理 TE0/TM0、source direction 和 mode selection。
- [ ] GPU 系统检查、显存检查、引擎/会话证据与 working FSP 的 Analysis-mode 结果均已保存。
- [ ] 每个数据集波段和采样点数正确；无空结果或未授权降精度/转 CPU。
- [ ] working FSP、外部 `.h5`、图、CSV、原始数据、日志和 manifest 可作为一组从交付位置独立重开复核；不要求额外 Analysis FSP。
