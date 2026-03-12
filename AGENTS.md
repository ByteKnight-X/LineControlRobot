# AGENTS.md — 产线控制桌面端 V0

## 背景
本仓库用于实现《[PRD]产线控制软件V0》桌面端前端。生产任务导入页不再是当前主线，当前主线为《[DesignDoc]网版设计B0.1》。

网版设计页是当前前端工艺规划界面，目标是围绕 `forms/separation_page.ui` 搭建可展示、可校验、可批准、可流转的页面闭环。

## 目标
完成《[DesignDoc]网版设计B0.1》对应的 `separation_page` 前端集成。

当前阶段能力范围：
- 展示方案元信息
- 展示图案预览
- 展示并编辑网版工艺参数
- 展示 SOP
- 展示校验信息
- 提供历史方案入口并支持从版本库回填历史详情
- 提供 AI 优化入口
- 提供显式校验入口
- 提供批准入口并支持批准落库后回填正式版本
- 提供下一步流转入口
- 保持页面可本地运行、可挂载、可验收

当前阶段命名约定：
- 页面设计稿：`forms/separation_page.ui`
- 页面类标准名：`SeparationPage`
- 历史旧名：`LayeringPage`
- 当前行为层文件：`separation_page.py`

## 当前阶段核心控件与区块
顶部动作：
- `btnImportScheme`
- `btnGenerate`
- `btnValidate`
- `btnApprove`
- `btnNext`

画布区：
- `graphicsPreview`

方案元信息区：
- `txtPlanId`
- `txtPlanVer`
- `txtSku`
- `txtCodeRange`
- `txtColorway`
- `txtApprover`
- `txtStatus`

参数区：
- `txtWireMaterial`
- `txtWireModel`
- `txtWireDia`
- `cmbStretchMethod`
- `spinStretchAngle`
- `spinTpi`
- `spinTension`
- `txtFrameSpec`

SOP 区：
- `txtSOPSteps`

校验反馈区：
- `txtValidationInfo`

## 当前阶段最小前端数据契约
当前阶段默认围绕以下页面状态量与产线上下文字段收敛实现：
- `page_status`
- `loading`
- `dirty`
- `current_plan`
- `active_mesh_index`
- `validation_summary`
- `library_dialog`
- `order_context`
- `lot_context`
- `process_plan_context`
- `process_route_context`
- `constraint_context`

### `process_plan_header`
至少包含：
- `process_plan_id`
- `process_plan_version`
- `sku`
- `code_range`
- `colorway`
- `validated_by`
- `status`

### `process_plan_line`
至少包含：
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

### `validation_summary`
至少包含：
- `passed`
- `errors`
- `risks`

### `process_plan_context`
至少包含：
- `process_plan_header`
- `process_plan_line`

### `process_plan` 接口依赖
- `GET /process_plan/list`：前端客户端 `process_plans.list()` 需返回 `list[process_plan_header]`
- `GET /process_plan/{process_plan_id}-{process_plan_version}`：用于加载历史方案详情
- `POST /process_plan/validate`：用于校验当前编辑方案并回填 `validation_summary`
- `POST /process_plan/approve`：用于批准当前方案并返回正式版本信息

约束：
- 缺字段时允许占位，但不得静默失败
- 字段名确定后，不在页面层随意改名
- 页面内部映射必须围绕新 UI 命名，而不是继续沿用旧控件名
- `[批准方案]` 前端前置条件固定为 `page_status == "validated"`

## 技术约束
- Python 3.10+
- PyQt5>=5.15.7
- PyQtWebEngine>=5.15.7
- PyQt5-sip
- requests>=2.31.0
- 编码风格采用 Google Python Guide
- 页面字段命名、页面类名、导航名称发生变化时，必须同步更新 `README.md` 和 `AGENTS.md`
- 新增页面数据契约或上下文字段时，需同步更新文档说明

## 实现约束
- 当前阶段以 `docs/[DesignDoc]网版设计B0.1.pdf` 作为第一事实来源
- `docs/[PRD]产线控制软件V0.pdf` 只作为范围边界参考
- UI 结构与控件命名以 `forms/separation_page.ui` 为准
- 页面类名标准为 `SeparationPage`
- `LayeringPage` 仅作为历史命名参考
- 主窗口装配、日志文案、注释、文档命名需要跟随 `SeparationPage`
- Python 层只负责：加载 UI、绑定事件、组织数据、调用后端客户端
- 后端调用统一通过 `utilities/backend_client.py` 封装
- 缺少后端数据时，必须在反馈区提供明确说明
- 不擅自改动设计稿表达的信息架构、区块布局和按钮语义
- 不在生成后的 `_ui.py` 中手改逻辑
- 不在未明确要求时扩大为跨页面重构
- 不提前引入新的前端架构层级
- 路径处理必须兼容项目相对路径，不写死 Windows 绝对路径

## 当前阶段不扩展内容
- 不重做导入页
- 不提前实现 routine / prepare / monitor / KPI 页
- 不修改 `forms/separation_page.ui` 的信息架构
- 不脱离设计稿扩展为通用前端组件体系
- 不在未明确要求时进行跨页面大规模重构

## 关键目录
- `forms/separation_page.ui`：当前阶段设计稿与 UI 基准
- `separation_page.py`：当前页面行为层文件，对应 `SeparationPage`
- `app.py`：主窗口装配与页面挂载入口
- `forms/main_window.ui`：主窗口 UI
- `utilities/backend_client.py`：统一后端客户端入口
- `docs/[DesignDoc]网版设计B0.1.pdf`：当前阶段设计文档
- `docs/[PRD]产线控制软件V0.pdf`：产品范围参考

## 必备命令
- 创建 Windows 虚拟环境：`python -m venv .venv_windows`
- 创建 WSL 虚拟环境：`python3 -m venv .venv_linux`
- 安装依赖：`pip install -r requirement.txt`
- 启动前端：`python app.py`
- 联调前确认本地后端已启动在 `http://127.0.0.1:18000`

## 测试与验收场景

1. `SeparationPage` 页面加载
用例名称：页面可正常加载新设计稿  
断言：`forms/separation_page.ui` 能被正常加载  
断言：页面初始化不再依赖旧控件名主导主流程

2. 主窗口挂载
用例名称：主窗口可挂载网版设计页  
断言：页面能从主窗口进入  
断言：导航命名逐步向 `SeparationPage` 收敛

3. 顶部动作按钮绑定
用例名称：顶部五个按钮具备明确行为  
断言：`btnImportScheme` 可打开版本库并加载历史方案详情  
断言：`btnApprove` 可调用批准接口并回填正式版本信息  
断言：`btnGenerate`、`btnValidate`、`btnNext` 均完成信号绑定  
断言：后端未接通时，页面反馈明确，不静默失败

4. 元信息回填
用例名称：方案元信息可显示  
断言：`txtPlanId`、`txtPlanVer`、`txtSku`、`txtCodeRange`、`txtColorway`、`txtApprover`、`txtStatus` 都有数据或明确占位

5. 参数区回填
用例名称：网版参数可展示  
断言：参数区字段可从 `process_plan_line` 回填  
断言：无数据时有明确默认值或提示

6. SOP 与校验反馈
用例名称：SOP 和校验区具备展示能力  
断言：`txtSOPSteps` 与 `txtValidationInfo` 可显示文本内容  
断言：校验失败与风险提示语义清晰

7. 文档一致性
用例名称：命名、控件、职责、数据契约一致  
断言：README、AGENTS、代码中的页面命名不再继续强化 `LayeringPage`  
断言：文档中列出的控件名与 `forms/separation_page.ui` 一致
