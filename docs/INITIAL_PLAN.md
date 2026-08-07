# Godot 2D MCP 初始化规划

状态：阶段 0 至阶段 7 已完成。阶段 1 至阶段 5 已交付完整 2D/UI 场景、动画、物理、导航、TileMap、视觉、粒子与控件语义能力；阶段 6 已交付场景启动/停止、游戏日志、真实运行时截图、键盘/鼠标/多点触摸输入模拟、项目 Input Map 动作与键盘/鼠标/手柄绑定编辑、`AudioStreamPlayer2D` 运行时状态/播放/停止/定位控制、受限性能采样、客户端 PNG 内容断言和有总超时/自动清理边界的游戏测试编排；阶段 7 已交付运行时 `ClassDB` 2D 覆盖审计、完整快照、跨版本差异、类型详情反射和全允许节点生命周期验收（v0.53.0）
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
| `input_map_get` | 分页读取项目 Input Map 动作与持久化绑定 |
| `input_map_action_upsert` | 创建或显式完整替换一个项目输入动作 |
| `input_map_action_delete` | 显式确认后删除一个项目输入动作 |
| `input_map_undo` / `input_map_redo` | 撤销或重做紧邻的 MCP 输入映射操作 |
| `class_search` | 查询允许创建的 2D 类型及能力 |
| `class_2d_describe` | 分页读取支持类型的继承、公开属性、方法、信号和枚举 |
| `scene_get_hierarchy` | 分页读取当前场景树 |
| `node_get_properties` | 获取节点属性、脚本、分组和信号 |
| `node_create` | 创建内置节点，可附加兼容项目脚本 |
| `node_script_bind` | 向本地节点绑定兼容项目脚本 |
| `node_script_clear` | 从本地节点显式解绑脚本 |
| `node_instance_scene` | 实例化项目内完整 2D PackedScene 并保留实例边界 |
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

- 会话选择、编辑器状态、2D 类型检索、场景树和节点属性读取；`scene_create` 仅在项目内创建此前不存在的 `.tscn`，自动打开并允许后续节点编辑，`scene_open` 会先审计完整实例子树再打开现有项目 `.tscn`/`.scn`，两者均拒绝 3D 和其他策略外节点。
- `input_map_get`、`input_map_action_upsert`、`input_map_action_delete`、`input_map_undo`、`input_map_redo` 支持项目级 Input Map 的分页读取、动作创建/完整替换、显式删除和受作用域限制的全局撤销/重做。写入同步保存 `project.godot`，不依赖场景保存；键盘、鼠标按钮、手柄按钮和手柄轴绑定均采用稳定 JSON 结构，键盘支持 keycode、physical keycode、key label、unicode 与修饰键，`device: -1` 表示全部设备。为避免破坏 Godot 编辑器导航，`ui_*` 内置动作只读。
- 内置 `ClassDB` 2D/UI 节点创建、兼容项目内非 `@tool` Script 的直接创建/绑定/显式解绑、原子属性修改、删除、撤销/重做和显式保存；脚本必须具有兼容的受支持 2D/UI 原生基类，`@tool` 脚本会被拒绝以避免编辑器内代码执行。对 Godot 声明为 `Resource` 的公开属性，以及 `TypedArray`/`TypedDictionary` 中声明为 Resource 的元素，可通过严格类型检查的 `{ "resource_path": "res://..." }` 引用安全绑定项目资源，且不会修改外部资源。读取类型化容器时会返回 `container_type` 元数据；每个元素在写入前按 Godot 声明转换，非字符串键字典以 `{ "entries": [{ "key": ..., "value": ... }] }` 传输以保持键类型，场景 Node 引用和脚本约束对象明确拒绝。`node_instance_scene` 仅实例化完整受支持的 2D/UI PackedScene，保留内部 owner，支持撤销/重做与完整实例根删除，`node_duplicate`/`node_reparent` 同样可处理未添加局部 override 的完整实例根且绝不展平其内部节点。
- `node_rename`、`node_duplicate`、`node_reparent` 和 `node_move`。
- `node_get_signals`、`signal_connect` 和 `signal_disconnect`，支持连接已有节点方法、绑定 JSON 参数、deferred 与 one-shot 选项。
- `animation_list`、`animation_get`、`animation_create`、`animation_delete`、属性轨道 upsert/delete 和关键帧 upsert/delete；支持场景内嵌动画库、撤销/重做与保存。
- `control_get_layout`、`control_set_layout`、`control_set_layout_preset`，支持精确 anchors/offsets 与 Godot 布局预设；Container 子节点会明确拒绝。
- `container_2d_get`、`container_2d_set`、`container_child_layout_set`，支持 Box、Grid、Center、AspectRatio、Flow、Split、Scroll、Tab、SubViewport 容器的已核验公开布局配置，以及直接 Control 子节点的 `custom_minimum_size`、两轴尺寸标志和伸缩比例；可读尺寸标志为 `fill`、`expand`、`shrink_begin`、`shrink_center`、`shrink_end`。`tab_container_items_get`、`tab_container_item_set` 支持 TabContainer 直接 Control 子项的标题、提示、项目内图标、图标最大宽度、禁用/隐藏、JSON metadata 和关闭按钮图标；使用已有 `node_move` 重排子项。
- `control_get_styleboxes`、`control_stylebox_flat_upsert`、`control_stylebox_override_clear`，支持节点本地 `StyleBoxFlat` 状态覆盖及撤销/重做。
- `button_2d_get`、`button_2d_set`，支持所有 `BaseButton` 派生节点的 disabled/toggle/pressed/action/mask、外部 ButtonGroup/Shortcut 绑定和交互配置；`Button` 派生节点额外支持文本、图标、对齐、换行、文本方向和语言，`TextureButton` 支持五态贴图、BitMap 点击掩码、拉伸与翻转，`LinkButton` 支持 URI、下划线模式、溢出截断、截断字符、文本方向和语言。`button_menu_items_get`、`button_menu_items_set`、`button_menu_items_clear` 支持 OptionButton 的普通/分隔选择项以及 MenuButton 的普通/复选/单选/多状态/分隔项、项目内图标、元数据、文本本地化、缩进与图标呈现；平面菜单替换和清空均注册为单个撤销事务。嵌套 PopupMenu 子菜单树和单项 Shortcut 资源仍会显式拒绝或不暴露写入，避免不完整序列化。
- `control_theme_get`、`control_theme_create`、`control_theme_assign`，支持读取、创建、绑定、解除和撤销 Control 的 Theme 资源分配。
- `control_theme_defaults_set`、`control_theme_defaults_clear`，支持嵌入式 Theme 默认字体、字体大小与基础缩放。
- `control_theme_item_upsert`、`control_theme_item_clear`，支持嵌入式 Theme 的颜色、常量、字体大小、字体、图标和 `StyleBoxFlat` 条目。
- `collision_shape_get`、`collision_shape_set`、`collision_shape_clear`，支持 `CircleShape2D`、`RectangleShape2D`、`CapsuleShape2D`、`SegmentShape2D`、`SeparationRayShape2D`、`WorldBoundaryShape2D`、`ConvexPolygonShape2D` 与 `ConcavePolygonShape2D` 的场景内嵌资源编辑。
- `collision_object_get_layers`、`collision_object_set_layers`，支持 `CollisionObject2D` 的碰撞 layer/mask 位与 1-32 层编号之间的可读转换。
- `area_2d_get`、`area_2d_set`，支持 `Area2D` 的监测、优先级、重力与阻尼覆盖，枚举使用稳定的可读名称。
- `physics_body_2d_get`、`physics_body_2d_set`，支持 `StaticBody2D`、`AnimatableBody2D`、`CharacterBody2D` 与 `RigidBody2D` 的专属行为配置；角色平台层以 1-32 层编号数组表示。
- `joint_2d_get`、`joint_2d_set`，支持 `PinJoint2D`、`GrooveJoint2D`、`DampedSpringJoint2D` 的物理参数与安全端点绑定；端点采用稳定场景路径并由插件转换为相对 `NodePath`。
- `ray_cast_2d_get`、`ray_cast_2d_set`，支持 `RayCast2D` 的持久查询配置、筛选标志和以 1-32 层编号表示的碰撞掩码。
- `shape_cast_2d_get`、`shape_cast_2d_set`、`shape_cast_2d_shape_clear`，支持 `ShapeCast2D` 的持久查询配置与独立内嵌 `Shape2D` 的创建、替换、清除、撤销/重做。
- `navigation_2d_get`、`navigation_2d_set`，支持 `NavigationRegion2D`、`NavigationAgent2D`、`NavigationObstacle2D`、`NavigationLink2D` 的安全语义配置；导航与避障位域使用 1-32 层编号数组。
- `navigation_polygon_get`、`navigation_polygon_create`、`navigation_polygon_geometry_set`、`navigation_polygon_outline_set`、`navigation_polygon_outline_remove`、`navigation_polygon_make_from_outlines`、`navigation_polygon_bake_request`、`navigation_polygon_bake_result_get`、`navigation_polygon_clear`，支持 NavigationRegion2D 的内嵌 NavigationPolygon 创建、绑定、凸多边形索引、轮廓、轮廓构建、移除、解绑，以及当前场景子树的异步源几何 Bake。Bake 在新复制的资源上执行，仅当编辑场景和原资源均未改变时才经 UndoRedo 提交；否则返回 `stale`，不覆盖后续编辑。
- `light_2d_get`、`light_2d_set`，支持 `PointLight2D` 与 `DirectionalLight2D` 的颜色、能量、混合模式、阴影、层位、法线高度、PointLight 纹理/偏移/缩放和 DirectionalLight 阴影距离；全部配置在单个撤销事务中更新。
- `light_occluder_2d_get`、`light_occluder_2d_set`，支持 `LightOccluder2D` 的光照层位、SDF collision 与独立内嵌 `OccluderPolygon2D` 的创建、替换和清除；闭合多边形会拒绝退化、自交或不可三角化的几何，避免修改共享或外部遮挡资源。
- `camera_2d_get`、`camera_2d_set`，支持 `Camera2D` 锚点、拖拽边距与偏移、限位、平滑、更新回调、缩放和当前场景内 `Viewport`/`SubViewport` 绑定；可读枚举使用稳定名称，所有更新在单个撤销事务中完成。
- `parallax_2d_get`、`parallax_2d_set`，支持 `Parallax2D` 的自动滚动、相机跟随、滚动限位、重复尺寸/次数与偏移缩放；拒绝无效限位和负重复尺寸。
- `canvas_layer_get`、`canvas_layer_set`，支持 `CanvasLayer` 的 viewport 绑定、层级、跟随、偏移、旋转、缩放、完整 Transform2D 与可见性；同一事务拒绝同时设置 `transform` 和派生的偏移/旋转/缩放，避免顺序依赖。
- `gpu_particles_2d_get`、`gpu_particles_2d_set`，支持 GPUParticles2D 的公开持久化节点配置、现有 `Texture2D`/`Material` 资源绑定和场景内子发射器绑定；所有更新均在单个撤销事务中完成。
- `particle_process_material_2d_get`、`particle_process_material_2d_create`、`particle_process_material_2d_set`，支持 GPUParticles2D 的 ParticleProcessMaterial 查询、独立内嵌材质创建，以及发射、速度、加速度、缩放、颜色、湍流、碰撞和子发射器的复制后替换编辑；外部或共享材质不会被原地修改。
- `particle_process_material_2d_curve_get`、`particle_process_material_2d_curve_bind`、`particle_process_material_2d_curve_set`、`particle_process_material_2d_curve_clear`，支持 GPUParticles2D ParticleProcessMaterial 的全部 17 个 2D 标量 CurveTexture 槽位查询、项目资源绑定、复制后替换的内嵌编辑和解绑，覆盖纹理宽度/模式以及嵌套 Curve 的范围、烘焙、点和切线。
- `particle_process_material_2d_gradient_get`、`particle_process_material_2d_gradient_bind`、`particle_process_material_2d_gradient_set`、`particle_process_material_2d_gradient_clear`，支持 color 和 initial_color GradientTexture1D 的查询、项目资源绑定、复制后替换的内嵌编辑和解绑，覆盖 HDR、纹理宽度及嵌套 Gradient 的色标和插值；外部或共享的材质、纹理和 Gradient 均不会被原地修改。
- `canvas_item_material_get`、`canvas_item_material_create`、`canvas_item_material_bind`、`canvas_item_material_set`、`canvas_item_material_clear`，支持任意本地 CanvasItem 上 CanvasItemMaterial 的查询、内嵌创建、项目资源绑定、复制后替换的 blend/light/粒子图集动画配置和解绑；外部或共享材质不会被原地修改，替换非 CanvasItemMaterial 前必须显式确认。
- `canvas_item_shader_get`、`canvas_item_shader_create`、`canvas_item_shader_bind`、`canvas_item_shader_set`、`canvas_item_shader_uniforms_set`、`canvas_item_shader_uniforms_clear`、`canvas_item_shader_clear`，支持任意本地 CanvasItem 上 Godot 解析为 `canvas_item` 的 ShaderMaterial 查询、内嵌创建、项目资源绑定、复制后替换源码、运行时 uniform 发现/安全批量写入/恢复默认值和解绑；外部或共享 ShaderMaterial/Shader 不会被原地修改，内嵌源码限 65,536 字符且不支持 `#include`。
- `cpu_particles_2d_get`、`cpu_particles_2d_set`，支持 CPUParticles2D 的发射、时间、纹理绑定、点/法线/颜色发射几何、方向与重力、全部公开 min/max 运动参数、颜色和 split scale；所有写入在单个撤销事务中完成。
- `cpu_particles_2d_curve_get`、`cpu_particles_2d_curve_bind`、`cpu_particles_2d_curve_set`、`cpu_particles_2d_curve_clear`，支持 CPUParticles2D 全部 14 个参数 Curve 槽位的查询、项目资源绑定、复制后替换的内嵌编辑和解绑；外部或共享 Curve 不会被原地修改。
- `cpu_particles_2d_gradient_get`、`cpu_particles_2d_gradient_bind`、`cpu_particles_2d_gradient_set`、`cpu_particles_2d_gradient_clear`，支持 color 和 initial_color Gradient 坡度的查询、项目资源绑定、复制后替换的内嵌编辑和解绑；外部或共享 Gradient 不会被原地修改。
- `tile_map_layer_get`、`tile_map_layer_cells_get`、`tile_set_get`、`tile_set_layers_get`、`tile_set_atlas_tile_get`、`tile_set_create`、`tile_set_clear`、`tile_set_atlas_source_create`、`tile_set_atlas_tile_create`、`tile_set_physics_layer_create`、`tile_set_navigation_layer_create`、`tile_set_occlusion_layer_create`、`tile_set_custom_data_layer_create`、`tile_set_layer_set`、`tile_set_layer_remove`、`tile_set_terrain_set_create`、`tile_set_terrain_create`、`tile_set_terrain_set_remove`、`tile_set_terrain_remove`、`tile_set_atlas_alternative_create`、`tile_set_atlas_tile_terrain_set`、`tile_set_atlas_tile_custom_data_set`、`tile_set_atlas_tile_collision_set`、`tile_set_atlas_tile_navigation_set`、`tile_set_atlas_tile_occlusion_set`、`tile_map_layer_cells_set`、`tile_map_layer_terrain_paint`、`tile_map_layer_cells_clear`，支持 TileMapLayer 的内嵌 TileSet 创建/解绑、Atlas Source、基础与替代 Atlas tile、物理/导航/遮挡/custom-data 层定义的编辑删除、terrain 集和 terrain 的创建删除、已验证的 per-tile terrain/custom data、读取/原子替换 TileData 碰撞多边形、导航多边形和 OccluderPolygon2D、分页 cells 读取、已验证的 cells 批量写入/清除，以及 connect/path terrain 绘制与精确撤销重做。
- 重命名和重新挂载时迁移场景内直接 `NodePath` 属性及内嵌 `AnimationPlayer` 动画轨道。
- 重新挂载默认保持 `Node2D`/`Control` 的全局视觉位置，并允许调用方关闭该行为。

当前结构编辑拒绝对 PackedScene 内部节点进行跨边界编辑，并拒绝包含不受支持 3D 节点的子树；`node_instance_scene` 可安全插入或删除完整 2D 实例根，`node_duplicate`/`node_reparent` 可复制或重新挂载没有本地 override 子节点的完整实例根并保留内部 owner。实例内部编辑和带本地 override 的实例根结构编辑仍属于后续 PackedScene 批次。删除会预检直接 `NodePath` 和动画轨道，避免留下悬空引用。动画工具仅写入场景内嵌 `AnimationLibrary`/`Animation`，并且只创建或修改本地 2D/UI 节点的属性值轨道；外部资源、导入轨道和方法/音频/嵌套动画轨道仍属于后续阶段。通用布局工具拒绝由 `Container` 管理的子节点；容器工具仅允许编辑场景内本地 Container 和其直接 Control 子节点，并将子节点范围限定为最小尺寸、尺寸标志和伸缩比例。样式工具只创建独立的节点本地 `StyleBoxFlat` override，不会修改共享 Theme 或外部资源。Theme 工具可绑定外部 `res://` Theme，但它们在 MCP 内只读；可写范围限于场景内嵌 Theme，因此全部 Theme 变更都能随场景撤销和重做。字体可绑定项目 `Font` 或新建内嵌 `SystemFont`，图标仅绑定项目中已有的 `Texture2D`。碰撞形状工具创建或复制独立内嵌的 `Shape2D` 后替换节点分配，不修改共享或外部 Shape2D；碰撞层工具只改动本地 `CollisionObject2D` 的 layer/mask。Area/Body/Joint 工具仅允许已核验的公开物理配置，并在写入前校验枚举、层位、端点类型与关键数值约束；RayCast/ShapeCast 工具仅保存配置和独立内嵌 Shape2D，不在静态编辑器中伪造运行时命中结果；导航节点工具支持 Region、Agent、Obstacle、Link 的安全配置与层位；NavigationPolygon 几何和轮廓工具仅以复制后替换的内嵌资源方式写入，避免原地修改共享或外部资源。异步源几何 Bake 限制为当前编辑场景子树和 `root_node_children` 模式，解析在编辑器主线程进行、烘焙在 Godot 后台任务中进行；回调仅在编辑场景、节点和原 NavigationPolygon 保持不变时通过一个 UndoRedo 事务绑定复制结果，其他情况标为 `stale`。Godot 未公开提供 Bake 取消 API，因此协议不会伪造取消结果。PointLight2D 与 DirectionalLight2D 仅允许经过类型和范围校验的光照属性，PointLight 纹理仅可来自项目内现有的 `Texture2D`；LightOccluder2D 总是新建内嵌遮挡资源后替换，清除也在同一撤销事务内完成。Camera2D 与 CanvasLayer 的 `custom_viewport_path` 只接受当前场景内的 `Viewport`/`SubViewport`，空字符串恢复默认 viewport；为兼容 Godot setter 的非空要求，插件内部使用节点对象执行该恢复，但 MCP 协议始终返回空字符串。TileMap 工具创建内嵌 TileSet/Atlas Source/tiles；物理层、导航层、遮挡层、terrain 集和 terrain、自定义数据层、替代 atlas tile 与 per-tile terrain/custom data、TileData 碰撞多边形、导航多边形及 OccluderPolygon2D 均在复制 TileSet 后替换，cells 写入批次则在一个编辑器撤销事务内完成。`tile_set_layer_set`、层/terrain 删除和 `tile_map_layer_terrain_paint` 同样使用复制后替换或精确 cell 快照，path 逐点验证相邻性，并支持完整撤销重做。碰撞多边形写入会拒绝退化或不可分解的几何；导航多边形写入要求凸、有序且无重复索引，并用 `clear: true` 显式解除该层资源；遮挡多边形支持 closed/open 和 cull mode，并拒绝退化的闭合几何。全部更新均在同一撤销事务中完成。信号工具仅操作场景内本地节点的持久化连接，并要求目标方法已存在，不会生成或修改脚本回调。这是为了避免 Agent 在无法证明安全的情况下静默破坏引用。自动脚本回调生成仍属于后续阶段。

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

协议已显式支持 `Vector2`、`Vector2i`、`Rect2`、`Transform2D`、`Color`、`NodePath`、`StringName`、枚举、TypedArray、TypedDictionary 和 Resource 引用。类型化容器按当前 Godot 属性的容器类型重建并逐项转换；字符串键字典使用 JSON object，其他键类型使用 `entries` 数组，避免 JSON 键字符串化。

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
- 由项目 GDExtension 提供且满足上述继承规则的运行时节点。
- 继承自合法基类的项目自定义脚本。

默认拒绝：

- `Node3D` 派生节点。
- Godot `ClassDB` 标记为 `API_EDITOR` 或 `API_EDITOR_EXTENSION` 的编辑器内部类型，即使它们碰巧继承 `Control`。
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
- 已交付：光照、遮挡、CanvasItemMaterial 的安全绑定和复制后替换配置、仅接受 `canvas_item` 类型的 ShaderMaterial 创建/项目资源绑定/复制后替换源码与运行时 uniform 的安全发现、批量写入和恢复默认值、相机、视口组合、Path2D/Curve2D 的独立内嵌资源替换与 Bézier 点编辑、Skeleton2D/Bone2D 的安全层级创建与 Rest Pose、AudioStreamPlayer2D 的外部流绑定和空间播放配置、GPUParticles2D 的完整节点配置/资源绑定/场景内子发射器编排、ParticleProcessMaterial 的内嵌创建与核心 2D 复制后替换编辑、17 个标量 CurveTexture 槽位与两类 GradientTexture1D 坡度，以及 CPUParticles2D 的核心发射、运动、绘制和纹理绑定配置、全部 14 个参数 Curve 槽位与两类 Gradient 坡度的安全资源编辑。`Sprite2D`、`Line2D`、`Polygon2D` 均支持独立 get/set 工具，项目路径纹理/Curve/Gradient 仅作类型校验后绑定，点、UV、颜色和枚举受数量与几何约束；`AnimatedSprite2D` 提供节点配置、动画列表/分页帧读取，以及 SpriteFrames 动画新增或替换、改名和删除能力。BaseButton 按钮工作流支持所有派生节点的交互状态与项目资源绑定，文本 Button 派生节点的文本/图标/排版，以及 TextureButton 的五态贴图与命中配置。SpriteFrames 修改始终复制并内嵌替换资源，不会原地写入外部或共享资源；每次写入均为单个 Godot 撤销事务。

### 阶段 6：运行反馈

- 运行/停止、编辑器和游戏日志、截图、输入模拟和测试运行。
- 已交付：`editor_run` 支持安全启动当前、主场景或现有 `res://` 自定义 `PackedScene`；`editor_stop` 可幂等停止运行中的场景。`runtime_get_state`、`runtime_logs_get`、`runtime_screenshot_request/get` 与 `runtime_input_send/result_get` 通过插件托管的 autoload 和 `EditorDebuggerPlugin` 连接真实游戏进程，支持带序号的日志、受 1024 像素/1 MB 上限约束的根视口 PNG/JPEG 截图、以及 action/键盘/鼠标/多点触摸事件注入回执。触摸支持 0 至 31 的索引、按下/抬起/取消、拖拽相对坐标和可选屏幕相对位移、压感、倾角与手写笔反转，且服务端与游戏端均严格验证固定 JSON 契约；速度由 Godot 的输入管线按时间与相对位移计算，不接受伪造值。`runtime_audio_stream_player_2d_control/result_get` 采用相同的请求 ID 轮询模型，限制为活动场景树内的 `AudioStreamPlayer2D` 及 `get`、`play`、`stop`、`seek` 四个动作，结果带回播放状态和 stream 元数据。
- 已交付：`runtime_performance_sample_request/result_get` 以 0.1 至 30 秒的有界采样窗口返回实际时长、帧数、估算 FPS、process delta min/mean/max，以及 `Performance.TIME_FPS`、静态内存、对象数量和当帧 draw calls。游戏进程只接受固定 `performance_sample` 调试消息，最多四个并发样本，编辑器仅保存有界轮询结果。
- 已交付：`runtime_screenshot_assert` 只在 MCP Python 进程中解码已完成的 PNG 截图，不向游戏开放表达式或脚本执行。解析器限制为 1 MB、1024 像素、非交错 8-bit RGB/RGBA PNG，验证 chunk CRC 并支持 PNG filter 0-4；断言限定为 `dimensions`、`pixel`、`region_mean` 与 `color_presence` 四类，每次最多 32 条。
- 已交付：`runtime_test_run` 将现有受限启动、等待、输入、性能和截图接口编排成一次有总时限的测试。它只能启动 current/main/项目内 custom 场景，等待编辑器运行和 runtime bridge 连接，返回结构化 `passed`/`failed`/`error`，默认停止测试场景。编辑器输出与游戏输出保持独立，绝不将编辑器界面截图冒充为游戏画面。

### 阶段 7：完整性审计

- 已交付：`class_2d_coverage` 从运行中 Godot 的 `ClassDB` 生成分页的 2D 节点和资源清单。每个条目记录基础支持、专用语义工具、可实例化状态和直接语义烟测状态；资源范围显式限定为当前 2D 工作流涉及的 Shape2D、导航、TileSet、Path、Curve、Gradient、光照、音频、粒子、材质、Shader、Theme、StyleBox、Font、Texture2D、SpriteFrames、ButtonGroup、Shortcut 和 LabelSettings 家族。`class_2d_coverage_snapshot` 在服务端收集完整分页清单并附上引擎元数据；`class_2d_coverage_diff` 接受这个基线并报告新增、移除、字段变化和可能破坏兼容性的变化。`class_2d_describe` 仅对同一类型策略允许的节点和已审计资源返回运行中 Godot 的继承链与分页的公开属性、方法、信号、枚举；属性包含声明类型、类名、提示、只读和 getter/setter，方法/信号包含参数、默认参数数和 flags。编辑器 API 类型会在集中类型策略中排除，避免错误写入游戏场景。
- 已交付：Godot 4.7 真实编辑器冒烟在隔离场景中对每个当前允许的 2D 节点执行创建、属性读取、保存/重开、删除和一次删除操作的撤销/重做；任何单类失败都会使 CI 失败。

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
