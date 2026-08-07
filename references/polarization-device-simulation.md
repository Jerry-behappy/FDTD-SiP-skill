# 偏振器件仿真：通用建模、测量、运行与交付规范

## 目录

1. 适用范围与边界
2. 工程分层、来源与可追溯性
3. SOI层叠、几何与边界检查
4. 参数语义隔离、controller与PML联动
5. setup扰动矩阵与替换门禁
6. 网格与资源门禁
7. 物理TE0/TM0预检与端口方向
8. 通用测量约定
9. 偏振器件原生Optimization
10. 工况、运行与结果读取
11. 指标、CSV与作图
12. PBS原生参数Sweep、结果交接与快速审计
13. 交付检查表

## 1. 适用范围与边界

本规范适用于 SOI 平台上的偏振分束器（PBS/PSR）、TE/TM 起偏器、偏振旋转器，以及 TM0→TE0 等模式转换器。它定义可复现的 FDTD/MODE FDE 建模、最小测量、GPU 运行和结果交付流程；不把某个项目的器件尺寸、工艺层号、波段或网格参数作为通用默认值。

- 通过 PyLumerical MCP 控制 Lumerical；先读取 `workflow`、`fdtd_workflow`、`fdtd_sources_monitors`、`fdtd_run_and_results` 和按需的 FDE 指南，再打开会话。
- PyLumerical MCP 是默认控制入口。只有用户明确授权切换入口时才使用本地 `ansys.lumerical.core`；切换前说明当前入口、能力差异和授权边界，且仍不得直接实例化 `lumapi`。
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
- 参数化structure group只重建器件几何；材料、仿真区域、source、monitor、mesh和测量映射保存在独立实际对象上。所有命名包含器件、端口、模式和方向语义。
- 若外部对象不需要随几何变化，GUI对象本身是设置真值，model/setup script不得隐式覆盖。若确有物理联动需求，允许使用显式标记、已审计的顶层controller读取真实structure-group属性并同步实际对象；此时controller是联动关系真值，必须记录依赖图、名义读回和扰动测试，不得存在未标记覆盖或同名shadow参数。

## 3. SOI 层叠、几何与边界检查

- 显式建立 Si、BOX、top cladding 和需要时的 substrate，并审计材料、z 范围、`override mesh order from material database`、mesh order 与 `subtract` 语义。
- 若要求透明显示，top cladding 的 `alpha` 按用户指定；例如要求为 0.2 时，仅对 top cladding 设为 0.2，不默认改变 BOX 或 substrate 的透明度。
- 主器件、source、DFT monitor和expansion截面必须在FDTD内；只有明确设计为穿过PML的均匀接入直波导可以越过FDTD边界。BOX/top cladding的x/y范围至少覆盖“全部Si几何 ∪ FDTD”，再预留工艺/边界余量。
- 输入/输出接入波导与主器件在同一中心线和材料层连续。直波导应穿过对应 PML 的合理距离，但不得超出 BOX/top cladding。
- GDS 导入后，重叠的同层波导必须先合并为最终 Si 轮廓；不得用重叠重复对象代替几何布尔，避免 mesh/材料优先级造成伪边界。宽度不一致的级联接入波导必须以已审计长度的 taper 连接。
- source、DFT monitor、mode expansion 和 port 都置于均匀直波导截面；不得放在 taper、分束结、GDS 边缘、PML 或材料交界面。
- 保存前后递归读取 structure group 内启用子对象的全局 bbox；不能只看 group 的局部坐标或 Layout 视图。

## 4. 参数语义隔离、controller与PML联动

### 4.1 参数拆分与真实优化路径

- 每个优化变量只代表一个可解释的物理自由度。旧变量若同时控制多个物理上独立的taper、MMI段或接入波导，先为目标结构新增专用属性；新属性的名义值设为旧值，使拆分前后名义几何坐标一致。
- 原生Optimization和参数扫描直接指向真实structure-group属性路径，例如 `::model::MMI::T_W2`；不得优化空controller别名、未被setup读取的变量或顶层重复属性。
- 对外参数名必须直接说明器件段和物理量，例如 `Length_Bulge`、`Width_Bulge_Plateau`、`Width_TaperInput`；清理 `A_L`、`B_H`、单字母 `L/W` 等无法从GUI判断含义的遗留名称。固定taper/直波导参数保留为可见group属性时，从Optimization参数列表移除并在参数表标记fixed。
- 顶层controller使用带作用域前缀的局部变量读取group属性，避免与对象属性同名造成遮蔽。controller只移动具有真实物理依赖的对象，不得为了“全部联动”而强行改变无关边界。
- 变量改变后读取实际polygon顶点、对象bbox和全局坐标；不能只证明user property数值改变。

### 4.2 依赖关系与连续性

- MMI纵向长度变化通常联动器件右端、FDTD右边界、输出monitor的x位置、场monitor范围、BOX/top cladding横向覆盖和输出直波导端点。
- 第二段MMI宽度若只移动其内部边缘、而器件总外包络不变，则外部FDTD边界和包层无需移动；以实际bbox决定，不按变量名称猜测依赖。
- taper输入宽度变化后，taper固定宽度输出端、下游均匀直波导和对应DFT/expansion monitor必须保持同一中心线；同时检查上下边界顶点与连接截面，防止只改宽度却产生横向错位。
- 输出monitor始终位于FDTD内的均匀直波导截面，并与PML保持审计过的内侧距离；不得落在taper、材料交界或PML内。
- BOX/top cladding横向范围覆盖“最终Si几何 ∪ FDTD区域 ∪ PML外延直波导”，并保留项目定义的余量。

### 4.3 PML内外直波导

- 对每个输出支路显式区分 `L_inside`（taper端面到FDTD边界的均匀直波导长度）与 `L_outside`（越过边界后的PML外延长度）。两条输出支路都应穿过对应PML，不能只延伸被优化的一支。
- 读取并验证 `x_taper_end + L_inside = x_fdtd_max`、`x_lead_end = x_fdtd_max + L_outside`，以及输出monitor位于 `[x_taper_end, x_fdtd_max)` 的均匀段；具体数值由项目审计得到，不写成通用默认值。

### 4.4 本对话项目映射示例（非通用默认值）

对 `1550 polarization device optimazation/TE.fsp` 的已审计语义如下；再次使用前仍须重开工程读回确认：

| 属性 | 物理语义 | 联动范围 |
|---|---|---|
| `::model::MMI::W2` | 第二段MMI宽度 | 第二段MMI几何；外包络不变时不强制移动FDTD |
| `::model::MMI::L2` | 第二段MMI长度 | 器件右端、FDTD/monitor/场monitor/包层x范围和输出直波导 |
| `::model::MMI::T_W2` | 第二段MMI的`Taper_3`输入宽度 | 仅`Taper_3`、其输出直波导中心线和对应T1 monitor的y位置 |
| `::model::MMI::T_W` | 其余taper共用宽度 | `Taper_1/2/4`；不得再控制`Taper_3` |
| `::model::MMI::wg_length` | 输出均匀直波导在FDTD内的长度 | 本项目名义值为5 um |
| `::model::MMI::wg_outside` | 输出直波导越过右侧FDTD/PML的外延长度 | 本项目名义值为2 um |

## 5. setup扰动矩阵与替换门禁

1. 对用户指定源文件做只读审计并记录SHA256；建立精确备份和独立candidate，不直接在唯一原件上试改。
2. 获得 `runsetup()` 授权后，在candidate上依次验证名义值、仅改新变量、仅改旧变量、组合改动。每个状态都读回structure-group子对象顶点、输出直波导、FDTD、source、DFT/expansion、场monitor、BOX/top cladding和mesh的实际全局坐标。
3. “仅改新变量”必须只影响目标taper及其真实下游依赖；“仅改旧变量”必须保持已拆出的目标taper不变；组合改动应同时且独立生效。长度变量单独验证横向联动，宽度变量单独验证纵向中心线联动。
4. 验证taper端面与直波导无缝、monitor处截面均匀、两条输出均穿过PML、包层完整覆盖，且名义状态与修改前几何在项目容差内一致。
5. 恢复名义参数后保存candidate，关闭并在独立会话重开复核。只有用户明确授权覆盖目标文件时，才替换目标；替换后再次重开并记录SHA256与参数/坐标读回。
6. manifest分别记录 `runsetup_used`、`switchtolayout_called`、`solver_run`、`runsweep_called` 和 `findmodes_called`。`runsetup()`不等于求解器运行；没有授权不得调用。磁盘文件重开后若已是Layout，不因旧截图显示Analysis而调用 `switchtolayout()`。
7. 进程存在不构成本任务求解证据。按命令行、工作目录和FSP路径识别进程归属；绝不终止、修改或复用其他任务的solver进程。
8. 用户在GUI中手工修改并保存group变量、setup script、对象名或monitor位置后，之前的SHA、坐标、绑定和Optimization路径审计全部视为过期；从最新磁盘文件重新建立基线和差异。目标FSP仍在用户GUI中打开时不自动覆盖保存，改用fresh副本或等待用户关闭。

## 6. 网格与资源门禁

- 先在固定几何、边界、波段、source/monitor 和结果定义下进行网格敏感性比较；不可仅凭单一 mesh 档称为收敛。
- 全局 mesh accuracy 主要控制均匀、低散射区域；局部 mesh 覆盖分束/耦合/亚波长结构、窄间隙、强场变化或材料突变区域。避免把局部细网格无差别铺满长直波导和低影响区域。
- 局部 mesh 的 bbox、步长、优先级、覆盖对象和预期物理目的写入 manifest。删除、移动或降精度局部 mesh 后，重新做显存评估。
- 正式 3D GPU FDTD 前：保存并关闭 pre-run，独立重开并审计空结果、几何、source/monitor、网格和资源；再调用 `runsystemcheck("FDTD","GPU")` 并读取当前空闲显存。
- 显存不满足时停止并报告估算依据。只有用户授权后，才按“先降低全局精度、保留关键区局部 20–40 nm mesh、重新估算”的顺序调整；不得静默转 CPU 或降低关键区精度。
- 所有实际求解使用可见GUI会话（例如 `open_session(..., hide=False)`），并保持 `LUMERICAL_HIDE_GUI=0`；每次仅运行一个FDTD会话以避免GPU显存竞争。
- 对长器件、强反射或曾发生空 expansion 的工程，正式网格前先做一次**不保存**的时间窗口验证：临时移除 local mesh、设较低全局 mesh accuracy，并在各目标输出直波导放小型 point time monitor。经运行授权后确认脉冲到达输出、传播延迟合理且未在到达前停止；再把正式 `simulation time` 写回实际 FDTD 对象。该低成本验证不替代正式仿真，也不保存为 pre-run/working 文件。

## 7. 物理 TE0/TM0 预检与端口方向

对每一个源/测量截面，在 FDTD 正式运行前做 FDE 预检：

1. 使用实际截面、材料层叠、网格和波段，求解候选模式。
2. 按主场分量、偏振分数、场形状、neff 与传播方向确认物理 TE0/TM0；不要只相信 mode list 的编号。
3. 将确认后的 mode selection、source injection axis/direction、monitor normal 与 forward/backward 符号写入 manifest。
4. 若模式退化、模式排序变化、候选不唯一或 source/expansion 物理偏振不一致，停止该批次，先修正横截面或选择规则。

对于模式转换器，必须分别记录“输入偏振”“目标输出偏振”和“是否为同偏振泄露”。所有源方向以器件的真实传播方向为准；不得为了沿用旧命名而将右端 source 误设为反向输入。

## 8. 通用测量约定：无输入 DFT，输出最小 expansion

输入端不添加 DFT monitor，以减少计算量。每个输出测量平面保留一个 DFT monitor，并为实际关注的模式创建相应 mode expansion，显式调用：

```python
fdtd.setexpansion(expansion_name, dft_name)
```

每个 source-specific working copy 只能启用一个 source（`src_TE0` 或 `src_TM0`）。基线中所有 source 可保留但均禁用；working copy 中删除未使用 expansion，保留输出 DFT。删除仅限运行副本，绝不修改不可变 pre-run 基线。

重命名DFT或mode expansion后，立即重做 `setexpansion`，并同步修改Optimization/Sweep result路径及FOM脚本中的对象名；随后执行setup/readback并在独立重开时再次核对。对象位置重合但绑定仍指向旧名称时，结果可能显示在对象列表中却无法计算，必须作为配置错误停止。

| 器件 | 输入源 | 激活 expansion | 交付曲线与语义 |
|---|---|---|---|
| MMI PBS/PSR | TE0 | `T1_TE0`、`T2_TE0` | T1 TE 损耗（目标）与 T2 TE 损耗（另一输出端） |
| MMI PBS/PSR | TM0 | `T2_TM0`、`T1_TM0` | T2 TM 损耗（目标）与 T1 TM 损耗（另一输出端） |
| TE/TM 起偏器 | TE0 | 输出 `*_TE0` | 仅该 TE0 的损耗 |
| TE/TM 起偏器 | TM0 | 输出 `*_TM0` | 仅该 TM0 的损耗 |
| TM0→TE0 转换器 | TM0 | 右端 `P_right_TE0` | TM0→TE0 转换损耗 |
| TM0→TE0 转换器 | TE0 | 右端 `P_right_TE0` | TE0 到右端 TE0 的泄露损耗 |

同偏振的另一 PBS 输出端是**端口隔离**，不是跨偏振串扰。转换器的 TE0 输入曲线是 TE0 泄露，TM0 输入曲线是 TM0→TE0 转换；不默认创建或报告 `P_right_TM0`。如用户明确要求完整散射矩阵、偏振串扰或残余模式，再扩展相应 expansion；不可把未要求的 expansion 当作默认必算项目。

## 9. 偏振器件原生Optimization

1. 从已通过第5节setup扰动矩阵的不可变pre-run建立优化模板；参数路径必须指向真实structure-group属性，参数范围、单位、制造约束和名义值来自用户或当前工程审计，不从其他波段工程继承。
2. 每个candidate先应用变量并执行获授权的setup，再检查几何有效性、变量隔离、taper/直波导连续性、PML穿越、monitor均匀截面、FDTD与包层覆盖。门禁失败的candidate记录失败原因，不启动solver。
3. 每个输入偏振使用独立source-specific working copy，且仅启用一个真实输入source；输出DFT与expansion按第8节映射。实际求解必须使用可见会话，并保留candidate参数、FSP、日志和原生结果。
4. FOM在归一化线性功率域定义，明确目标端口/模式、带宽聚合、惩罚项、权重和约束；正损耗或负dB只用于报告，不在未说明时混入FOM。验收阈值与优化目标分开记录。
5. 使用Lumerical原生Optimization时，读回optimizer对象的实际parameter path、范围、算法、generation、population、FOM绑定和状态；配置存在不等于某一代已完成。
6. 原生Optimization只调用一次 `runsweep(optimization_name,resource)`，Lumerical会自动推进后续各代；不得把Optimization改写成普通Sweep或每代重复调用。保持启动Optimization的可见PyLumerical会话存活，直至终态和原生history/result提取完成。连接中断时先只读核对solver、代目录、p0日志和state，避免重复启动同一任务。
7. 首次验证Optimization链路时，可在用户授权的低mesh或极小population×generation上使用独立pilot；pilot只验证source、FOM、GPU、candidate保存和结果提取。正式mesh从干净Layout创建新的working FSP，不继承pilot缓存、history或candidate。
8. 对可分段级联的模式转换器，只有在中间截面、目标中间模式、传播方向和均匀接入波导已明确时，才允许把长器件拆成独立stage优化以缩短计算时间；每段使用自己的source/expansion和FOM。分段最佳不能直接宣称全器件最佳，之后必须用fresh完整级联working FSP做转换与泄露复验。
9. 对GPU Optimization，将每个candidate视为不可拆分结果包：`candidate.fsp`、成功的`candidate_p0.log`和相邻同名目录中的`candidate/candidate_output.h5`。仅当三者存在、H5非空且名称对应时增加完成计数；不得按FSP数量、p0日志数量或solver退出码单独判定。轮询先检查确定性同名路径，只在缺失或名称异常时读取FSP二进制中的相对H5引用。
   - 新项目优先直接调用 `scripts/audit_native_optimization.py` 做代际filesystem门禁，调用 `scripts/audit_lumerical_result_bundle.py` 检查单个candidate/best结果包；不要重新复制项目专用watcher中的计数逻辑。
10. `resave files after analysis=1` 只表示analysis后重新保存candidate FSP，不会把GPU monitor数据嵌入FSP，也不能替代H5完整性检查。禁止在结果归档前调用`switchtolayout()`；切回Layout并保存会删除外部GPU结果。
11. 原生 `*_best_solution.fsp` 通常是candidate FSP的复制品，内部仍可能引用该candidate的相对H5路径。每次全局最佳变化后立即解析该引用，在best-solution FSP所在目录补齐完全相同的相对sidecar目录，同时向稳定归档位置原子复制“best FSP + sidecar目录”。记录原candidate、相对路径、字节数和FSP/H5 SHA256；目标已存在但SHA不符时停止，不覆盖。
    - 优先使用 `scripts/preserve_lumerical_result_bundle.py` 创建不可覆盖的原子归档，并用 `scripts/audit_lumerical_result_bundle.py --strict` 复核；不得只复制best FSP。
12. 在删除旧generation目录、暂停清理或移动best FSP前，先完成第11步。若被引用的candidate sidecar已经丢失，不能靠重新保存旧FSP、重算mode expansion或复制其他candidate H5修复；将其标记为不可恢复结果包并保留故障路径证据。
13. 只有一代的全部candidate结果包通过第9步、结果数量正确且汇总原子写入后，才能更新该代最佳与全局最佳。部分代、失败重试、空结果或缺sidecar candidate不得覆盖最近完整代的最佳值。原生history尚未落盘时，只能对p0成功且sidecar完整的稳定candidate做无run、无save只读诊断，并标记为 `partial-generation diagnostic`。
14. 用户要求停止时立即停止新增candidate，保留最近完整代、当前部分代、全局最佳、state/history、candidate结果包和日志；不得为“补齐一代”继续求解。
15. 最优值位于参数边界时标记 `boundary-best`，不自行扩大范围。最终最佳必须从干净Layout/不可变pre-run应用同一参数，在同一solver、mesh、波段和可见会话中独立复验；保存新的working FSP及其GPU sidecar。关闭后从最终交付位置只读重开，要求Analysis mode、目标mode-expansion `getresult()`成功、点数/有限值正确且H5 SHA匹配。旧best缺sidecar时，这次独立复验同时是唯一有效修复，不得把优化缓存或已有结果重绘当作重跑。

## 10. 工况、运行与结果读取

1. 复制 source-specific working copy，设置唯一 source 启用、其余 source 禁用；核验没有输入 DFT，输出 DFT 与激活 expansion 均启用且已绑定。所有 source 使用器件真实输入端的 Forward 方向。
2. 核对波长范围、采样点数、PML、FDTD span、mesh、source 方向与 FDE 预检记录。波段和点数由本项目需求决定，不从 1550 nm 项目继承到 1310 nm 项目。
3. 保存并关闭 working copy，独立重开后完成空结果、几何、source/monitor、mesh 审计，再调用 `runsystemcheck("FDTD","GPU")`。通过后顺序执行 GPU FDTD；一次仅允许一个可见 FDTD 会话。
4. 仅 `run()` 返回、working 会话进入 Analysis mode，且能读到实际结果时才算成功。立即从该 working FSP 导出原生 expansion 数据；无需另存 Analysis FSP。
5. 失败、空结果、频点数不符、异常 auto-shutoff、GPU 资源错误或模式结果不完整时，立即停止后续批次，并保留 working copy、其 `.h5`、引擎日志、错误文件和已完成数据。
6. 关闭并重新打开 **working FSP**，再读取 source 状态、对象表、绑定关系、Analysis result 和结果数组，作为运行成功证据；配置成功或进程退出不构成运行证据。

宽带 mode expansion 的归一化前向透射率优先使用原生结果中的 `T_forward`（仅在已确认 schema 时使用等义字段）。Lumerical JSON 可能同时含大小写不同的 `n`/`N` 字段；读取原始 JSON 时使用 Python 标准库 `json`，避免大小写字段冲突造成解析失败。

## 11. 指标、CSV 与作图

令 `T_target` 为目标 expansion 的前向、源归一化功率。对 `T_forward>0` 的样本直接计算对数，禁止使用 `max(T_forward,1e-12)`、`epsilon` 或其他固定下限截断。`T_forward=0` 保留为 `-Inf`，`T_forward<0` 标记为无效值/`NaN` 并作为数据质量问题报告，不取绝对值、不截断。

- 负dB透射光谱：对正值样本使用 `T_dB = 10*log10(T_forward)`，曲线应为非正dB；不将其与正插入损耗符号混用。
- 如需摘要正插损：`IL = -10*log10(T_target)`。
- 如需交叉偏振串扰：`XT = 10*log10(T_cross)`，并明确 `T_cross` 的端口及模式求和规则。
- PBS 若需总串扰或完整 S 矩阵，应逐端口、逐输入偏振保存原始模态功率及组合规则；不能用单端口结果代替。
- 每个输入偏振独立作图；图仅包含本规范第8节对应的关注曲线。默认成对输出线性功率图和负dB图 `10*log10(T_forward)`，两图使用完全相同的波长样本、曲线名称和颜色；用户明确要求仅一种表示时再缩减。负dB图的 `ylim` 上限固定为0 dB，下限由有限的正值样本自动确定，不设置人为的有限dB下限。
- 推荐的紧凑布局为：MMI PBS 的 TE/TM 输入各一张图；TM0→TE0 转换器将 TE 输入泄露与 TM 输入转换置于同一张图；每种起偏器各一张 `subplot(2,1,x)`，上图只放 TE 输入、下图只放 TM 输入。不得把两种起偏器合并到同一张分图中。
- 图例/标题必须区分“目标转换、同偏振端口隔离、TE 泄露、TM 泄露”等物理语义，不能把同偏振另一端口称为 cross-polarization crosstalk。颜色语义在同一批图中保持一致（例如 TE 输入蓝色实线、TM 输入红色虚线）。

每个工况至少输出逐波长 CSV、中心波长摘要 CSV、原始 expansion 数据、曲线 PNG/SVG（如要求）和 manifest。所有文件记录波长单位、点数、曲线名称、颜色语义、公式、零值/无效值位置以及“未使用数值截断”。

## 12. PBS原生参数Sweep、结果交接与快速审计

### 12.1 参数化与联动边界

- 让 structure group 只生成真实 Si 几何和必要引线；让顶层 `model` controller 直接读取该 group 的真实属性，再移动具有物理依赖的 FDTD、包层、monitor、expansion 或 PML lead。不要在顶层复制同名 user property，也不要保留已废弃的参数。
- 对“固定上边、下边变化”的 MMI 宽度参数，只移动下边；对与 MMI 上边相接的 taper，让 taper 上端点始终重合，只由下端点实现输入宽度变化。每次 setup 后都读回顶点、中心线和连接截面。
- 对 MMI 长度或输出位置参数，让依赖的输出直波导、PML continuation、FDTD/BOX/TOX/Sub 右边界及输出测量面按同一位移更新；仅当实际 bbox 扩展时才延长外包络。使所有输出支路穿过其对应 PML。
- 将 DFT monitor 和其 mode expansion 一起联动：相同的中心位置、相同的横向 span，并用 `setexpansion(expansion, dft)` 显式绑定。若任务指定 1.2 µm，则两个对象都设置为 1.2 µm 并读回确认。

### 12.2 快速 Layout 审计

- 在一次 build 会话内执行参数最小值、名义值、最大值三态 setup/readback；检查参数约束、polygon 自交、连续性、FDTD/PML 覆盖、source 和输出截面的均匀性、DFT/expansion 绑定与单一启用 source。
- 将独立重开审计缩减为一次最终 Layout readback；不要对同一三态重复做第二轮重开 setup。运行后只做一次结果 schema、点数、有限值、H5 和 SHA-256 核验。
- 未获 `runsetup()` 授权时，不把三态审计替换成求解器运行；只报告可从现有 Layout 直接读到的配置和几何。

### 12.3 原生 Sweep 的结果交接

- 按 `addsweep(0)` → `addsweepparameter` → `addsweepresult` → `runsweep` → `getsweepresult` 配置；将参数路径指向真实 structure-group 属性。需要候选 FSP 时启用 `resave files after analysis`，但不要将它当作原生汇总结果存在的证明。
- 所有实际 `runsweep()` 必须在 `open_session(..., hide=false)` 的可见 FDTD 会话中执行。求解前确认只有任务授权的 source 启用；求解后保持该同一会话。
- 在**同一会话、保存/关闭/重开之前**立即调用 `havesweepresult`、`getsweepdata` 和 `getsweepresult`。`runsweep()` 返回、候选 FSP 已生成或进程退出均不能证明原生结果可用；保存或重开后不要假设瞬态结果仍在 FSP 中。
- 通过 MCP 返回数据时只返回后处理所需的 `lambda`、扫描参数、`T_forward` 和必要诊断数组。不要把完整大型 Lumerical dataset 注入 envelope，以免响应截断导致 JSON 不可解析。
- 若原生 result container 为空、点数不符或存在非有限值，标记 Sweep 失败并保留现场；不要创建 H5/图，不要将其称为完成，也不要自动重跑、切换 CPU、降低 mesh 或调用 `switchtolayout()`。

### 12.4 PBS 的 T1 指标与作图

- 将目标端口的 `T_forward` 作为前向目标 transmission；仅在任务明确要求时报告或优化 `T_total`。不要混用二者，特别是在反向功率不可忽略时。
- 按用户定义选择 FOM 聚合方式。例如，带宽平均损耗为 `mean(-10*log10(T_forward))`；平均 transmission 为同一波长网格上线性 `T_forward` 的算术平均。分别记录二者，不能互相替代。
- 对单一 TE 输入的 taper 宽度 Sweep，若用户要求“一张图五条曲线”，绘制一个坐标轴：横轴波长，纵轴 `10*log10(T_forward)` 的负 dB，`ylim` 上限固定为 0 dB；不要额外加入 TM 子图或未请求的曲线。
- 对完整 PBS 的 TE/TM 对比，仅在用户要求时使用 `subplot(2,1)`：上图为 TE0 输入的 T1/T2， 下图为 TM0 输入的 T2/T1。把同偏振的另一输出端称为端口隔离，不称为跨偏振串扰。

### 12.5 结果真值与交付

- 将原生结果的可复算数值写入单一 H5；保存扫描参数、波长、`T_forward`、`T_total`（如读取）、负 dB 曲线、平均 transmission 和所用 FOM。CSV、图和 JSON 作为摘要、索引与审计，不替代 H5。
- 在 manifest 中记录输入/working FSP SHA-256、MCP envelope、可见运行证据、波长与点数、公式、数组 shape、有限值检查和均值复算。读取与作图阶段明确标记 `solver_called=false` 和 `fsp_modified=false`。

## 13. 交付检查表

- [ ] 原始输入与 pre-run 基线 SHA256 未被运行副本改变。
- [ ] 优化变量指向真实structure-group属性；共享变量已按物理语义拆分，名义/单变量/组合扰动矩阵通过且名义几何不变。
- [ ] 顶层controller无同名shadow参数；FDTD、monitor、场monitor、包层和PML外延只按真实依赖联动并已读回。
- [ ] taper与下游直波导中心线连续；FDTD内长度与PML外延长度已分开审计，两条输出支路均穿过PML。
- [ ] Si/BOX/top cladding/substrate、mesh order、subtract 语义和全局 bbox 已读回审计。
- [ ] 所有波导、source、DFT、expansion 和 port 位于 FDTD 与包层范围内，且截面均匀。
- [ ] 每个工况只有一个 source 启用；输入端无 DFT；激活 expansion 与输出 DFT 已用 `setexpansion` 绑定。
- [ ] FDE 已确认物理 TE0/TM0、source direction 和 mode selection。
- [ ] GPU 系统检查、显存检查、引擎/会话证据与 working FSP 的 Analysis-mode 结果均已保存。
- [ ] GPU Optimization的每个完成candidate均通过“FSP + p0成功日志 + 非空同名H5”门禁；best-solution的准确相对sidecar已在清理前捆绑归档并校验SHA256。
- [ ] 原生Optimization仅启动一次且拥有会话保持到history/result提取完成；pilot与正式mesh使用独立working空间，部分代诊断未覆盖完整代最佳。
- [ ] 每个数据集波段和采样点数正确；无空结果或未授权降精度/转 CPU。
- [ ] working FSP、外部 `.h5`、图、CSV、原始数据、日志和 manifest 可作为一组从交付位置独立重开复核；不要求额外 Analysis FSP。
