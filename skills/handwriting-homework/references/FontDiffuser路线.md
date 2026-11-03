# 路线 C：FontDiffuser（本机未验证，谨慎承诺）

> ⚠️ **诚实声明**：本技能的作者**没有在 macOS Apple Silicon 上跑通过这条路线**。
> 下面是依据官方 README（2024 版）整理的步骤，链接与参数都来自官方文档，
> 但环境是否能在 M 系列芯片上装起来、跑得动，**需要实机验证**。
> 在用户面前不要承诺"能生成一整套和你一模一样的字库"。

官方推荐环境是 **Linux + CUDA 11.7 + Python 3.9 + PyTorch 1.13.1**，这是最大的风险点：
`torch==1.13.1+cu117` 在 Apple Silicon 上装不了，官方也没有 MPS 支持声明。

---

## 1. 它是什么

- 论文：FontDiffuser，AAAI 2024，华南理工 DLVC-Lab
- 仓库：https://github.com/yeungchenwa/FontDiffuser
- 论文页：https://arxiv.org/abs/2312.12142
- 在线 Demo：https://huggingface.co/spaces/yeungchenwa/FontDiffuser-Gradio
- **许可证：仅限非商业研究用途**（商用需联系作者）

一句话：one-shot 字体生成，用「标准字体的字形」当内容源、「用户的少量手写」当风格参考，
生成没写过的字。

---

## 2. 环境搭建（官方步骤）

```bash
git clone https://github.com/yeungchenwa/FontDiffuser.git
conda create -n fontdiffuser python=3.9 -y
conda activate fontdiffuser
# 官方建议（CUDA）：Apple Silicon 上要换成对应平台的 torch
pip install torch==1.13.1+cu117 torchvision==0.14.1+cu117 torchaudio==0.13.1 \
    --extra-index-url https://download.pytorch.org/whl/cu117
pip install -r requirements.txt
```

`requirements.txt` 锁定得比较死，别随手升级：

```
transformers==4.33.1
accelerate==0.23.0
diffusers==0.22.0
gradio==4.8.0
pyyaml / pygame / opencv-python / info-nce-pytorch / kornia
```

**Apple Silicon 上的现实预期**：`diffusers==0.22.0` 与新版本 torch 可能不兼容；
可行的思路是装 CPU 版 torch 跑（很慢），或者找一台带 N 卡的机器。
如果只是想验证效果，先用上面那个 Hugging Face Demo 在线试，别急着搭环境。

---

## 3. 权重（需要人工下载）

Model Zoo 里两个 checkpoint（FontDiffuser 和 SCR）：

- Google Drive：https://drive.google.com/drive/folders/12hfuZ9MQvXqcteNuz7JQ2B_mUcTr-5jZ
- 百度云：https://pan.baidu.com/s/19t1B7le8x8L2yFGaOvyyBQ （提取码 gexg）

下载后把 `ckpt` 放到仓库根目录，里面必须有三个文件：
`unet.pth`、`content_encoder.pth`、`style_encoder.pth`。

> 没有自动下载脚本，必须人工下载并登录网盘/GDrive。

---

## 4. 数据目录（官方结构）

````
data_examples/
└── train/
    ├── ContentImage/                 # 目标字在标准字体里的图（内容源）
    │   ├── char0.png
    │   └── ...
    └── TargetImage/                  # 按风格分子目录（style0 = 用户笔迹）
        ├── style0/
        │   ├── style0+char0.png      # 用户手写的 char0
        │   └── ...
        └── style1/
            └── ...
````

要点：
- `ContentImage` 用**楷体/思源**渲染目标字（我们工具链里 `handlib.content_font()` 用的就是楷体）；
- `TargetImage/<风格名>/` 就是用户的采样纸切出来的字，文件名格式 `风格名+字文件名`；
- 图片分辨率：`content_image_size` 与 `resolution` 必须一致，`style_image_size` 可以不同。

---

## 5. 训练（微调）

```bash
accelerate config          # 先配一次并行/混合精度
sh train_phase_1.sh        # 阶段一
sh train_phase_2.sh        # 阶段二（需要 SCR 权重，并把阶段一的 ckpt 放到 phase_1_ckpt/）
```

主要可调项（官方 README 列出的）：

`data_root` / `output_dir` / `resolution` / `style_image_size` /
`content_image_size` / `channel_attn` / `train_batch_size` /
`max_train_steps` / `learning_rate` / `ckpt_interval` / `drop_prob`

**样本很少时防过拟合**（这是官方没写、但必然要调的）：
- 学习率降到官方默认的 1/5 ~ 1/10；
- `max_train_steps` 宁可少，配合 `ckpt_interval` 频繁存点，用生成效果挑 checkpoint；
- 阶段二只用必要步数，`num_neg` 太大在小样本上反而不稳。

---

## 6. 生成

**(1) 用内容图 + 风格图**

```bash
sh script/sample_content_image.sh
```

参数：`ckpt_dir`、`content_image_path`、`style_image_path`、`save_image`、
`save_image_dir`、`device`、`guidance_scale`、`num_inference_steps`（DPM-Solver++）。
输出 `out_single.png` 与 `out_with_cs.png`。

**(2) 直接给字符**

```bash
sh script/sample_content_character.sh
```

用 `character_input=True` + `content_character="明"`。
官方提示：需要一个**含大量汉字的 ttf** 来渲染内容源（README 里给了一个百度云链接）。

**(3) WebUI**

```bash
gradio gradio_app.py
```

---

## 7. 生成完怎么接回本工具链

FontDiffuser 出来的是**位图**，正好接上我们的打包管线：

```bash
# 把生成的字图（一个文件一个字，文件名就是那个字）放进一个目录，例如 fd_out/
python3 import_glyphs.py --from-dir fd_out --out <作业目录>/data --source fontdiffuser
python3 build_font.py --data <作业目录>/data --out <作业目录>/myhandwriting.ttf --verify 30
```

`import_glyphs.py` 会做：二值化 → 去噪 → 紧致裁剪 → 归一到 512 → 写进
`data/glyphs_mask/` 与 `data/manifest.json`（`flags=["imported"]`）。

**来源会被如实标注**：这些字不是用户真迹，渲染报告里会算进「非真迹」那一类。

---

## 8. 替代方案

如果 FontDiffuser 环境搭不起来，按以下顺序退：

1. **zi2zi-pytorch**：经典 GAN 路线，原理类似，样本需求更多、训练更久；
2. **本工具的部件拼接**（`compose.py`）：完全离线、不用 GPU，用用户写过的部件拼新字——
   这是目前**唯一在本机验证过**的"生成新字"手段；
3. **让用户补写**：最土但最真，简答题场景通常只需要补十几个字。
