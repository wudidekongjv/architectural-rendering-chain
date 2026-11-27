# 训练数据集说明

## 概览

| 项目 | 内容 |
|---|---|
| 图片数量 | 140 张 |
| 格式 | JPG / WebP |
| 内容 | 建筑效果图（室内 / 室外 / 景观 / 概念图 / 实体模型） |
| 标签 | 每张图片对应一个同名 `.txt` 文件 |
| 标签语言 | 英文 |
| 标签格式 | kohya_ss 标准（单行、逗号分隔） |
| 用途 | SDXL 风格 LoRA 微调 |

## 目录结构

```
data/
├── 01-_line_.jpg
├── 01-_line_.txt          # 对应英文标签
├── 2026_0113_0157.jpg
├── 2026_0113_0157.txt
├── COLINA_31_HIGH-4.jpg
├── COLINA_31_HIGH-4.txt
└── ... (共 140 组)
```

## 标签维度（14–21 个）

每个标签覆盖以下视觉维度，确保模型能学到完整的风格特征：

1. **image type** — 图像类型（photograph / rendering / line drawing / concept board / study model）
2. **building type** — 建筑类型（villa / apartment / museum / terminal / residence）
3. **architectural style** — 风格（minimalist / contemporary / Scandinavian / brutalist / Japanese）
4. **view / perspective** — 视角（eye-level / aerial / low-angle / wide-angle / interior）
5. **materials** — 材质（exposed concrete / cross-laminated timber / white stucco / teal shutters）
6. **lighting** — 光照（soft diffused daylight / dramatic direct sun / overcast）
7. **time of day / weather** — 时段天气（sunny midday / golden hour / dusk）
8. **environment / setting** — 环境（coastal pine forest / urban / courtyard / landscape）
9. **color palette** — 配色（warm beige and honey wood / white and teal）
10. **key features** — 关键特征（infinity pool / pergola / paper lantern / atrium）
11. **composition** — 构图（symmetrical / diagonal leading lines / layered）
12. **mood / atmosphere** — 氛围（calm serene / dramatic contemplative / relaxed vacation）
13. **photography style** — 摄影风格（architectural photography）
14. **quality marker** — 质量标记（professional rendering）

## 标签示例

`2026_0113_0157.txt`:
```
architectural interior rendering, modern wooden loft apartment, Scandinavian minimalist style with Japanese influences, eye-level interior view from staircase, exposed timber beams and plywood wall panels, warm natural daylight from floor-to-ceiling glazing, bright sunny midday, open mezzanine with indoor plants, warm beige and honey wood tones, large white paper lantern pendant, curved stainless steel handrail, diagonal composition leading to bedroom, calm serene atmosphere, architectural photography, professional rendering
```

## 图片内容分布

数据集涵盖多类建筑图像：
- 现代极简住宅 / 别墅（灰砖、红砖、白墙木构）
- 室内空间（木构 loft、采光井、中庭）
- 公共建筑（博物馆、交通枢纽、学习中心）
- 景观与度假建筑（泳池、松林、庭院）
- 建筑模型与设计分析板（概念图、实体模型）

> 注：标注时对非渲染图（概念板、实体模型、线稿感照片）均如实描述其真实类型，未强行归类为渲染图，以保证标签忠实度。

## 数据生成方式

所有标签均通过逐张视觉识别生成（ViewImage），非根据文件名推测。文件名中的下划线占位符（如 `02-________.jpg`）不携带语义，标签内容完全来自图像本身。

## 与训练脚本的配合

`scripts/train_lora.sh` 会读取 `data/` 目录，自动统计图片与标签数量，并以 kohya_ss 标准格式训练：

```bash
--train_data_dir=./data
--resolution=1024
--network_dim=32
--network_alpha=16
```
