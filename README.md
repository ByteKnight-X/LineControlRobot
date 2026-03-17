# 产线控制桌面端 V0

## 背景
本仓库用于实现《[PRD]产线控制软件V0》桌面端前端。当前主线已切换为《[DesignDoc]工艺路线设计B0.0》定义的工艺路线设计模块。

当前页面标准名为 `ProcessRoutePage`，目标是在不修改 `forms/process_routine_page.ui` 信息架构的前提下，完成工艺路线设计最小闭环。

## 当前范围（ProcessRoutePage）
当前阶段只聚焦最小闭环：
- 加载 `forms/process_routine_page.ui`
- 保持现有 `process_routine_page.ui` 设计稿不变
- 查询并导入历史工艺路线
- 将 `process_route_header`、`process_route_loop_line`、`process_route_loop_step_line` 与前端视图对应
- 依据 `docs/json2graph.py` 规则转换为 GML/GraphML
- 展示工艺路线数字孪生图
- 展示并编辑节点信息
- 展示校验反馈
- 批准并回填版本信息
- 保留仿真、AI 优化、AI 校验入口，但当前允许使用占位符

## 当前命名与状态约定
- 页面设计稿：`forms/process_routine_page.ui`
- 页面类标准名：`ProcessRoutePage`
- 当前实现文件：`routine_page.py`
- 历史实现名：`RoutinePage`
- `RoutinePage` 仅作为历史命名或代码现状说明
- 后续文档、页面命名、导航命名应统一向 `ProcessRoutePage` 收敛

## 当前页面数据约定
`ProcessRoutePage` 默认围绕以下页面状态量与产线上下文组织展示：

### 页面状态量
- `page_status`
- `loading`
- `dirty`
- `current_route`
- `active_loop_id`
- `active_node_id`
- `validation_summary`
- `simulation`
- `simulation_status`
- `objective_weight`
- `assumption`
- `library_dialog`

### `process_route_header`
典型字段：
- `lot_id`
- `process_route_id`
- `process_route_version`
- `line_spec_id`
- `approved_by`
- `status`

### `process_route_loop_line`
典型字段：
- `lot_id`
- `process_route_id`
- `process_route_version`
- `loop_id`
- `loop_index`
- `entry_node_id`
- `exit_node_id`
- `loop_count`

### `process_route_loop_step_line`
典型字段：
- `lot_id`
- `process_route_id`
- `process_route_version`
- `loop_id`
- `node_index`
- `node_id`
- `node_type`
- `instruction`
- `params`

### `validation_summary`
典型字段：
- `passed`
- `errors`
- `risks`

### `simulation`
当前阶段允许占位，但至少保留：
- `objective_weight`
- `simulation_results`
- `assumption`

### 产线上下文
- `order_context`
- `lot_context`
- `process_plan_context`
- `process_route_context`
- `constraint_context`

## 工艺路线数孪渲染链路
当前页面的主展示链路如下：
- 后端返回 `process_route_header`、`process_route_loop_line`、`process_route_loop_step_line`
- 前端先将三段模型与页面视图结构对应
- 再根据 `docs/json2graph.py` 的约定转换为 GML/GraphML
- `graphicsDigitalTwin` 消费转换结果展示节点、连线与循环关系

这意味着当前数孪展示不直接消费原始后端 JSON，而是消费转换后的 GML/GraphML 结果。

## 当前接口依赖
- `GET /process_route/list`：查询历史工艺路线版本列表
- `GET /process_route/{process_route_id}/{process_route_version}`：查询指定工艺路线详情
- `POST /process_route/validate`：提交当前编辑方案进行校验
- `POST /process_route/approve`：批准当前工艺路线方案并回填正式版本

说明：
- `validate` 是最小闭环中的必备动作入口
- 仿真、AI 优化、AI 校验在当前阶段允许占位
- 占位能力需提供清晰反馈，不静默失败
- `[批准方案]` 前端前置条件：`page_status == "validated"`

## 快速开始
```bash
python3 -m venv .venv_linux
pip install -r requirement.txt
python app.py
```

联调前确认本地后端已启动在：`http://127.0.0.1:18000`

## 关键文件
- `forms/process_routine_page.ui`：当前阶段 UI 结构基准
- `routine_page.py`：当前页面行为层文件
- `app.py`：主窗口装配入口
- `utilities/backend_client.py`：统一后端客户端入口
- `docs/[DesignDoc]工艺路线设计B0.0.docx`：当前阶段设计文档
- `docs/后端V0.md`：接口说明
- `docs/json2graph.py`：工艺路线数孪转换参考

## 测试与验收
当前阶段验收重点：
- 页面可正常加载 `forms/process_routine_page.ui`
- 主窗口可进入工艺路线页
- 历史工艺路线可导入
- 三段模型可与前端视图对应并转换为 GML/GraphML
- 数孪图可展示节点、连线、循环关系
- 校验与批准闭环可走通
- 占位功能反馈清晰，不静默失败

## 非目标范围
当前阶段不扩展以下内容：
- 不修改 `forms/process_routine_page.ui`
- 不重做导入页
- 不提前实现完整仿真
- 不提前实现完整 AI 优化
- 不提前实现完整 AI 校验智能体
- 不提前改造 prepare / monitor / KPI 页
- 不做跨页面大规模重构
