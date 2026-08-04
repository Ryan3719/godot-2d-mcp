# Godot 2D MCP 初始化规划

状态：阶段 0 已完成；阶段 1 已交付首批场景写入、结构编辑、信号管理、动画编辑、UI 布局/样式与嵌入式 Theme 资源能力；阶段 3 已开始交付 Shape2D 与碰撞层能力（v0.8.0）
目标引擎：Godot 4.7+  
参考实现：[`hi-godot/godot-ai`](https://github.com/hi-godot/godot-ai)

## 1. 项目目标

Godot 2D MCP 是一个面向 Codex、Claude Code 等 MCP 客户端的 Godot 编辑器插件与 MCP Server。它让 Agent 能通过结构化工具读取和编辑正在运行的 Godot 编辑器，而不是直接猜测或拼接 `.tscn` 文件。

最终目标是覆盖 Godot 4.7 的公开 2D 编辑能力，并通过运行时能力发现兼容后续 Godot 版本。初版只交付部分能力，但协议、类型系统和模块边界必须允许后续扩展到完整 2D 工作流。

不修改 Godot 引擎源码。仓库内的 Godot 源码副本只作为 API 调研依据，不属于本项目发布内容。

## 2. 已确认决策

- 独立精简实现，不直接 fork `godot-ai`。
- 最低支持 Godot 4.7，当前 Godot 4.8-dev 用于前向兼容验证。
- 采用 Python 3.11+、FastMCP、Pydantic、WebSocket 和 `uv`。
- MCP Server 与 Godot EditorPlugin 分离。
- 支持 Streamable HTTP，同时提供适用于 Codex、Claude Desktop 的 `stdio attach`。
- 初版优先完成场景和节点编辑闭环，后续扩展到全部 2D 领域。
- 可选择性复用 `godot-ai` 的 MIT 代码；任何复用必须保留原许可证和版权声明。

## 3. 架构

```text
Codex / Claude Code / MCP Client
              |
       MCP (HTTP / stdio)
              |
       Python MCP Server
       - MCP transport
       - schema validation
       - session routing
       - error normalization
              |
       WebSocket RPC (loopback)
              |
       Godot EditorPlugin
       - main-thread queue
       - editor readiness
       - scene/node handlers
       - undo/redo
              |
       Godot Editor public APIs
```

### Python Server 职责

- 实现 MCP 生命周期、工具和资源。
- 校验输入参数并生成稳定的 JSON Schema。
- 管理多个 Godot 编辑器会话，并防止请求路由到错误项目。
- 将 Godot 错误映射为结构化 MCP 错误。
- 管理重连、超时、请求关联和长任务。
- 不直接修改 Godot 场景或资源。

### Godot 插件职责

- 通过 `EditorInterface`、`EditorUndoRedoManager`、`ClassDB`、`ResourceLoader` 操作编辑器。
- 在 `_process()` 中按帧预算处理命令，禁止在网络回调中修改场景树。
- 报告项目、Godot 版本、当前场景、导入状态和运行状态。
- 对所有编辑操作执行主线程检查、可写状态检查和撤销重做注册。
- 不实现 MCP 传输协议。

## 4. 完整 2D 支持定义

一个 2D 节点或资源只有满足以下条件才算完整支持：

1. 能查询类型、继承关系、属性、枚举、方法和信号。
2. 能创建、删除、复制、重命名、移动和重新挂载节点。
3. 能读写全部公开且可序列化的属性。
4. 能创建、加载、绑定和保存依赖资源。
5. 能连接和断开信号。
6. 能正确保存 `.tscn`、`.tres`，不破坏节点所有权或场景实例关系。
7. 编辑器写操作能撤销和重做。
8. 复杂领域具有语义化工具和端到端测试，而不只是通用属性入口。

### 最终覆盖领域

- 场景、节点、PackedScene 实例和自定义脚本节点。
- `Node2D`、`CanvasItem` 及全部公开 2D 派生节点。
- 全部 `Control`、Container、Button、Theme、StyleBox 和字体工作流。
- AnimationPlayer、AnimationLibrary、属性/方法轨道和 Tween 工作流。
- 2D 物理、碰撞形状、Area、Body、Joint、RayCast 和 ShapeCast。
- TileMapLayer、TileSet、Atlas、terrain、custom data、碰撞和导航层。
- NavigationRegion2D、NavigationAgent2D、NavigationObstacle2D 和 NavigationLink2D。
- Camera2D、SubViewport、CanvasLayer、Parallax2D。
- 2D 光照、遮挡、粒子、CanvasItemMaterial 和 2D Shader。
- Path2D、Curve2D、Skeleton2D 和 Bone2D。
- AudioStreamPlayer2D、输入映射、触摸、鼠标、键盘和 GUI 焦点。
- 运行、停止、日志、截图、输入模拟和视觉验证。

## 5. 初版工具面

初版控制工具数量，优先保证 Agent 调用准确率。

| 工具 | 作用 |
| --- | --- |
| `session_list` | 列出连接的 Godot 编辑器实例 |
| `session_activate` | 显式选择目标编辑器会话 |
| `editor_get_state` | 获取项目、场景、导入和运行状态 |
| `class_search` | 查询允许创建的 2D 类型及能力 |
| `scene_get_hierarchy` | 分页读取当前场景树 |
| `node_get_properties` | 获取节点属性、脚本、分组和信号 |
| `node_create` | 创建内置节点、自定义脚本节点或 PackedScene 实例 |
| `node_update` | 批量修改属性、名称、父节点和顺序 |
| `node_duplicate` | 复制节点或子树 |
| `node_delete` | 删除非场景根节点 |
| `scene_create` | 创建 2D 或 UI 场景 |
| `scene_open` | 在编辑器中打开场景 |
| `scene_save` | 显式保存当前场景 |
| `scene_apply_patch` | 原子执行一组预校验的场景操作 |
| `signal_manage` | 查询、连接和断开信号 |
| `resource_manage` | 创建、加载、修改和保存 2D 资源 |

通用反射层应让所有合法 2D 节点从初版起具备基础创建和属性编辑能力。后续阶段增加复杂领域的专用工具，而不是重新设计底层协议。

### 当前已交付

- 会话选择、编辑器状态、2D 类型检索、场景树和节点属性读取。
- 内置 `ClassDB` 2D/UI 节点创建、原子属性修改、删除、撤销/重做和显式保存。
- `node_rename`、`node_duplicate`、`node_reparent` 和 `node_move`。
- `node_get_signals`、`signal_connect` 和 `signal_disconnect`，支持连接已有节点方法、绑定 JSON 参数、deferred 与 one-shot 选项。
- `animation_list`、`animation_get`、`animation_create`、`animation_delete`、属性轨道 upsert/delete 和关键帧 upsert/delete；支持场景内嵌动画库、撤销/重做与保存。
- `control_get_layout`、`control_set_layout`、`control_set_layout_preset`，支持精确 anchors/offsets 与 Godot 布局预设；Container 子节点会明确拒绝。
- `control_get_styleboxes`、`control_stylebox_flat_upsert`、`control_stylebox_override_clear`，支持节点本地 `StyleBoxFlat` 状态覆盖及撤销/重做。
- `control_theme_get`、`control_theme_create`、`control_theme_assign`，支持读取、创建、绑定、解除和撤销 Control 的 Theme 资源分配。
- `control_theme_defaults_set`、`control_theme_defaults_clear`，支持嵌入式 Theme 默认字体、字体大小与基础缩放。
- `control_theme_item_upsert`、`control_theme_item_clear`，支持嵌入式 Theme 的颜色、常量、字体大小、字体、图标和 `StyleBoxFlat` 条目。
- `collision_shape_get`、`collision_shape_set`、`collision_shape_clear`，支持 `CircleShape2D`、`RectangleShape2D`、`CapsuleShape2D`、`SegmentShape2D`、`SeparationRayShape2D`、`WorldBoundaryShape2D`、`ConvexPolygonShape2D` 与 `ConcavePolygonShape2D` 的场景内嵌资源编辑。
- `collision_object_get_layers`、`collision_object_set_layers`，支持 `CollisionObject2D` 的碰撞 layer/mask 位与 1-32 层编号之间的可读转换。
- 重命名和重新挂载时迁移场景内直接 `NodePath` 属性及内嵌 `AnimationPlayer` 动画轨道。
- 重新挂载默认保持 `Node2D`/`Control` 的全局视觉位置，并允许调用方关闭该行为。

当前结构编辑拒绝跨 PackedScene 边界、包含不受支持 3D 节点的子树，以及需要修改外部动画资源的操作；删除会预检直接 `NodePath` 和动画轨道，避免留下悬空引用。动画工具仅写入场景内嵌 `AnimationLibrary`/`Animation`，并且只创建或修改本地 2D/UI 节点的属性值轨道；外部资源、导入轨道和方法/音频/嵌套动画轨道仍属于后续阶段。布局工具拒绝由 `Container` 管理的子节点；样式工具只创建独立的节点本地 `StyleBoxFlat` override，不会修改共享 Theme 或外部资源。Theme 工具可绑定外部 `res://` Theme，但它们在 MCP 内只读；可写范围限于场景内嵌 Theme，因此全部 Theme 变更都能随场景撤销和重做。字体可绑定项目 `Font` 或新建内嵌 `SystemFont`，图标仅绑定项目中已有的 `Texture2D`。碰撞形状工具创建或复制独立内嵌的 `Shape2D` 后替换节点分配，不修改共享或外部 Shape2D；碰撞层工具只改动本地 `CollisionObject2D` 的 layer/mask。Area、Body、Joint 的进一步语义化配置，以及导航、TileMap，仍在后续阶段。信号工具仅操作场景内本地节点的持久化连接，并要求目标方法已存在，不会生成或修改脚本回调。这是为了避免 Agent 在无法证明安全的情况下静默破坏引用。自动脚本回调生成和完整 PackedScene 工作流仍属于后续阶段。

## 6. 核心数据约定

### 节点引用

节点引用使用稳定的结构化标识：

```json
{
  "session_id": "project-name@a1b2",
  "scene_file": "res://scenes/main.tscn",
  "node_path": "/Main/Player",
  "scene_revision": 12
}
```

禁止将 Godot `instance_id` 作为跨请求稳定标识。

### Variant 编解码

协议必须显式支持 `Vector2`、`Vector2i`、`Rect2`、`Transform2D`、`Color`、`NodePath`、`StringName`、枚举、TypedArray、TypedDictionary 和 Resource 引用。

属性写入必须根据 Godot 属性元数据执行类型转换。转换失败必须返回错误，禁止静默写入默认值。

### 响应格式

Godot RPC 响应保持稳定外壳：

```json
{
  "request_id": "...",
  "status": "ok",
  "data": {},
  "meta": {
    "session_id": "project-name@a1b2",
    "readiness": "ready",
    "scene_revision": 12
  }
}
```

错误包含稳定错误码、可读消息、是否可重试、修复提示和结构化细节。

## 7. 编辑一致性

- 所有写操作使用 `EditorUndoRedoManager`。
- 写操作默认只标记场景未保存；只有 `scene_save` 才写盘。
- 复杂操作先预校验，再一次性提交。
- `scene_apply_patch` 支持 `expected_revision`，拒绝基于旧场景状态的写入。
- 场景根节点不能被通用删除或重新挂载。
- PackedScene 实例必须保留实例关系，不能错误重写子节点 owner。
- 插件处于导入、播放或退出等不可写状态时，写工具必须明确拒绝。

## 8. 2D 类型策略

类型策略由运行时 `ClassDB` 元数据和集中配置生成，禁止在各处理器中散落硬编码名单。

默认允许：

- `CanvasItem`、`Node2D`、`Control` 派生节点。
- 明确登记的通用支持节点，例如 `Node`、`Timer`、`AnimationPlayer` 和 `AudioStreamPlayer`。
- 名称和基类均满足 2D 策略的辅助节点。
- 继承自合法基类的项目自定义脚本。

默认拒绝：

- `Node3D` 派生节点。
- 3D 专用但不继承 `Node3D` 的节点和资源。
- `Shape3D`、Mesh 等 3D 资源。
- 任意 `Object.call()`、任意表达式执行和 Shell 执行入口。

## 9. 安全边界

- HTTP 和 WebSocket 默认只绑定 `127.0.0.1`。
- 多编辑器场景下，写操作必须显式或唯一解析目标会话。
- 文件访问限制在目标项目 `res://` 和受控 `user://` 范围。
- 限制请求体、队列长度、分页大小、执行时间和并发数。
- MCP 工具声明 `readOnlyHint`、`destructiveHint` 和幂等信息。
- 客户端配置修改必须由用户在 Godot Dock 中主动触发，并采用原子写入。
- 不收集遥测，不访问公网，不上传项目内容。

## 10. 仓库结构

```text
godot-2d-mcp/
├── plugin/addons/godot_2d_mcp/   # Godot EditorPlugin
├── server/src/godot_2d_mcp/      # Python MCP Server
├── server/tests/                  # Python 单元和协议测试
├── test_project/                  # Godot 4.7 集成测试工程
├── docs/                          # 架构、协议和覆盖矩阵
├── scripts/                       # 开发和 CI 脚本
└── .github/workflows/             # 跨平台验证
```

## 11. 实施阶段

### 阶段 0：基础设施

- 仓库、许可证、开发环境和 CI。
- FastMCP Server、WebSocket transport 和协议数据模型。
- Godot EditorPlugin、状态 Dock、连接和主线程 Dispatcher。
- 会话握手、心跳、重连、版本检查和 readiness。

### 阶段 1：场景与节点闭环

- 场景层级、节点属性和 ClassDB 查询。
- 节点创建、修改、删除、复制和重新挂载。
- Variant 编解码、撤销重做、显式保存和原子 patch。
- 内置节点、自定义脚本节点和 PackedScene 实例。

### 阶段 2：UI 与动画

- Control、Container、Theme、StyleBox、字体和图标。
- Button 状态、信号、AnimationPlayer 和 Tween。
- 布局预设、锚点、焦点和输入行为。

### 阶段 3：物理与导航

- 全部 Shape2D、Body2D、Area2D、Joint2D 和查询节点。
- 2D 导航区域、Agent、Obstacle、Link 和 NavigationPolygon。

### 阶段 4：TileMap

- TileMapLayer、TileSetAtlasSource、图块和 terrain。
- custom data、替代 tile、碰撞层和导航层。

### 阶段 5：高级 2D

- 粒子、光照、遮挡、Shader、骨骼、路径、相机和音频。

### 阶段 6：运行反馈

- 运行/停止、编辑器和游戏日志、截图、输入模拟和测试运行。

### 阶段 7：完整性审计

- 从 Godot 4.7 `ClassDB` 生成 2D 类型与资源清单。
- 为每个类型记录基础支持、语义支持和测试状态。
- 对 Godot 新版本执行能力差异检测。

## 12. 测试与验收

- Python 单元测试：Schema、协议、错误、会话路由、超时和重连。
- GDScript 单元测试：Variant、路径、类型策略、撤销重做和 handler。
- 契约测试：Python 与 Godot 请求/响应、版本和错误码一致性。
- 集成测试：真实 Godot 4.7 headless editor 与 MCP Server。
- 视觉测试：真实渲染的 2D 截图和像素检查。
- 客户端冒烟：Codex `stdio`、Codex HTTP、Claude Code HTTP。
- 平台矩阵：Linux、macOS、Windows。
- 版本矩阵：Godot 4.7-stable 为发布门槛，4.8-dev 为前向兼容检查。

阶段 1 的完成标准是 Agent 能稳定执行：连接编辑器、读取场景、创建并配置多个 2D 节点、撤销和重做、保存场景、重新加载验证结果。

## 13. 暂不实施

- 任何 3D 节点、资源、编辑器 Gizmo 或 3D 运行工作流。
- Godot 引擎源码修改或私有编辑器 API 补丁。
- 远程公网 MCP 服务和多租户部署。
- 任意代码求值、Shell 执行或项目目录外文件管理。
- 首版自更新、遥测和大规模客户端配置适配。

## 14. 参考资料

- [Godot Engine](https://github.com/godotengine/godot)
- [Godot AI](https://github.com/hi-godot/godot-ai)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp)
