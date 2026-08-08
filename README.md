# ComfyUI-Tlant-Toolkit

Small utility nodes for ComfyUI workflows.

## Nodes

- `Load File Batch (Tlant)`: selects one file from a folder by fixed index, incremental counter, or seed-stable random choice, and outputs the absolute path plus filename metadata.
- `MiniMax H3提示词扩写指令·简单模式（Tlant）`: 使用少量常用中文选项生成完整、无状态的 MiniMax H3 I2VA 扩写指令。
- `MiniMax H3高级配置·基础生成（Tlant）`: 配置时长、画幅、主题和创意策略。
- `MiniMax H3高级配置·人物一致性（Tlant）`: 配置身份、人脸、视线和表情稳定性。
- `MiniMax H3高级配置·人物动作（Tlant）`: 配置姿势、手脚、移动和舞蹈动作。
- `MiniMax H3高级配置·镜头剪辑（Tlant）`: 配置分镜、切镜、运镜和焦点变化。
- `MiniMax H3高级配置·场景效果（Tlant）`: 配置背景、光线、物理动态和视觉效果。
- `MiniMax H3高级配置·音频（Tlant）`: 配置 MiniMax H3 原生环境声、动作音、音乐和对白。
- `MiniMax H3提示词扩写指令·高级汇总（Tlant）`: 汇总高级配置；未连接的分类使用 seed 生成可复现随机值。

## MiniMax H3 提示词扩写

这些节点用于将写实静态人物图或上游反推的图片描述，转换成发送给远程 LLM 的完整无状态扩写指令。远程 LLM 的输出被约束为干净的英文 MiniMax H3 I2VA 提示词，可直接连接到本地 MiniMax H3 工作流。

### 简单模式

使用 `MiniMax H3提示词扩写指令·简单模式（Tlant）`：设置时长、画幅、主题、动作幅度、人脸保护、切镜、镜头动感、音频、音乐与 seed 即可。未展示的高级参数会由节点按 seed 稳定随机抽取。

### 高级模式

将需要的 `MiniMax H3高级配置` 节点连接到 `MiniMax H3提示词扩写指令·高级汇总（Tlant）`。任何未连接的分类都会按汇总节点的 seed 抽取随机值，因此可以只精确控制一部分配置。

### 图像与文本输入

两个模式均可接收 `IMAGE` 和 `STRING` 类型的图像描述。连接 `IMAGE` 时会原样透传给后续视觉 LLM，并在指令中明确要求以实际图像为最高依据；`STRING` 仅作为辅助信息。未连接图像时，必须提供图像描述。

### 可复现随机

所有“随机”选项通过 `seed + 字段名` 独立采样。将 ComfyUI 的 seed 控制设为 `fixed` 后，相同输入和 seed 会得到相同的选项组合；改变一个字段不会扰乱其他字段的随机结果。
