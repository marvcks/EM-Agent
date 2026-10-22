---
name: cnt2d
description: CNT/PVDF 二维复合材料稳态导热；生成随机结构或导入 CNT 角点，计算 X 方向有效热导率、温度与热流。通过共用科学任务队列提交和监控。
---

# CNT 二维导热

用于二维正方形 RVE 内矩形 CNT 芯体、有限厚度界面层和基体的标量稳态导热。
左右恒温、上下绝热；二阶有限元。无需 MATLAB/COMSOL，不支持三维、瞬态、
周期边界、各向异性或额外接触热阻。用现有终端运行以下 CLI，不另起后台进程。

```sh
em-cnt2d submit --seed 20260901 --cores 2 --memory-mb 4096
em-cnt2d status JOB_ID
em-cnt2d cancel JOB_ID
em-cnt2d download JOB_ID ./cnt-results
```

默认：边长100、CNT外长10外宽1、界面厚0.1、单位mm、面积分数0.01（10根），
取向−90到90度；CNT/界面/基体热导率400/7.642/0.146 W/(m·K)，左右308/288 K。
创建 JSON 文件覆盖需要修改的参数，然后：

```sh
em-cnt2d submit --parameters parameters.json --corners Corners.txt --memory-mb 4096
```

允许的 JSON 键：box_size, cnt_length, cnt_width, surface_width,
filler_area_fraction_target, angle_min, angle_max, length_unit (m/cm/mm/um/nm),
cnt_k, surface_k, pvdf_k, t_left, t_right, bulk_size, interface_layers。
不传角点则按种子生成；角点使用所选长度单位，制表符表头
`CNT_ID x1 y1 x2 y2 x3 y3 x4 y4`，每行一根外矩形，四角逆时针。
导入时直接复用结构，不能假定 MATLAB 和 Python 相同种子产生同一结构。

最多64根、50万三角形；面积分数0–0.1。bulk_size为边长1–25%；
surface_width/interface_layers 不小于边长0.025%，interface_layers为1–3。
申请内存低于4096 MB时最多20万三角形。输入必须是框内互不接触的矩形。
长度与网格尺寸用所选单位，温度K，热导率W/(m·K)。

两入口共用串行队列（最多10项、8核/8192MB），CLI 标记 Agent 来源，无平台总时长上限。
主动查询日志和状态；无进展或需要中止时 cancel，不把停止后遗留文件当成功。
手动页面任务限15分钟。内存申请不等于OS硬隔离。

成功后 result.json 的 verified=true 才展示 metrics.Keff_X，单位W/(m·K)。
results.zip包含实际参数、角点、温度/热流/网格PNG、网格MSH、VTU和完整P2解NPZ。
Energy_Balance_Error为弱形式反力守恒比例，不是网格收敛证明；另有直接梯度热流诊断。
SOLVED只表示本次求解成功。已对照一个5%/50根CNT的COMSOL算例，其他工况仍需网格收敛检查。
