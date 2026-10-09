# 参数化欧拉弯曲设计、仿真与交付规范

## 目录

1. [适用范围与任务确认](#适用范围与任务确认)
2. [求解器分工](#求解器分工)
3. [通用参数化接口](#通用参数化接口)
4. [欧拉曲率与几何生成](#欧拉曲率与几何生成)
5. [EME cell groups与模式映射](#eme-cell-groups与模式映射)
6. [基线、优化与独立复验](#基线优化与独立复验)
7. [收敛与高保真验证](#收敛与高保真验证)
8. [3D FDTD弯曲波导的贴边mesh与内存预检](#3d-fdtd弯曲波导的贴边mesh与内存预检)
9. [宽带、S矩阵与图表](#宽带s矩阵与图表)
10. [结果归档与清理](#结果归档与清理)
11. [验收检查表](#验收检查表)

## 适用范围与任务确认

将本规范用于平面Euler/clothoid弯曲、部分欧拉弯曲、对称或非对称变曲率弯曲，以及半径、长度、宽度、模式串扰和带宽优化。不要把某个固定角度、段数、半径或模式数量写成所有弯曲的默认值。

开始建模前确认：

1. 几何来源：解析曲率、论文/GDS复现或从零设计。
2. 输入/输出端点、切线方向、总转角和传播方向。
3. 曲率定义：纯Euler、Euler+圆弧、对称双Euler、非对称profile或用户自定义 `kappa(s)`。
4. 起点/终点曲率、最小/最大半径、Euler段长度、可选圆弧长度和直波导长度。
5. 波导宽度、Si厚度、BOX、top cladding、刻蚀与材料模型。
6. 输入/输出模式、需要保留的模式数、偏振和波段。
7. 优化变量、范围、最小内侧半径、最小间距、footprint和其他制造约束。
8. 主求解器、最终验证求解器、mesh/basis/cell收敛要求和验收阈值。
9. 是否需要最终GDS，以及允许的曲线弦高误差。

若输入资料对曲率profile、参考半径或端点切线有多种解释，只完成只读审计和候选方程说明，待用户确认后再生成最终结构。

## 求解器分工

- **MODE FDE/FEEM**：求直波导或局部常曲率截面的模式、`neff/ng`、偏振、confinement和局部辐射趋势；不能替代完整弯曲传播。
- **varFDTD**：平面器件和大参数空间的快速初筛；最终关键点用EME或3D FDTD验证。
- **MODE EME**：长弯曲、缓变曲率、多模传播、半径/长度扫描和完整S矩阵；强辐射或急剧不连续时必须评估其适用性。
- **3D FDTD**：紧凑强散射弯曲、反射/辐射/场泄漏分析及少量最终高保真验证点；不默认承担全部大规模扫参。

通过PyLumerical MCP操作：先读取 `workflow`、`pic` 和对应FDE/EME/FDTD guidelines，再 `list_sessions` / `open_session`。MODE EME/FDE在本机v251使用CPU；只有3D FDTD可按GPU流程执行。

`run()`、`emesweep()`/其他sweep和 `switchtolayout()` 分别需要明确授权。EME GUI保持可见；不要在MCP snippet中重新导入或实例化 `lumapi`。

## 通用参数化接口

在controller和manifest中至少公开：

```text
bend_angle
curvature_profile
kappa_start / kappa_end
R_min / R_max（仅在该profile适用时）
euler_length / circular_length / total_length
n_curve_sections
input_straight_length / output_straight_length
wg_width / si_thickness / layer_stack
chord_sag_tolerance
```

- 使用 `topology_version` 区分纯Euler、部分Euler、Euler+圆弧和自定义profile；不同拓扑不复用旧结果缓存。
- 参数名采用物理语义。若profile没有有限 `R_max` 或没有圆弧段，不创建虚假的对应变量。
- 优化范围必须保证曲率、内侧偏置曲线、端点和制造约束合法；不要用clamp隐藏非法候选。
- 输入/输出直波导与弯曲中心线位置和切线连续，port/source位于均匀直段。

## 欧拉曲率与几何生成

Euler/clothoid段的核心定义是曲率随弧长线性变化：

```text
kappa(s) = kappa_0 + a*s
dtheta/ds = kappa(s)
dx/ds = cos(theta(s))
dy/ds = sin(theta(s))
```

总转角必须满足：

```text
integral(kappa(s), ds) = bend_angle
```

对分段Euler、Euler+圆弧或自定义profile，分别积分每段并验证总和，不因结构看似弯到目标方向就跳过角度审计。若使用对称profile，检查曲率和span关于指定对称点一致；非对称设计不得被强制镜像。

几何生成流程：

1. 依据用户确认的 `kappa(s)` 自适应采样中心线；在曲率变化快处增加点数。
2. 对中心线积分得到位置和切线，验证起止端点、总转角和直段连接。
3. 沿单位法向偏置 `±wg_width/2` 生成两侧边界；检查内侧半径、偏置曲线自交和尖角。
4. 形成闭合Si polygon或structure group子对象，设置正确z范围、材料和mesh order。
5. 用正的亚纳米弦高容差控制曲线离散；记录实际最大弦高和顶点数，而不是固定低顶点数。
6. 临时改变角度、曲率或宽度后重新setup，确认几何可重建，再恢复基线。

允许用数值积分或Fresnel积分实现中心线，但必须把定义、积分精度和坐标变换写入audit。GDS复现时按DBU和原始polygon精度设置拟合容差。

## EME cell groups与模式映射

EME纵向分段必须从当前曲率profile动态生成，不固定cell group数量：

- 输入和输出直波导各自使用至少一个适当cell group。
- 弯曲段按曲率变化、几何误差和收敛要求划分；每组可使用一个或多个纵向cells。
- 选择代表曲率和group span，使离散角度满足 `sum(kappa_j*Delta_s_j)` 与目标角度在容差内一致；端点权重取决于当前积分方案，不盲用某次工程的首尾半span规则。
- 设置group spans后重新读取EME region bounds，因为总长度可能改变region center。
- 打开custom eigensolver settings，并读回每个关键group的实际radius/curvature、span、cells和basis modes。

模式映射规则：

- 端口先搜索足够的trial modes，再按偏振比例、`real(neff)`、confinement和场型识别用户要求的模式集合。
- 不固定预设的TE阶数或模式集合，也不永久依赖raw mode序号。若目标模式不足，停止该参数点，不能用其他偏振补位。
- EME port定义模式边界，不是FDTD光源；保留端口mode index、物理名称、`neff`、偏振比例和confinement审计。
- cell basis mode数量独立于端口输出模式数量；两者都要做收敛或明确固定口径。

## 基线、优化与独立复验

1. 保存干净Layout `.lms`/`.fsp`，审计几何、端口、cell groups、模式、mesh和波长。
2. 获得授权后运行中心波长基线；EME先完成cell eigenmode solve，再propagate并提取原生S矩阵。
3. 检查目标模式透射、串扰、反射、能量闭合、passivity和reciprocity，确认S元素映射正确。
4. 使用用户确认的变量与范围执行显式扫描或原生Optimization；不要默认只扫 `R_min/R_max`。
5. 每个候选保存参数、几何审计、模式映射、FOM和状态；模式识别或求解器异常必须停止，不能作为低FOM继续。
6. 最佳值位于范围边界时标记 `boundary-best`，不自动扩大范围。
7. 从干净Layout应用最佳参数，独立重跑并比较FOM/S矩阵；通过后再进入高精度或宽带验证。

FOM优先在明确的线性功率域定义，可组合目标模式透射、串扰、反射、footprint和制造惩罚；公式、权重、模式方向和归一化写入manifest。

## 收敛与高保真验证

分别验证并分别标注：

1. 横截面mesh或maximum step。
2. 每个EME cell的basis mode数量。
3. 曲率纵向section/cell数量。
4. 端口trial/输出模式映射稳定性。
5. 宽带模式基组或独立波长重算。
6. EME/varFDTD与3D FDTD高保真交叉验证。

项目计划应为目标模式透射、关键串扰、总反射/透射、passivity和reciprocity定义数值阈值。只收敛其中一类时，例如仅横截面mesh，应写“固定basis和纵向离散下的mesh收敛”，不得简称完整收敛。

3D FDTD验证点使用独立工程，重新审计边界、source/mode expansion、mesh和传播方向；正式GPU运行前在精确pre-run FSP做system check并保留GPU证据。

## 3D FDTD弯曲波导的贴边mesh与内存预检

### 几何与mesh覆盖

- 从PDK/GDS建模时，先用原生PDK参数生成目标弯曲，再独立重读GDS的DBU、层/数据类型、Si轮廓、连通性、端点和bbox。只有横向Si版图时，Si厚度、BOX、top cladding和材料仍须从项目工艺约定或用户输入确定；GUI的 `alpha` 仅改变显示透明度。
- 用户要求mesh“跟着弯曲波导带一层buffer”时，buffer从**Si实际外边缘**量起，不从中心线或整个器件bbox量起。可将Si polygon组成 `pya.Region`，按 `round(buffer/dbu)` 做区域外扩；沿选定坐标轴（例如x轴）用窄切片覆盖外扩区域，并将各切片内的局部bbox转换为Lumerical矩形mesh override。`z` 范围覆盖Si上下表面并各加同一指定buffer。切片间要相接或重叠；记录mesh区域数量、外扩Si面积、mesh并集面积及目标区域之外的多余覆盖面积，并要求 `外扩Si区域 - mesh并集` 的面积为零。切片宽度是近似精度/区域数量的选择，不是物理buffer。
- 输入和输出均匀直段的mesh延伸至各自port平面，并按计划的纵向裕量跨过port；横向从access波导Si边缘外扩buffer，垂向与弯曲段一致。几何审计要证明两端access mesh与弯曲mesh相交、没有断带，且port截面附近的波导及所需包层都在局部mesh内。端口仍应放在均匀直段，并单独审计其模式窗口、方向和source/结果定义。
- FDTD `mesh accuracy` 与局部mesh的 `maximum mesh step` 是不同参数；建立每个override时显式启用x/y/z覆盖并设置、回读 `dx/dy/dz`。保存后独立重开精确候选FSP，检查实际区域、步长、材料、port和monitor；不能只凭规划脚本或GUI截图认定覆盖有效。

### 监视器与内存边界

- 若只需端口透射光谱，完整XY电场DFT monitor属于可取消的高内存诊断输出；保留必要的原生port结果。稀疏采样的index截面可单独用于材料审计，不能把index monitor称为XY电场监视器，也不能将两者的内存代价混为一谈。删改monitor后保存新的Layout/pre-run，并重新估算内存。
- 对每组 `R_min`、buffer、`dx/dy/dz` 和monitor配置保存独立的精确候选FSP及SHA256，独立重开后运行 `runsystemcheck("FDTD","GPU")` 读取GPU最大估计，并用 `runsystemcheck("FDTD","CPU")` 读取主机初始化/划网格及运行阶段估计；后者是GPU求解前的**主机内存预检**，不意味着改用CPU求解。记录检查时的空闲主机RAM、空闲GPU显存、各阶段估计值、余量和检查器警告；主机门禁使用相关阶段的较高估计。采用项目预先确定的安全裕量，例如主机和GPU估计均低于各自当时可用内存的90%；裕量随机器负载和风险要求调整，不将90%当成物理定律。
- 主机RAM与GPU显存任一门禁失败、估计警告显著或余量极小，都不要把候选标为可稳妥运行；不自动改粗mesh、缩buffer或切CPU。通过预检只说明该离散候选在该时刻**估计**满足门禁，不能保证实际峰值、求解成功或mesh收敛。尤其靠近主机RAM上限时，conformal mesh的CPU估计可能偏差较大。
- 问“mesh能划到多小”时，按固定buffer和其余配置扫描有界的离散候选，分别列出最细的已测通过/失败值及安全余量。若只做Layout和system check，标记 `solver_calls=[]`；不能把离散扫描边界写成连续意义上的最小可行步长。改变buffer后必须重新建模、重开、预检，旧内存结果不沿用。

### 执行与半径对比

- 得到明确运行授权后，先锁定不可变pre-run及其SHA256，从独立working副本在可见 `hide=false` 会话运行指定CPU/GPU资源。只有求解返回、Analysis mode与solver status正确、外部H5/端口数据可读，并且从最终交付位置独立重开成功，才称该点完成。保留p0日志、资源证据、原生port复数S/功率、波长数组和文件哈希。
- 同一组半径比较应固定工艺、宽度、波段/采样、端口模式、边界、monitor、buffer及局部mesh步长等数值口径；几何包络会随半径自然变化。若内存限制迫使某半径使用不同buffer，图例、逐点CSV和manifest都要标出每点的 `R_min + buffer + dx/dy/dz`，并说明该图是**不同数值配置的结果并列**，不能将差值全归因于半径。单档mesh或仅通过内存门禁不构成收敛。
- 透射功率先按已核对的port方向/归一化从原生S计算，例如目标模式 `eta=|S_out,in|^2`；反射单独提取。保存逐波长线性效率和 `10*log10(eta)` 负dB双图、同色同采样CSV，并按下文规则保留零值与无效值。

## 宽带、S矩阵与图表

两端口各保留 `N` 个模式时，保存完整 `2N×2N` 复数S矩阵和 `|S|^2` 功率矩阵；`N`由任务定义，不硬编码。一次有效的EME propagate已经包含正反向系数，不为互易元素重复求解。

宽带可选择：

- 中心波长模式基组加group-delay修正的快速EME wavelength sweep。
- 多个离散波长独立完整mode solve。
- 每个波长完整重算，用于最终高精度结论。

必须在报告中说明采用哪种口径。快速sweep不等于每个波长重新求解全部cell modes；至少用中心和波段边缘独立重算检查误差，具体点数由计划决定。

输出至少包括：

- 波长数组、完整复数S矩阵、功率矩阵和mode mapping。
- 目标模式透射/插损、主要模式转换、反射、能量闭合、passivity和reciprocity。
- 中心波长与独立单点一致性、峰值/最差值及窗口边界状态。
- 两张独立光谱图：线性功率图，以及对 `eta>0` 样本直接计算的 `10*log10(eta)` 负dB图；波长、采样、曲线和颜色完全一致。禁止使用 `max(eta,1e-12)`、`epsilon` 或其他固定下限截断；`eta=0` 保留为 `-Inf`，`eta<0` 标记为无效值/`NaN`。

正损耗可作为摘要，不能替代负dB图。负dB图默认只固定纵轴上限为 `0 dB`，下限由有限正值样本自动确定。串扰dB的分母、方向、零值/无效值位置和“未使用数值截断”必须写入manifest。

## 结果归档与清理

在丢弃analysis缓存前保存：

- Layout、Optimization和最终Analysis工程。
- 完整复数S矩阵、功率矩阵、CSV/JSON/NPZ/MAT/HDF5和mode mapping。
- 几何、曲率、cell、mesh、模式、收敛、passivity、reciprocity和运行日志。
- 线性/负dB图、必要场图、manifest和文件SHA256。

只有用户明确同意丢弃结果后才调用 `switchtolayout()`。调用前确认可复算数据完整；调用后保存为明确的Layout文件，从新会话重开并验证 `layoutmode`。清理前关闭持有目标文件的会话，清理后 `list_sessions` 必须为空。

用户确认导出GDS时，从独立最终Layout工程复用 `scripts/export_layout.lsf`，使用亚纳米弦高自适应离散并审计cell、layer/datatype、DBU、bbox、最小特征、顶点数和SHA256；不修改Analysis工程。

## 验收检查表

- [ ] 已确认弯曲角度、端点/切线、曲率profile、工艺、模式、优化范围和求解器分工。
- [ ] 没有固定套用某个转角、cell数量、半径组合或模式数。
- [ ] 曲率积分总转角、中心线端点、切线连续、偏置边界、自交和最小内侧半径通过审计。
- [ ] EME groups由当前profile动态生成，实际span、curvature、cells和basis已读回。
- [ ] 端口模式按物理属性映射，未用错误偏振补位。
- [ ] mesh、basis modes、纵向sections、宽带和高保真验证分别标注。
- [ ] 如使用3D FDTD贴边mesh，外扩Si与端口access均无覆盖缺口，buffer、步长和实际区域已独立重开回读。
- [ ] GPU求解前同时记录主机RAM和GPU显存预检及余量；纯预检候选与实际Analysis结果清楚区分。
- [ ] 最佳点从干净Layout独立复验；边界最佳已标记。
- [ ] 完整复数S、功率矩阵、passivity、reciprocity和能量闭合已保存。
- [ ] 线性与负dB图定义、采样和颜色一致。
- [ ] 最终工程和外部数据可重开；清理符合授权，MCP会话为空。
