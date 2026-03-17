# AGENTS.md — 产线控制桌面端 V0（工艺路线设计主线）

## 背景
本仓库为产线控制前端桌面版，当前主要开发目标收敛到工艺路线设计（[DesignDoc]工艺路线设计B0.0）。仓库中已有的“生产任务导入”与“网版设计”模块保持不变。

## 目标
- 实现并集成工艺路线设计页面（基于 `forms/process_routine_page.ui`）。
- 支持展示、导入历史版本、编辑节点指令与参数、校验与批准的最小闭环。
- 将三段后端模型（`process_route_header` / `process_route_loop_line` / `process_route_loop_step_line`）映射并按 `docs/json2graph.py` 规则转换为前端可用的数孪表示。
- 保留仿真、AI 校验/优化入口（允许占位提示），但需有明确反馈。
- 页面须本地可运行、可挂载于主窗口并可验收。

## 技术约束
- Python 3.10+
- PyQt5 >= 5.15.7, PyQtWebEngine >= 5.15.7, PyQt5-sip
- requests >= 2.31.0
- 遵循 Google Python Style Guide
- 后端默认本地联调地址：`http://127.0.0.1:18000`

## 实现约束
- 事实与实现依据：
  - 设计文档：`docs/[DesignDoc]工艺路线设计B0.0.docx`
  - 接口说明：`docs/后端V0.md`
  - 数孪转换参考：`docs/json2graph.py`
- UI 基准：`forms/process_routine_page.ui`（不得随意改信息架构或按钮语义）
- Python 层职责：加载 UI、绑定事件、组织数据、调用 `utilities/backend_client.py`、将后端数据模型转换为数孪视图
- 后端交互通过 `utilities/backend_client.py` 封装；缺字段或后端不可达时页面须给出明确提示（不得静默失败）
- 保持项目相对路径处理；不要写死 Windows 绝对路径
- 不在生成的 `_ui.py` 中手改逻辑；不做跨页面大规模重构；仿真/AI 功能可为占位但必须反馈状态

## 关键目录
- `forms/process_routine_page.ui`
- `routine_page.py`
- `app.py`
- `utilities/backend_client.py`
- `docs/[DesignDoc]工艺路线设计B0.0.docx`
- `docs/后端V0.md`
- `docs/json2graph.py`
- 参考/现有模块（保持不变）：`import_page.py`、`separation_page.py`、`prepare_page.py`

## 必备命令
- 创建虚拟环境（Windows）：`python -m venv .venv_windows`
- 创建虚拟环境（WSL/Linux）：`python3 -m venv .venv_linux`
- 安装依赖：`pip install -r requirement.txt`
- 启动前端：`python app.py`
- 联调前确认后端已启动：`http://127.0.0.1:18000`
