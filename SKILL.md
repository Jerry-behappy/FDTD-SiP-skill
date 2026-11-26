---
name: fdtd-sip-simulation
description: General Ansys Lumerical 2025 R1 workflow for SOI silicon-photonic devices at JNU MWP. Use for FDTD, MODE/FDE, EME, varFDTD, parameterized structure groups, native Optimization, GDS reconstruction/export, GPU execution, broadband results, parameter sweeps, tapers, bends, MMI/PBS, couplers, grating couplers, mode converters, and related simulation debugging or cleanup through PyLumerical MCP.
---

# FDTD-SiP-Simulation — 硅光器件通用仿真规范

## 核心原则

- 使用中文回复，技术术语保留英文；建模与controller脚本使用UTF-8并包含可维护的中文注释。
- **skill与MCP必须同时使用**：每次调用本skill（`fdtd-sip-simulation`），必须同时使用 `pylumerical` MCP；不得仅加载skill而省略MCP。通过PyLumerical MCP控制Lumerical，不直接实例化 `lumapi`。把可复现的长流程保存为项目脚本，不让关键逻辑只存在于一次性snippet。
- 按任务选择所需阶段。纯 Layout 建模、单点排错和只读结果分析可在取得所需几何、原生数据或诊断结论后结束。正式运行与交付按下文保留基线、结果包和复核记录。
- 按用户已授权的任务范围执行。Layout 建模或几何验证可在工作副本上执行 `runsetup()`。明确要求的仿真可完成所需的 `findmodes()`、`run()`、`runsweep()` 或 `emesweep()`，无需逐条确认。仅建模或只读任务保持在各自范围内。超出范围的高成本验证、覆盖用户原件或丢弃唯一有效结果需要确认。
- **实际求解使用可见会话**。以 `open_session(..., hide=false)` 打开求解会话。纯 Layout 建模、只读审计、controller、watcher、日志和归档脚本可以隐藏。
- 不发明材料、尺寸、边界、mesh、模式数或优化范围；能从输入文件发现的先审计，仍有高影响歧义时再询问用户。
- 用参数化structure group或可维护polygon生成器表示待优化器件；GDS可作真值和只读对照，不作为不可编辑的优化主体。
- 不把单档mesh、单一basis-mode数或单一纵向离散称为已收敛；报告准确的验证层级。
- 用实际结果、日志和重开证据证明成功，不以配置值、进程退出码或文件存在代替结果验收。

## 专用参考入口

- 光栅耦合器GDS复现、周期定义、Gaussian对光、原生Optimization、3D GPU宽带和GDS交付：完整读取 [references/grating-coupler-optimization.md](references/grating-coupler-optimization.md)。
- 参数化欧拉/一般变曲率弯曲、FDE/varFDTD/EME/FDTD分工、曲率离散、S矩阵和弯曲优化：完整读取 [references/eme-euler-bend.md](references/eme-euler-bend.md)。欧拉专用参数和流程只维护在该文件，主skill不复制。
- 偏振器件（PBS/PSR、起偏器、偏振旋转器和模式转换器）的参数语义隔离、structure group与仿真对象联动、PML直波导、TE/TM测量、原生Optimization/Parameter Sweep、结果交接和快速审计：完整读取 [references/polarization-device-simulation.md](references/polarization-device-simulation.md)。
- 从最终Layout FSP导出曲线GDS：完整读取并复用 [scripts/export_layout.lsf](scripts/export_layout.lsf)，只改顶部参数区，不重写主体。

## 通用脚本入口

- 批量执行PyLumerical MCP调用可复用 [scripts/pylumerical_mcp_stdio_runner.py](scripts/pylumerical_mcp_stdio_runner.py)。scenario保存有序tool calls、UTF-8 `code_file` 和可选JSON `code_context`。在任务范围内从可见会话求解。新建或改动scenario后可用 `--dry-run` 校验。
- FDTD、MODE/FDE、EME与varFDTD的通用Layout配置：复用 [scripts/configure_lumerical_project_via_mcp.py](scripts/configure_lumerical_project_via_mcp.py)。通过`code_context`传入named/global设置、structure group参数、`setexpansion`绑定、可选`runsetup`和readback；只允许显式fresh `save_as`，不求解、不自动`switchtolayout()`。
- 跨求解器只读配置/结果分析：复用 [scripts/audit_lumerical_project_via_mcp.py](scripts/audit_lumerical_project_via_mcp.py)。读取named object、global source/monitor、Sweep属性和原生`getresult()`，大数组只返回shape、有限值统计与小样本；不在通用脚本中预设器件FOM或模式语义。
- 配置原生Parameter Sweep或Optimization：复用 [scripts/configure_native_sweep_via_mcp.py](scripts/configure_native_sweep_via_mcp.py)。直接使用Lumerical原生parameter/result struct字段，先枚举再按显式`replace_existing`替换，并回读设置；脚本永不调用`runsweep()`/`emesweep()`。
- GDSII版图只读审计：复用 [scripts/audit_gds_geometry.py](scripts/audit_gds_geometry.py)。标准库解析cell、layer/datatype、BOUNDARY/BOX/PATH/TEXT、SREF、bbox、DBU和SHA-256；AREF等未展开内容必须保留warning，不能宣称几何完整。
- 从已审计的工艺层映射生成GDS重建LSF：复用 [scripts/generate_gds_import_lsf.py](scripts/generate_gds_import_lsf.py)。输入明确的GDS、cell、layer/datatype、material和可选Z范围，输出只做`gdsimport()`的Layout脚本；不猜材料/层叠，也不执行Lumerical。
- 生成文件树SHA-256清单：复用 [scripts/build_sha256_manifest.py](scripts/build_sha256_manifest.py)。默认拒绝root外输入；确需审计外部源文件时显式使用 `--allow-outside-root`，不得借此修改源文件。
- 审计单个working/best/candidate结果包：复用 [scripts/audit_lumerical_result_bundle.py](scripts/audit_lumerical_result_bundle.py)。它只读检查FSP、同名或内嵌引用H5及可选p0成功日志；正式门禁使用 `--strict`，但结果可读性仍须PyLumerical独立重开 `getresult()` 验证。
- 清理代目录前原子归档结果包：复用 [scripts/preserve_lumerical_result_bundle.py](scripts/preserve_lumerical_result_bundle.py)。它保持FSP引用的相对sidecar目录结构、复制并校验SHA-256，且拒绝覆盖已有目标；先用 `--dry-run` 核对源与目标。
- 审计原生Optimization代目录：复用 [scripts/audit_native_optimization.py](scripts/audit_native_optimization.py)。传入working FSP、Optimization名称、population和generation数；只有FSP、成功p0和非空H5齐全才计为完整candidate。该脚本不读取原生FOM/history，不得用其filesystem计数冒充Optimization最终结果。
- 上述Python脚本只使用stdlib，并通过 [scripts/_artifact_utils.py](scripts/_artifact_utils.py) 共享atomic JSON、流式SHA-256和GPU sidecar解析。优先参数化调用这些脚本，不在新项目中复制后再加入器件专用常量。

## PyLumerical MCP调用规范

1. 写任何Lumerical Python前调用 `get_guidelines_for("workflow")` 和 `get_guidelines_for("pic")`。
2. 按产品补充guidelines：
   - FDTD/varFDTD：`fdtd_workflow`，并按需读取geometry、materials、sources/monitors、run/results、mesh/convergence。
   - MODE FDE：`mode_fde_workflow`；结果提取再读 `mode_fde_results`。
   - MODE EME：`mode_eme_workflow`；扫描再读 `sweeps` 或 `nested_sweeps`。
3. 先 `list_sessions`，复用产品、文件和用途均匹配的会话，否则 `open_session`。任务结束时关闭本任务创建且无需继续监控或交接的会话，保留用户已有及其他任务的会话。
4. 用 `execute_python_code` 分阶段执行，从 `_lum_get(session_name)` 取得句柄。多行代码使用 `exec(compile(code,label,"exec"))` 整体提交。
5. 结构化返回使用 `_lum_print_json(...)`；大数组先降维或写入项目文件，不注入对话上下文。
6. 每个MCP envelope检查 `success=true` 且没有 `error`、`timed_out` 或意外 `retained`。
7. `restart_session` 会销毁所有live handles和未保存状态，只在确认会话失效且已保存可恢复文件后使用。

PyLumerical MCP只是控制入口，不等于求解器或GPU已经工作。MODE FDE/EME在本机v251使用CPU；3D FDTD GPU必须显式选择GPU资源并验证。

## 标准工作流

以下步骤按交付目标选用。已有可用基线或原生结果时先复用，已完成的阶段直接核对所需证据。

1. **定义目标**：器件功能、输入/输出模式、偏振、中心波长与带宽、材料层叠、制造约束、FOM、计算资源和验收阈值。
2. **审计输入**：区分已知参数、输入文件真值、论文公开值、本地假设和待用户确认项；记录坐标系、单位、端口和传播方向。
3. **选择求解器**：根据器件物理、长度、辐射和扫描规模选择FDE、varFDTD、EME或3D FDTD，并定义最终交叉验证层级。
4. **参数化Layout**：建立材料层叠、器件几何、直波导、source/ports、monitor和边界；保存无结果的基线工程。
5. **运行setup审计**：读取实际子对象和全局坐标，验证连续性、自交、最小特征、材料、mesh order、端口/source和边界。
6. **确定性基线**。需要基线时，在已授权的仿真范围内运行中心波长或低成本工况，验证模式、传播方向、归一化和FOM。
7. **扫描或优化**：使用用户确认的变量、范围、约束、算法和停止条件；原子保存state/history与全局最佳。
8. **独立复验**。交付经复验的最佳性能或确认候选需重跑时，从干净Layout应用参数。标记边界最优，其参数范围沿用任务设置。
9. **高精度和宽带验证**。按任务范围选择mesh、mode/cell和波长验证。可独立复验最终性能指标，并按实际比较范围报告收敛状态。
10. **重开与交付**。正式结果从最终交付位置独立重开，验证原生数据及其依赖，并按需要生成图表、manifest和SHA-256。保留不可变pre-run及完成求解的working结果包（含所依赖的H5）。仅在有交付需求时额外另存Analysis FSP。

## 求解器选择

| 求解器 | 优先场景 | 主要限制 |
|---|---|---|
| MODE FDE/FEEM | 横截面模式、`neff/ng`、偏振、局部弯曲模式 | 不代替完整器件传播与散射 |
| varFDTD | 近似平面器件快速初筛、低成本参数搜索 | 必须用更高保真求解器验证关键结论 |
| MODE EME | 长taper、MMI、方向耦合器、模式转换器、变曲率弯曲、长度扫描 | 强辐射、强反射或复杂垂直散射需FDTD验证 |
| 3D FDTD | 强散射、反射、辐射、光栅、紧凑三维结构和最终验证 | 计算与显存成本最高 |

先用低成本工具缩小参数空间，再用与目标物理匹配的高保真工具验证；不得把不同求解器结果混称为同一收敛序列。

## 参数化建模与几何审计

- 顶层controller管理材料、全局尺寸、求解参数和优化变量；structure group只重建材料几何，不读取仿真结果。
- 每次setup先清理该结构组的旧子对象，再按确定顺序重建；对象名、参数名、结果字段使用一致的物理语义。
- 对外user property、Optimization变量和关键子对象使用能直接定位物理区域的英文全名，例如 `Length_Bulge`、`Width_TaperInput`、`Output_wg`；禁止继续暴露 `A_L`、`B_H`、单独的`L/W`等需猜测的缩写。固定参数可以保留为可见属性，但必须从Optimization参数表移除并在manifest标明fixed。
- 直接用方程和参数范围保证单调性、连接和最小间隔；避免用clamp把不同非法候选映射为同一几何。
- 输入/输出直波导延伸穿过相关PML，port/source和monitor放在均匀直波导或均匀介质内。非光栅器件的FDTD边界不要无必要地进入高折射率substrate；光栅耦合器按衬底通道建模规则处理。
- 曲线使用基于弦高误差的自适应离散；审计实际最大弦高、顶点数、切线连续性和自交。
- 每次参数变化后执行setup并读取实际全局坐标，不只检查user property。
- 从GDS重建器件时，只导入或解析任务需要的工艺层；端口标记、边界参考和器件轮廓要分开处理。端口标记层只用于定位和宽度参考，不应被误导入为硅器件几何。
- 对会改变轮廓的参数扫描，优先在structure group内集中管理参数和几何重建。保存名义pre-run时恢复用户指定的基准参数，并记录参数单位、物理含义和默认值。
- 使用 `polygrow` 或等价几何偏置时，必须审计面积变化趋势、bbox、顶点数、自交、退化边、错误孔洞和与固定波导/端口区域的连续性。基准参数几何应在GDS DBU或项目指定容差内复现原始轮廓真值。
- 旧变量若同时驱动多个物理上独立的结构，先拆成独立变量；新变量的名义值先等于旧值，并用“名义、仅改新变量、仅改旧变量、组合改动”的setup矩阵证明基线几何不变且控制关系相互隔离。
- structure group负责真实器件几何；需要联动FDTD、source、monitor、包层、mesh或PML延伸时，由显式标记的顶层controller读取真实group属性并按物理依赖更新。禁止在顶层复制同名shadow参数，禁止移动与变量没有真实依赖的对象。
- 将均匀输出直波导明确拆为FDTD/PML内长度与边界外延长度；参数变化后读回taper端面、直波导中心线、monitor平面、FDTD边界和包层bbox，证明连续性与覆盖关系。

### SOI基础层叠

- Si芯层、BOX、top cladding和任务规定的substrate使用用户给定、PDK或输入文件审计得到的工艺值；禁止把某次工程厚度写成通用默认值。
- 以Si芯层中心 `z_si` 和厚度 `h_si` 定义 `si_z_min=z_si-h_si/2`、`si_z_max=z_si+h_si/2`。BOX连续占据 `[si_z_min-h_box, si_z_min]`；若建substrate，其顶面与BOX底面相接。
- top cladding从 `si_z_min` 连续延伸到项目定义的上边界，并在横向覆盖器件与求解区余量。它应包围Si并填充全刻蚀槽，不能在Si侧壁、槽底或BOX顶面留下非设计空气缝。
- top cladding的 `graphical rendering` 中 `alpha` 默认设为 `0.2`；仍需通过材料、mesh order和index截面验证物理结构，不能把透明度当作材料证据。
- 浅刻蚀使用“连续残余slab + 上层未刻蚀Si”或等价的显式差集；全刻蚀槽贯穿完整Si器件层；多刻蚀深度分别建立各层边界。不得用错误的对象优先级把残余slab意外清空。
- 光栅耦合器默认把Si substrate纳入FDTD，检查向衬底的辐射与反射；只有用户明确要求理想化无衬底模型时才可省略，并在manifest标注。衬底顶面与BOX底面连续相接、连续穿过底部PML；其有限深度必须用改变深度的中心波长检查确认，不能把“下边界停在BOX内”当作光栅仿真的默认。非光栅器件若无需substrate，才可按项目范围留在BOX内部并记录剩余厚度。

### Subtract、刻蚀与材料替换

- `subtract`表示“从基体中移除刻蚀区域”的物理语义，不假设存在通用的 `subtract()` LSF命令。按项目选择一种实现并写入manifest：直接生成差集后的Si polygon、使用Layer Builder的布尔/工艺层，或用重叠的etch/background对象替换Si。
- 参数化器件优先直接生成最终保留的Si几何；这样制造约束、最小线宽和GDS导出共享同一真值。复杂孔洞必须保留内外环方向/孔洞语义，不能用自交polygon伪造差集。
- 采用重叠材料实现刻蚀时，etch/replacement对象的材料必须等于刻蚀后真实填充介质，并且mesh-order优先级严格高于Si。背景不是空气时，禁止沿用默认 `n=1` etch材料。
- 普通top cladding不是etch mask：它与Si重叠时必须由Si胜出，仅在槽和Si外部填充。除非计划明确要求材料替换，不得让top cladding切掉Si。
- 2D对象始终优先于3D对象；需要在2D材料中开孔时，应直接构造带孔2D几何，不能依赖3D刻蚀对象覆盖。

### Mesh order硬规范

- 数字越小优先级越高。不同材料相交时不得使用相同mesh order，也不得依赖object tree先后顺序决定物理几何。
- 每个显式材料对象先设置 `override mesh order from material database=1`，再设置并回读 `mesh order`。GUI `alpha` 只影响显示，不能作为材料或刻蚀证据。
- 推荐起始约定为：Si器件 `2`，BOX/substrate `3`，top cladding `4`；明确的etch/replacement对象必须优先于Si（常用 `1`）。这是重叠解析约定，不是不可更改的材料常数；若项目修改，必须保持相对优先级并记录理由。
- `runsetup()` 后回读相关对象的材料、override状态、mesh order和全局bbox。正式验证、存在材料替换或重叠关系存疑时，用代表性index截面确认Si、槽、BOX和top cladding的实际解析。

## 模式、source、port与monitor

- 按物理属性识别模式：偏振比例、`neff`、confinement和场型；不永久依赖raw mode序号。
- **TE0 动态识别与选择硬性检查**：不得把 `mode 1`、`mode 2` 或任一固定 raw mode 序号永久写成 TE0。在包含横截面求模的任务中，FDE 用 `findmodes()`，EME 对每个 port 分别更新其 port modes。传播和扫描按任务范围执行。逐个候选回读与当前传播轴定义一致的 `TE polarization fraction`、复数 `neff`、loss、目标芯层 confinement/场分布和横向节点数；若 EME port 只返回 mode profiles，则按 MODE 原生定义从场重算，例如 x 方向传播使用 `∫|Ey|²dydz / ∫(|Ey|²+|Ez|²)dydz`，不得以单点场值或箭头方向代替。先排除 `Re(neff)` 不高于背景折射率数值容差、场不局域在目标芯层或辐射/包层模式，再在基阶无横向节点候选中选择 TE 占优且 TE fraction 最高的模式；强偏振自动选择时 TE fraction 应高于 TM fraction 并优先达到 80%，否则标记为偏振歧义并停止自动映射。双芯 FDE 必须识别同一 TE0 家族的两个偶/奇超模，不能只取单个最高 `neff` 模；EME 的输入与每个输出 port 必须各自独立求模和判断，禁止把一个 port 的 raw mode 序号复制给其他 port。正式结果记录并在重开时复核所选 port/FDE 名称、trial modes、raw mode 序号、TE fraction、`neff`、场/约束判据和最终选择规则。
- 需要逐模激励时每次只启用一个输入source，并同步更新输入/输出mode expansion或port模式映射。
- EME port定义模式边界，不是FDTD光源；FDTD mode source、Gaussian source和EME port不能混用语义。
- **FDTD Port频率轮廓硬规范**：建立FDTD Ports后，默认对所有参与激励或结果提取的输入/输出Port分别显式设置 `frequency dependent profile=0`，并从每个准确对象路径（例如 `FDTD::ports::<port_name>`）逐一回读为 `0`。只检查source Port不算通过。只有宽带模式色散、截面变化或基线证据表明单一中心频率轮廓不足时，才允许为特定Port启用该选项；启用时必须记录Port名称、理由、`number of field profile samples`、额外计算成本，并做频率采样收敛。不得依赖GUI默认值，也不得把Port group属性与具体Port属性混淆。
- **Port 截面覆盖硬性检查**：每个 FDTD mode source、mode-expansion monitor 或 EME port 必须在其法向截面内完整覆盖目标波导核心，并在两个横向方向保留足够的、均匀的背景/包层裕量以容纳倏逝场。端口的 `y/z` 中心应与目标波导核心中心对齐；其 `y span`、`z span` 均不得小于核心相应尺寸，且必须通过回读验证“核心 bbox 完全落在端口 bbox 内”。对于相邻波导间距远大于端口窗时，应采用局域窗口并确认不包含另一条波导；不得仅因图标箭头看似对准或方便起见而使用 `full simulation span`。端口窗口扩大后，同步确认其仍位于求解器横向域内、背景材料一致且未被 PML 截断。将核心 bbox、端口 bbox、两侧/上下包层裕量和是否包含非目标波导写入 manifest；获得运行授权后再对端口窗口与模式数做收敛检查。
- **EME port 放置与坐标模式硬性检查**：EME port 是 `EME::Ports` 下的 solver 子对象，必须显式设置并回读 `use relative coordinates`。优先使用相对坐标放置端口：局部坐标按 `port_local = target_global - EME_origin_global` 计算，输入/输出端的局部 x 应分别对应 EME 左/右边界，局部 y/z 应使换算后的全局中心与目标波导核心中心一致。若改用绝对坐标，必须在同一次原子更新中重写全部 x/y/z；禁止只切换复选框而沿用旧坐标值。`port location=left/right` 不能替代坐标审计。配置后回读并记录坐标模式、端口局部/绝对 x/y/z、EME 全局原点、换算后的端口全局坐标、目标波导端面全局坐标和三轴偏差；只有端口平面位于对应波导端面、横向中心偏差为零且窗口完整覆盖核心时才算放置通过。
- power monitor测总净功率；mode expansion测目标模式正反向功率；field/index monitor只为必要审计开启。FDTD Port已经提供任务所需的复数S参数/模式功率时，不再在同一截面添加重复的power monitor；只有需要独立能量闭合、辐射/非目标模式总功率或不同截面诊断时才额外添加，并在manifest记录其独立用途。
- 宽带power/expansion覆盖完整波段且包含中心波长。field monitor默认只记录中心波长，除非确需场频谱。
- 重命名或移动DFT/mode-expansion后，在同一次原子更新中重新执行 `setexpansion(expansion,dft)`，并同步修改Optimization/Sweep result路径与FOM脚本中的对象名；更新后从准确路径回读绑定，正式结果从交付位置重开时复核。旧result缓存、旧对象路径或仅GUI同位置都不能证明绑定有效。
- 正式结果从交付位置重开，按任务复核selected mode、偏振、波长点、归一化、传播方向和目标原生数据。

## Mesh、边界与执行门禁

- mesh accuracy编号不等于固定步长；记录实际网格或maximum step。局部mesh先覆盖完整关键材料几何，不通过平移造成另一侧失去覆盖。
- source/束腰局部mesh是独立的可选项，不因使用Gaussian source自动创建。用户要求“不加source mesh”时必须保持对象不存在；只有source profile、离散误差或收敛证据表明需要时才提出，并单独记录范围、步长和显存代价。
- 分开验证材料/横截面mesh、模式基组、纵向离散和时间/波长采样；只完成其中一项时准确标注。
- 对称边界要求几何、材料、source/port、monitor和目标模式奇偶性一致。用户未批准直接采用时，先做同配置全域/半域资格验证。
- 3D FDTD正式GPU运行前，在工作副本完成几何审计和 `runsystemcheck("FDTD","GPU")`，并核对当前空闲显存。预检使用与运行一致的配置，从磁盘载入或工程保存行为存疑时独立重开核对。预计超过项目显存预算时先排查资源占用，再按任务范围处理。更换资源或降低精度时核对用户要求。
- 局部mesh优先覆盖主要散射、耦合、分光或强场变化区域；不要为了图上美观把mesh铺满长直波导、端口或低影响弯曲段。改变mesh步长做敏感性比较时，保持bbox、边界、端口、源、波长和结果提取定义不变，只改变待比较的mesh参数。
- 打开或切换求解会话时确认 `hide=false` 且窗口可见。同一会话继续求模或扫描时复用该确认，窗口状态异常时复查。若当前只有隐藏建模会话，将Layout保存到工作副本后以 `hide=false` 打开求解。出现GPU资源未激活等警告时先修正资源配置再运行。
- 正式运行保留原始pre-run，从独立工作副本求解。Lumerical可能原地更新当前FSP或同名外部结果目录。只有求解返回、会话进入Analysis且目标原生结果可读时，才将工作工程标记为已完成结果。
- 用求解日志和原生结果核实实际资源及完成状态。资源或结果异常时再查 `fdtd-engine`、显存、auto-shutoff和controller状态。
- 自动化脚本写入阶段状态与error文件；长任务按完成事件更新，不用固定高频轮询。
- 短批次汇总运行状态和关键结果。长任务在阶段完成、出现有意义的新最佳、异常或需要用户操作时更新。

## 优化与容错

- 在明确的线性功率域定义FOM，并在metadata记录公式、权重、方向、模式和monitor/result路径。
- 优先使用Lumerical原生Optimization处理连续变量；计划中明确算法、变量、范围、约束、generation size、最大代数、容差和随机策略。
- 原生Optimization只调用一次 `runsweep(optimization_name,resource)`；Lumerical随后自动推进各代。保持启动它的可见PyLumerical会话存活到终态并在关闭前提取原生history/result；不得按代重复启动。MCP连接中断时先只读检查solver、generation目录、p0日志和state，确认原任务已终止后才允许新启动。
- 首次验证数据链路时，可在用户授权的较低mesh或极小population/generation上运行独立pilot；pilot只验证solver、FOM、候选保存和结果读取，不代表优化效果。正式mesh必须从干净Layout创建新的working FSP，不得把pilot结果或状态续接为正式Optimization。
- 优化参数盒应天然满足制造约束。可在仿真前拒绝自交、断开或非法尺寸；模式映射、缓存和求解器异常必须停止任务，不能当普通低FOM候选。
- 运行自定义优化时按可恢复的阶段原子保存state/history。原生优化结束后验证原生result和history，保留全局最佳及任务所需的复验和代际记录。
- **GPU Optimization结果捆绑硬门禁**：GPU candidate只有在candidate FSP、成功p0日志及其同目录同名sidecar `<candidate>/<candidate>_output.h5` 均存在且H5非空时才能计为完成；不得仅按FSP数量或成功日志计数。轮询时先检查确定性的同名sidecar路径，只在路径异常时读取FSP内嵌引用，避免反复扫描大型FSP。
- 原生 `*_best_solution.fsp` 可能引用candidate的相对H5路径。全局最佳更新时记录对应candidate及H5引用，保留仍被引用的文件。清理相关代目录前或正式交付时，原子归档best-solution FSP及其准确相对路径下的H5，并检查大小和SHA-256。`resave files after analysis=1` 只重新保存candidate FSP，GPU monitor数据仍依赖H5。
- 交付前从最终位置独立重开best/working FSP，要求Analysis mode、目标 `getresult()` 成功、schema/点数/有限值正确且sidecar SHA匹配。若引用的H5已丢失，旧FSP结果不可无损恢复；保留故障证据，从干净Layout应用同一最佳参数，以同一solver、mesh和波段显示重跑生成新的working FSP+sidecar，不用重新保存旧FSP冒充修复。
- 原生PSO按“完整一代”提交代际快照：记录计划粒子数、已提取粒子数、该代最佳、累计最佳、边界状态和时间戳。部分代不得覆盖上一完整代的全局最佳，也不得用于最终3D结构，除非用户明确选择该候选并完成独立复验。
- 运行中若原生history尚未落盘，只能对“p0成功且sidecar完整”的稳定candidate做无run、无save只读诊断，并明确标记 `partial-generation diagnostic`；它不能冒充完整代最佳，也不能覆盖上一完整代最佳。
- 将效率目标与FOM分离：目标值只是验收阈值，不得为追求目标而改符号、归一化或篡改Optimization FOM。总运行上限必须与 `generation size × maximum generations` 一致；暂停、停止和续跑遵守用户最近指令，不重复启动仍在运行的Optimization。
- 按已授权的计划完成优化、独立复验和最终宽带。提高mesh、切换求解器或新增宽带验证会改变范围或计算预算时先确认。
- 形状优化先基于失效机理收缩参数空间：若弯曲损耗不是主要问题，应优先优化中心分光/散射区域，固定输入/输出直波导、端口坐标和低影响长弯曲。参数数量、粒子数和代数要与计算预算一起显式记录；用户要求简化时，先减少物理冗余参数而不是改变FOM定义。
- 不要把额外工艺变动或鲁棒性约束自动加入Optimization，除非计划中明确要求。名义优化完成后，再用独立Layout和独立扫描工程做后续验证；验证失败是后续结论，不应回写成优化历史中的伪约束。
- 用户要求停止Optimization时，立即停止提交新任务并确认无残留求解/优化进程；只把已完成的完整代或已独立复验候选作为可交付最佳点。停止后的后续验证必须从该最佳点的干净Layout副本开始。

## 结果、图表与证据

- 保存原生功率/Transmission、模式结果、完整S矩阵或当前求解器的等价原生dataset；使用离线overlap时说明归一化、公式和限制。
- 多端口/多模器件保存完整复数S矩阵、功率矩阵、mode mapping、passivity、reciprocity和能量闭合，不只保存单个 `S21`。
- 每个波长光谱输出两张独立图：线性效率/透射率图，以及对 `eta>0` 样本直接计算的 `10*log10(eta)` 负dB图。禁止用 `max(eta,1e-12)`、`epsilon` 或其他固定下限抬高低功率点；`eta=0` 保留为 `-Inf`，`eta<0` 标记为无效值并停止将其解释为物理透射率。两图的波长、采样、曲线名称和颜色一致，并在manifest记录零值、无效值及“未使用数值截断”。
- 负dB图默认只固定纵轴上限为 `0 dB`，下限由有限的正值样本自动确定；不得为了显示而修改原始线性数据或写入人为的有限dB下限。
- 正损耗 `-10*log10(eta)` 可作为摘要指标，不得代替负dB光谱或混淆符号。
- 报告中心波长、峰值和位置、1/3 dB带宽、模式占比/串扰和边界截断状态；窗口边界峰值不得宣称为真实峰值。
- 最终结论区分baseline、优化最佳、独立复验、宽带、网格、mode/cell收敛和工艺变动验证。
- 数据交付优先保存可复算的逐点CSV、按扫描变量汇总CSV、单行摘要CSV和manifest。CSV行数、扫描点数、波长点数、单位和列名必须可由manifest复核；图表只作为呈现，不作为唯一数据源。
- 作图先确定指标定义和单位，再画图；同一指标的不同曲线使用一致采样和颜色语义。用户已经给出坐标轴文字或字号偏好时严格使用；不要把内部mesh标签塞进标题。

## 项目结构、归档与清理

建议按以下职责组织，不强制具体文件名：

```text
<project>/
├── src/       # UTF-8建模、运行、提取与审计脚本
├── projects/  # Layout/Optimization模板与working结果工程
├── data/      # CSV/JSON/NPZ/MAT/HDF5与manifest
├── figures/   # 线性和负dB图、必要场图
└── logs/      # MCP、controller、solver和GPU日志
```

- FSP/LMS依赖外部HDF5时，将工程和数据目录作为不可拆分的一组移动、重命名和归档。
- 路径含空格导致Lumerical脚本或批处理截断时，优先迁移到项目内无空格目录并同步更新脚本、manifest和关联路径；不要在路径解析不可靠的状态下继续运行长任务。
- 不同器件、mesh档位、优化候选和参数扫描验证使用独立运行空间；不要覆盖既有mesh档位、pre-run、working结果或历史sweep结果。目录名中包含器件、候选、mesh和阶段语义，避免后续把敏感性比较误认为收敛。
- 正式运行分离不可变pre-run与工作工程。将Analysis状态的working FSP及所依赖的H5作为结果来源。正式交付、迁移或清理前归档时记录相应文件的SHA-256。
- 用户在GUI中手工保存参数、脚本、对象名或monitor位置后，旧SHA、坐标审计和绑定审计立即失效；先把最新磁盘FSP视为新输入并重新记录SHA/差异，再继续自动修改。不得覆盖用户当前仍打开的目标FSP；优先让用户关闭后处理，或改用新的fresh working副本。
- 需要切回Layout时优先使用独立副本，保护用户原件和唯一有效Analysis。对要删除或清除的有效结果，先保存所需原生数据、可复算数据及其依赖，从保留位置重开验证后再按授权处理。
- 解析所有删除目标的绝对路径，确认位于项目根内；永久删除唯一Analysis、外部HDF5或有效优化历史需要用户明确授权。
- 清理后更新已有manifest，核对本任务待关闭的会话。

## v251简要陷阱

- `.lsf`由 `fdtd-solutions.exe -run` 执行，不直接交给 `fdtd-engine.exe`；可见运行不要依赖已观察到不稳定的 `-trun`。
- 路径含空格导致脚本加载失败时，使用无空格运行目录和相对路径，不猜测GUI是否执行。
- 新建FDTD频域monitor使用 `adddftmonitor`，避免已废弃的 `addpower`。
- `length(matrix)`不保证返回行数；需要行数时使用 `length(mtx(:,1))`。
- 设置mesh order前开启material-database override。
- `runsweep()`/`emesweep()`返回不代表结果一定存在；立即检查result schema、点数和数值。
- 调用 `deletesweep(name)` 前先枚举并核对真实sweep/Optimization名称；对象不存在时跳过并记录，不制造无意义warning。Optimization名称、自动生成job名和路径组合应保持简短；保存失败时先检查完整路径长度、目录权限和剩余空间，不把失败候选当作低FOM继续。
- 多行MCP代码整体compile；遇到dimension/cache错误关闭污染会话，从干净工程重开并先读最稳健的原生结果。

## FSP 保存与运行资源

- FSP资源配置沿用任务指定的CPU或GPU。指定GPU求解时，求解前显式选择并检查GPU资源。交付供用户直接点GUI Run的GPU FSP时，保存前回读所需GPU资源已启用，并核对进程及线程配置。

- 自动化GPU求解使用对应调用的显式GPU资源参数，例如 `runsweep(name, "GPU")`。保留可用于确认实际执行资源的求解记录。

## 最终验收

按本次交付选用检查项。只读审查复核所用数据和结论。纯Layout交付核对所需配置与几何。正式求解结果交付使用相应的运行、数据和结果包检查。

- [ ] 需求、工艺、坐标、模式、FOM、资源和授权已明确。
- [ ] 若交付新建或修改的模型，Si、BOX、top cladding和刻蚀深度与工艺一致，z边界连续。光栅报告所用Si衬底、深度/PML敏感性验证状态及理想化例外。
- [ ] 参数化几何setup后通过连续性、最小特征、材料、端口/source、monitor和边界审计。
- [ ] 涉及重叠材料时核对mesh order。正式验证或存在重叠歧义时用index截面复核实际材料。
- [ ] 求解器与物理问题匹配，低成本优化和高保真验证没有混称。
- [ ] mesh、模式基组、纵向离散和宽带验证状态分别标注。
- [ ] 优化的边界最佳已标记，最佳点的独立复验状态与交付结论一致。
- [ ] 已求解的目标原生数据可读、非空，点数、有限值和归一化通过复核。正式结果有资源证据和适用的图、manifest与SHA-256。供GUI直接运行的GPU工程已核对资源启用。
- [ ] GPU Optimization的candidate与best-solution FSP均保留其准确相对路径的非空H5 sidecar；完成计数、SHA256和独立重开 `getresult()` 已通过。
- [ ] 不可变pre-run与working结果包语义分离；working FSP/H5是结果真值，未在无明确需求时制造额外Analysis FSP。
- [ ] Gaussian source没有被自动附加source mesh；若存在source mesh，已有明确理由、范围、显存和验证证据。
- [ ] 最终工程与外部数据可从交付位置重开。
- [ ] 清理符合授权。本任务无需继续使用的会话已关闭。
