# 光栅耦合器通用设计、优化与交付规范

## 目录

1. [适用范围与求解门禁](#适用范围与求解门禁)
2. [任务定义与用户确认](#任务定义与用户确认)
3. [通用参数化接口](#通用参数化接口)
4. [GDS真值审计与参数提取](#gds真值审计与参数提取)
5. [材料层叠与参数化建模](#材料层叠与参数化建模)
6. [Gaussian、角度与落点口径](#gaussian角度与落点口径)
7. [基线、对光与原生Optimization](#基线对光与原生optimization)
8. [Anti-Symmetric、mesh与GPU门禁](#anti-symmetricmesh与gpu门禁)
9. [monitor、结果重开与v251稳定性](#monitor结果重开与v251稳定性)
10. [指标、光谱图与带宽](#指标光谱图与带宽)
11. [GDS导出、归档与清理](#gds导出归档与清理)
12. [交付检查表](#交付检查表)

## 适用范围与求解门禁

将本规范用于聚焦或非聚焦、均匀或apodized、全刻蚀/浅刻蚀/多刻蚀深度的光栅耦合器，以及位置、角度、光程、结构和制造容差优化。

必须遵守：

- 通过PyLumerical MCP控制Lumerical；先读取 `workflow`、`pic`、`geometry`、`fdtd_workflow`、`fdtd_sources_monitors`、`fdtd_run_and_results` 和按需的 `sweeps` guidelines。
- 先完成Layout、参数审计、source profile和资源预检，再决定是否运行。
- 分别获得 `run()`、`runsweep()` 和 `switchtolayout()` 的明确授权；优化授权不自动包含最终3D运行或丢弃结果授权。
- 不把单独一档mesh结果称为已收敛，不把扫描窗口边界最大值称为真实峰值，不把配置成功称为GPU实际运行成功。
- 每个MCP阶段核对 `success=true`，并保证没有 `error`、`timed_out` 或意外 `retained`。

## 任务定义与用户确认

在生成最终结构或Optimization对象前，先从输入资料提取可确定事实，再让用户确认仍有歧义的设计选择。至少锁定：

1. 几何来源：GDS、论文/版图参数或从零设计。
2. 工艺：全刻蚀、浅刻蚀、多深度刻蚀，以及Si、BOX、top cladding和可选reflector。
3. 周期方向：从光栅内侧到外侧，或沿输入到输出传播方向。
4. 周期内有序分段。要求用户用有序序列回答，例如 `gap → Si`、`Si → gap` 或自定义多段；例子只说明格式，不得被自动选为默认值。
5. 起始边界：connector真实边缘、波导边缘或指定坐标。
6. 终端策略：普通周期结束、末段与连续tail合并、末端gap延伸或自定义结构。
7. 周期数、优化变量、范围、派生变量、最小线宽/间隙和其他制造约束。
8. 中心波长、波段、偏振、入射方向、Gaussian MFD、waist位置、角度和落点定义。
9. 对称边界：直接采用、先做资格验证或使用全域。
10. 优化与最终仿真完成后是否导出GDS。用户已在同一请求明确要求时不重复询问。

若GDS可支持多种周期解释且用户尚未确认，只进行只读GDS审计、候选参数提取和差异说明；不生成最终结构、不添加Optimization、不启动求解。

## 通用参数化接口

在controller和manifest中用逻辑接口 `period_segments` 保存一个周期的有序分段：

```text
period_segments = [
  {name, kind, material_or_void, width_parameter, derived}
]
```

- `name`使用用户确认的物理语义；`kind`区分材料段、gap/刻蚀段或其他工艺段。
- 顺序就是几何生成顺序，禁止在setup script内按固定的gap-first或Si-first模板重新排序。
- `period = sum(segment widths)`。允许一个宽度由period和其他段派生；若有多个依赖量，必须写出无歧义方程组。
- 将逻辑分段映射为Lumerical structure group的独立user property；对象名、Optimization参数路径和审计字段沿用相同语义。
- 用 `n_periods`、`start_boundary`、`terminal_policy` 和 `terminal_extension` 分别控制周期数、首段位置和末端拓扑。
- 对聚焦光栅，可用 `outer_radius=start_radius+n_periods*period+terminal_extension`。`half_angle`仅控制角向范围，不得隐式改变outer radius。
- 优化参数盒必须在所有组合下满足最小特征、宽度和守恒关系；优先用边界代数/区间最坏值证明，不用clamp把非法候选压成合法几何。

接口改变或用户更改分段顺序时，建立新的 `topology_version` 和独立目录；不得复用旧候选、旧Optimization history或结果缓存。

## GDS真值审计与参数提取

1. 审计library、TOP cell、layer/datatype、DBU、单位、bbox、polygon/path/text/port数量和源文件SHA256。
2. 让用户确认每个器件层的工艺语义；不要把某个项目的 `1/0`、`2/0` 含义写成通用事实。
3. 忽略边框、文字和端口标注前先记录其层号和用途。
4. 只对完全重合、同层、同材料、同工艺语义的polygon去重；保存原始数、唯一数、polygon哈希、来源索引和重复次数。
5. 选择端口焦点、波导中心或用户指定点作为模型原点，记录刚体变换和传播方向。
6. 提取候选周期方向、有序分段、起始/终止边界、connector轮廓、周期数、扇区角和波导宽度；有多种解释时交给用户选择。
7. 用参数化structure group重建，不把不可编辑GDS polygon作为优化主体。可保留只读GDS对照对象，但默认禁用求解。
8. 根据GDS DBU和边界拟合误差设定重建容差；逐边界报告误差，不能只比较总bbox。

对曲线轮廓按弦高误差自适应增加顶点。目标必须为正的亚纳米值，默认0.25 nm；禁止用固定低顶点数近似圆弧。记录目标弦高、实际最大弦高和每个polygon顶点数。

## 材料层叠与参数化建模

- 分离材料层叠、connector/taper、周期结构、输入/输出波导和terminal结构；结构组只重建几何，不读取仿真结果。
- 全刻蚀用实际穿透Si层的gap表示；浅刻蚀用连续下层Si和未刻蚀上层Si表示；多深度刻蚀为每个深度建立明确层级。不要用对象重叠偶然得到目标刻蚀深度。
- 让BOX和top cladding连续覆盖器件范围，由top cladding自然填充刻蚀区域；若建立显式填充对象，审计材料优先级和重叠。
- Si使用高于包层的mesh优先级，并启用 `override mesh order from material database` 后再设置mesh order。
- 直波导穿过侧向PML；FDTD下边界停在BOX内或低风险区域，不进入高折射率substrate。

每次 `runsetup()` 后审计：

- 周期内分段顺序与用户确认完全一致。
- 每段宽度、周期和派生关系满足容差及制造约束。
- 所有径向/纵向边界单调，没有自交、断开或非预期重叠。
- 首段从确认的start boundary开始；末周期符合terminal policy。
- 子对象数量、材料、z范围、mesh order、全局坐标和命名正确。
- 临时改变至少一个参数后能重建，再恢复默认值并重新审计。

## Gaussian、角度与落点口径

显式电磁光纤与Gaussian等效模型二选一，不得作为两个独立激励同时启用。

Gaussian规则：

- 使用 `w0=MFD/2`；`distance from waist`表示waist到source注入面的有符号光程，不等同于垂直机械间隙。
- source位于均匀介质内，并设置足够span；用source profile检查边缘截断、传播方向、会聚/发散和偏振。
- 将物理角度、Lumerical原生 `angle theta/phi`、注入轴和传播方向同时写入manifest；不能只看角度属性值判断方向。
- offset统一定义为芯片目标平面的实际落点偏移。空气、top cladding或其他介质分段传播时，用折射关系从落点反算source坐标。
- 距离或角度研究必须注明固定落点、固定source横坐标或每点重新对光，三种口径不得混用。
- Lumerical v251 Gaussian GPU工作流保持 `frequency dependent profile=0`；在setup、保存、system check和正式运行前重新设置并读取确认。

若使用显式光纤，建立core/cladding/端面和光纤模式源，并将Fresnel反射及端面纳入模型；不再叠加Gaussian source。

## 基线、对光与原生Optimization

按成本从低到高执行，具体阶段由用户批准的任务计划选择：

1. 建立确定性Layout基线，记录几何、source、monitor、边界、mesh和波段。
2. 在中心波长验证传播方向和落点。需要独立对光时，先关闭局部mesh和非必要monitor，做覆盖正负offset的总功率扫描；边界最优则扩展，直到峰值被两侧实测点包围或达到安全边界。
3. 需要目标模式时，在总功率候选附近做TE0细扫，并用实测点包围峰值，不只依赖拟合。
4. 若用户选择联合优化，将offset和确认的几何变量一起加入FDTD原生Optimization；不要固定优化period、fill factor或etch depth，除非当前任务确实选择这些变量。
5. 从干净Layout应用最佳参数并独立运行复验；复验通过后才能进入3D宽带验证。

对光扫描先在manifest定义物理offset零点、正方向、source坐标映射、范围、步长和mesh层级。优先采用稀疏粗扫，再在实测最佳点附近细扫；已有有效采样点必须复用，只追加未覆盖点，不因调整步长而从头重跑。用户要求停止或手动关闭后，先审计现存结果和job状态，不自动重启。

连续原生Optimization优先采用 `addsweep(1)`、`addsweepparameter` 和 `addsweepresult`。任务计划必须明确：

- Optimization名称、算法、Maximize/Minimize、generation size、最大代数、容差和随机种子策略。
- 每个参数路径、物理含义、上下界和单位。
- 线性功率域FOM、传播方向、monitor/result路径及多目标权重。
- 制造约束证明、停止阈值和边界最优策略。

只在一代完整结束后判断代际停止条件。最佳参数位于范围边界时标记 `boundary-best`，不自动扩大用户确认范围。保存best FOM、best parameters、trend、完整history和Optimization FSP。长任务只在新最佳或阶段切换时给出实质更新；必要心跳保持简短。

原生PSO每个完整generation原子写入快照，至少包含 `completed/expected`、本代最佳、累计最佳、全部参数、派生尺寸、是否触边和距验收目标的差值。部分代不得冒充完整代；停止后最终结构默认取最后一个完整代的全局最佳。验收目标只比较独立复验后的线性效率，不修改FOM。调用 `deletesweep` 前先确认对象实际存在；缺失对象直接跳过，避免把清理warning误报成仿真失败。PSO名称和输出路径保持简短，预先检查自动job文件完整路径，避免Windows路径过长导致保存失败。

## Anti-Symmetric、mesh与GPU门禁

只有几何、材料、source、monitor和目标模式关于对称面满足正确奇偶性时才使用Anti-Symmetric。

- 用户明确确认直接采用时，记录其依据；否则用相同几何、source、monitor、x/z边界和mesh比较全域PML与半域中心波长结果，并在manifest定义效率、dB和方向阈值。
- source横向偏移、非对称apodization、非对称材料/刻蚀、非对称monitor或模式奇偶性变化后，重新判断资格。
- v251可保留完整几何y span并在y-min设置Anti-Symmetric；不要手工裁半几何后又依赖求解器镜像。记录求解前边界标签和重开后的实际显示范围。
- 网格比较使用相同对称边界，不能把全域和半域混入同一收敛序列。

局部mesh规则：

- grating local mesh覆盖全部允许的周期结构、terminal及Si厚度附近；优先扩大span，不用平移mesh造成另一侧结构失去覆盖。
- Gaussian source/束腰mesh不属于默认配置。用户要求不加source mesh时保持对象不存在；仅当source profile或专门的mesh比较证明需要时才单独增加，不能把grating mesh和source mesh合并成无法独立审计的对象。
- 用户提供参考FSP作为mesh真值时，独立重开并回读mesh对象名称、启用状态、bbox、`dx/dy/dz` 和相对/绝对坐标，再移植到新工程；不得凭截图或文件名猜测。
- 同时记录x/y/z override及实际 `dx/dy/dz`；mesh accuracy编号不等同于固定网格尺寸。
- 至少比较两档有效mesh才能讨论网格收敛；单档结果只标记为该档局部细网格结果。
- 关闭不用于当前FOM的field/index/air monitor，避免无谓显存与结果缓存。

GPU门禁：

1. 完成setup、source、monitor、边界和mesh后保存精确pre-run FSP，记录运行前SHA256，关闭会话并独立重开审计。
2. 将pre-run保存为不可变快照；另建运行工作副本。不要在唯一pre-run快照上调用solver，因为Lumerical可能原地更新当前FSP及同名外部结果目录。
3. 在运行工作副本执行 `runsystemcheck("FDTD","GPU")`，记录最小/最大显存估算。几何审计后、正式运行前重新读取当前空闲显存；超过计划安全线即停止，不自动降mesh或转CPU。
4. 正式运行前重新读取对称边界和 `frequency dependent profile=0`，显式选择GPU资源。
5. 只有 `run("FDTD","GPU")` 返回且会话处于Analysis mode后才保存Analysis FSP。门禁失败、中止、异常或返回Layout mode时不得创建或保留带Analysis语义的FSP。
6. 用GPU资源配置、`fdtd-engine`进程、p0日志、显存、auto-shutoff、controller状态和最终Analysis结果共同证明GPU执行；任务管理器单个默认图表不是唯一证据。

## monitor、结果重开与v251稳定性

- `wg_power`输出波导总净功率，适合基线和总功率FOM。
- mode expansion输出目标模式正向/反向功率；按物理TE属性选择模式，不永久依赖raw mode序号。
- field monitor只在传播和落点审计需要时开启，默认只记录中心波长；index monitor默认关闭。
- 检查传播方向及 `0≤TE0≤wg_power≤1`（允许数值容差），计算 `TE0 fraction=TE0/wg_power`。

结果重开分离执行：

1. 在独立会话读取原生 `wg_power -> T`，并与 `transmission("wg_power")` 比较点数、波长和数值。
2. 通过后在另一个会话读取TE0 expansion，避免脆弱的expansion调用阻断原生Transmission审计。
3. 原生dataset不可用时，允许导出原始E/H、source power和频率匹配mode basis进行离线功率或overlap；必须记录公式、归一化、grid-dispersion限制及其与原生结果的差异，不能冒充原生dataset。

v251规则：

- 新建频域monitor使用 `adddftmonitor`，静态扫描保证 `addpower(` 为0。
- 不启用Gaussian `frequency dependent profile`；若出现dimension error，关闭污染会话，从干净FSP重开并先测试原生Transmission。
- `frequency dependent profile=0`时日志中的narrowband spatial injection提示不代表DFT只计算单点；以source波段、monitor点数和重开波长数组判断宽带结果。
- 不把 `updatemodes("monitor")` 当作通用调用；先在对象属性中选模式并审计。
- 结果FSP与同名外部HDF5目录作为不可拆分的一组移动、重命名和归档。
- pre-run快照、运行工作副本和Analysis FSP不得混用命名或成功状态。manifest分别保存运行前/后SHA256、solver是否启动、Analysis是否创建、p0路径和最终会话模式；若运行工作副本被原地改写，不能把其运行后哈希当作原始pre-run哈希。
- MCP多行Python使用 `exec(compile(code,label,"exec"))` 整体提交。

## 指标、光谱图与带宽

统一计算：

```text
eta_TE0 = 目标TE0正向功率 / 输入功率
eta_wg  = 输出波导总净功率 / 输入功率
TE0_fraction = eta_TE0 / eta_wg
coupling_dB = 10*log10(max(eta, epsilon))
positive_loss_dB = -coupling_dB
```

每个宽带结果输出两张独立图片：

- 线性效率/透射率纵轴。
- 负值dB纵轴，严格使用 `10*log10(max(eta,epsilon))`；不得用正损耗替代。

两图必须使用相同波长范围、采样点、曲线名称、颜色和中心波长标记，并在manifest记录epsilon、源CSV SHA256和图文件SHA256。摘要可另报正损耗，但必须与负dB图符号明确区分。

报告中心波长效率、峰值效率和波长、TE0占比、1 dB/3 dB带宽及左右边界。峰值或带宽阈值触及仿真窗口时标记为censored/未找到完整边界，不外推成完整带宽。

## GDS导出、归档与清理

用户确认导出后，等待最终参数和验证完成，再从独立最终Layout FSP复用 `scripts/export_layout.lsf`：

- 只修改顶部 `project_filename`、cell名、材料截面和layer/datatype定义，不重写主体。
- 通过PyLumerical MCP执行；脚本只读取FSP几何，不调用solver、`runsetup()`或保存FSP。
- 使用 `polystencil()` 的亚纳米 `curve_chord_tol` 自适应离散；保留孔洞拒绝、退化polygon和8190顶点检查。
- 导出后审计cell、layer/datatype、BOUNDARY数、DBU、bbox、最小制造特征、顶点数、弦高目标、字节数和SHA256。
- 保留Analysis FSP及外部HDF5不动；导出源Layout FSP也要保存SHA256。

最终保留：最终Layout/Analysis FSP、外部HDF5、Optimization与独立复验、轻量扫描/资格JSON、宽带CSV/数组、两张光谱图、GDS、GPU日志和总manifest。

删除前解析绝对路径并确认位于项目根目录内，记录路径、原因、大小和SHA256。永久删除、把唯一Analysis切回Layout或删除其HDF5都需要明确授权。完成后关闭PyLumerical会话，并确认 `list_sessions` 为空。

## 交付检查表

- [ ] 已确认几何来源、刻蚀类型、周期方向和有序分段；没有套用固定周期模板。
- [ ] 已确认start boundary、terminal policy、制造约束和派生宽度方程。
- [ ] GDS层语义、DBU、端口、重复polygon、坐标变换和SHA256已审计。
- [ ] setup后逐周期顺序、宽度、边界单调性、首段、末端和对象数量通过审计。
- [ ] Gaussian/显式光纤路线唯一；MFD、waist距离、角度、偏振和芯片落点定义明确。
- [ ] 优化变量、范围、FOM、停止条件和求解授权与任务计划一致。
- [ ] 最佳点从干净Layout独立复验；边界最佳已标记。
- [ ] Anti-Symmetric由用户直接确认或完成资格验证；不满足条件时使用全域。
- [ ] grating local mesh与可选source mesh独立审计；用户要求不加source mesh时对象数为0；单档mesh没有被称为收敛。
- [ ] 精确pre-run FSP已完成GPU system check，GPU执行证据完整。
- [ ] 不可变pre-run快照、运行工作副本和Analysis保存顺序正确；失败路径不会留下伪Analysis。
- [ ] `frequency dependent profile=0`在正式运行前后均已审计。
- [ ] 原生Transmission先于TE0读取；离线后处理限制已披露。
- [ ] 线性图和负dB图的波长、采样、曲线和颜色一致。
- [ ] 最终Analysis FSP与外部HDF5可从交付位置重开。
- [ ] GDS来自独立Layout FSP，并完成层、几何、弦高和SHA256审计。
- [ ] 清理manifest完整，最终PyLumerical `list_sessions`为空。
