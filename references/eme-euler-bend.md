# 参数化欧拉弯曲设计、仿真与交付规范

## 目录

1. [适用范围与任务确认](#适用范围与任务确认)
2. [求解器分工](#求解器分工)
3. [通用参数化接口](#通用参数化接口)
4. [欧拉曲率与几何生成](#欧拉曲率与几何生成)
5. [EME cell groups与模式映射](#eme-cell-groups与模式映射)
6. [基线、优化与独立复验](#基线优化与独立复验)
7. [收敛与高保真验证](#收敛与高保真验证)
8. [宽带、S矩阵与图表](#宽带s矩阵与图表)
9. [结果归档与清理](#结果归档与清理)
10. [验收检查表](#验收检查表)

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
- 两张独立光谱图：线性功率图，以及 `10*log10(max(eta,epsilon))` 的负dB图；波长、采样、曲线和颜色完全一致。

正损耗可作为摘要，不能替代负dB图。串扰dB的分母、方向和零值floor必须写入manifest。

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
- [ ] 最佳点从干净Layout独立复验；边界最佳已标记。
- [ ] 完整复数S、功率矩阵、passivity、reciprocity和能量闭合已保存。
- [ ] 线性与负dB图定义、采样和颜色一致。
- [ ] 最终工程和外部数据可重开；清理符合授权，MCP会话为空。
