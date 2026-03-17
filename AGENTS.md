# AGENTS.md — 产线控制桌面端 V0（生产准备主线）

## 背景
本仓库为产线控制前端桌面版，当前主要开发目标收敛到生产准备模块（`docs/[DesignDoc]生产准备B0.0.docx`）。仓库中已有的“生产任务导入”“网版设计”“工艺路线设计”模块保持现状，当前阶段重点是基于历史工艺路线版本生成并维护生产准备指令集。

## 目标
- 实现并集成生产准备页面（基于 `forms/prep_page.ui`）。
- 支持最小闭环：导入历史工艺路线版本、编辑准备指令、校验、下发并落库。
- 支持四类准备指令：网版、胶浆油墨、物料、设备。
- 以前端页面状态组织生产准备数据：`created`、`validated`、`released`、`finished`。
- 页面须本地可运行、可挂载于主窗口并可验收。

## 技术约束
- Python 3.10+
- PyQt5 >= 5.15.7, PyQtWebEngine >= 5.15.7, PyQt5-sip
- requests >= 2.31.0
- 遵循 Google Python Style Guide
- 后端默认本地联调地址：`http://127.0.0.1:18000`
- 后端接口说明：`docs/后端V0.md`

## 实现约束
- 事实与实现依据：
  - 设计文档：`docs/[DesignDoc]生产准备B0.0.docx`
  - 接口说明：`docs/后端V0.md`
- UI 基准：`forms/prep_page.ui`（不得随意改信息架构或按钮语义）。
- Python 层职责：加载 UI、绑定事件、组织页面状态、调用 `utilities/backend_client.py` 完成后端交互。
- 页面核心数据围绕以下结构组织：
  - `prep_instruction_header`
  - `mesh_prep_instruction_line`
  - `ink_prep_instruction_line`
  - `material_prep_instruction_line`
  - `equipment_prep_instruction_line`
  - `validation_summary`
- 页面状态至少覆盖：
  - `page_status`
  - `loading`
  - `dirty`
  - `active_tab`
  - `active_target_id`
  - `library_dialog`
  - `selected_instruction_id`
  - `selected_instruction_version`
  - `current_instruction_set`
- 后端交互通过 `utilities/backend_client.py` 封装；缺字段、结构不匹配或后端不可达时页面须给出明确提示（不得静默失败）。
- 保持项目相对路径处理；不要写死 Windows 绝对路径。
- 不在生成的 `_ui.py` 中手改逻辑；不做跨页面大规模重构。
- 准备指令需与工艺路线、生产任务、lot、工艺方案等上下文保持关联。

## 关键目录
- `forms/prep_page.ui`
- `prepare_page.py`
- `app.py`
- `utilities/backend_client.py`
- `docs/[DesignDoc]生产准备B0.0.docx`
- `docs/后端V0.md`
- 参考/现有模块（保持不变）：`import_page.py`、`separation_page.py`、`routine_page.py`

## 必备命令
- 创建虚拟环境（Windows）：`python -m venv .venv_windows`
- 创建虚拟环境（WSL/Linux）：`python3 -m venv .venv_linux`
- 安装依赖：`pip install -r requirement.txt`
- 启动前端：`python app.py`
- 联调前确认后端已启动：`http://127.0.0.1:18000`
