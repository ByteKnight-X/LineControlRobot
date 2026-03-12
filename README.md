# 产线控制桌面端 V0

## 背景
本仓库用于实现《[PRD]产线控制软件V0》桌面端前端。当前仅涉及前端修改，生产任务导入页不再是当前主线，当前主线为《[DesignDoc]网版设计B0.1》定义的 `separation_page` 前端集成。

## 当前范围（SeparationPage）
当前阶段能力范围：
- 加载并展示 `forms/separation_page.ui`
- 展示历史或当前工艺方案元信息
- 展示网版图案画布预览
- 展示并编辑网版工艺参数
- 展示 SOP 内容
- 展示校验结果与反馈信息
- 通过版本库加载历史已批准方案并回填当前页面
- 调用后端批准接口并回填正式方案版本信息
- 保留 AI 优化、AI 校验、下一步三个动作入口
- 保持页面可本地运行、可挂载、可验收

## 当前命名与状态约定
- 页面设计稿名：`separation_page.ui`
- 页面类标准名：`SeparationPage`
- 历史旧名：`LayeringPage`
- 当前行为层文件：`separation_page.py`
- `LayeringPage` 仅作为历史命名参考，不再作为新实现依据
- 后续代码、文档、主窗口装配应统一收敛到 `SeparationPage`

## 当前页面数据约定
`SeparationPage` 默认围绕以下页面状态量与产线上下文组织展示：

### 页面状态量
- `page_status`
- `loading`
- `dirty`
- `current_plan`
- `active_mesh_index`
- `validation_summary`
- `library_dialog`

### `process_plan_header`
典型字段：
- `process_plan_id`
- `process_plan_version`
- `sku`
- `code_range`
- `colorway`
- `validated_by`
- `status`

### `process_plan_line`
典型字段：
- `mesh_index`
- `material`
- `mesh_model`
- `diameter`
- `stretching`
- `stretching_degree`
- `tpi`
- `tension`
- `frame_specification`
- `pattern_design`
- `operation`

### 产线上下文
- `order_context`
- `lot_context`
- `process_plan_context`
- `process_route_context`
- `constraint_context`

### `validation_summary`
典型字段：
- `passed`
- `errors`
- `risks`

### `sop_steps`
- 可以是文本
- 也可以是步骤列表
- 前端统一通过 SOP 展示区渲染

## 当前接口依赖
- `GET /process_plan/list`：查询历史已批准方案列表，前端客户端返回 `list[process_plan_header]`
- `GET /process_plan/{process_plan_id}-{process_plan_version}`：查询某个历史方案详情并回填页面
- `POST /process_plan/validate`：提交当前编辑方案并回填 `validation_summary`
- `POST /process_plan/approve`：提交当前方案并回填后端生成的 `process_plan_id`、`process_plan_version`、`status`
- `[批准方案]` 前端前置条件：`page_status == "validated"`

## 快速开始
```bash
python3 -m venv .venv_linux
pip install -r requirement.txt
python app.py
```

如需联调，默认后端地址为：`http://127.0.0.1:18000`

## 关键文件
- `forms/separation_page.ui`：当前阶段唯一 UI 结构基准
- `separation_page.py`：当前页面行为层文件，对应 `SeparationPage`
- `app.py`：主窗口装配入口
- `forms/main_window.ui`：主窗口 UI
- `utilities/backend_client.py`：统一后端客户端入口
- `docs/[DesignDoc]网版设计B0.1.pdf`：当前阶段第一事实来源
- `docs/[PRD]产线控制软件V0.pdf`：产品范围边界参考

## 测试与验收
当前阶段前端验收重点：
- 页面可正常加载 `forms/separation_page.ui`
- 主窗口可挂载该页面
- `[版本库]` 可选择并加载历史方案详情
- `[批准方案]` 可调用后端批准并回填版本号与状态
- 元信息区、参数区、SOP 区、校验区具备数据回填或明确占位反馈
- 文档命名、页面命名、设计稿命名保持一致

## 非目标范围
当前阶段不扩展以下内容：
- 不重做导入页
- 不提前实现 routine / prepare / monitor / KPI 页
- 不修改 `forms/separation_page.ui` 的信息架构
- 不在本轮引入新的前端架构层级
- 不做跨页面大规模重构
