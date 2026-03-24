# AGENTS.md — 产线控制桌面端 V0（批次单自动生成与校验主线）

## 背景
本仓库为产线控制前端桌面版。

当前增量目标聚焦《`specs/[FeatureDoc]批次单自动生成与校验B0.0.pdf`》定义的“批次单自动生成与显式校验”链路，主链路收敛为：
- 生产任务导入（`production_order`）
- 候选批次单自动生成与显式校验（`lot` / `ai`）

本阶段是在已存在页面和功能基础上的增量约束补充。除批次单自动生成与校验相关内容外，其它已有功能、页面、模块保持不变，不在本次文档更新范围内。

## 目标
- 支持基于已导入生产任务生成候选批次单。
- 支持对候选批次单进行显式校验。
- 支持前端展示候选结果与校验结果。
- 保持导入页相关交互语义稳定。
- 页面须本地可运行、可联调、可验收。
- `forms/import_page.ui` 本次不能改。

## 技术约束
- Python 3.10+
- PyQt5 >= 5.15.7, PyQtWebEngine >= 5.15.7, PyQt5-sip
- requests >= 2.31.0
- 遵循 Google Python Style Guide
- 后端默认本地联调地址：`http://127.0.0.1:18000`
- 时间字段以 Unix timestamp / timestamp_ms 为准，前端展示时按东八区 datetime 处理
- 前端通过 `utilities/backend_client.py` 封装后端交互
- 不在生成的 `_ui.py` 中手改逻辑
- 保持项目相对路径处理；不要写死 Windows 绝对路径

## 实现约束
- 事实与实现依据：
  - 首要依据：`specs/[FeatureDoc]批次单自动生成与校验B0.0.pdf`
  - 其它已有功能与页面不在本次文档更新范围内
- UI 基准：`forms/import_page.ui`（本次明确不得修改，不得调整信息架构、控件语义或按钮行为定义）
- Python 层职责：加载现有 UI、绑定事件、组织页面状态、调用 `utilities/backend_client.py` 完成后端交互
- 页面职责围绕生产任务生成候选批次单，并对候选批次单执行显式校验
- 候选结果与校验结果必须显式展示，不得静默失败
- 与批次单相关的前端逻辑必须区分“候选结果”和“落库结果”：
  - `POST /ai/generate_lots` 只返回候选批次单，不落库
  - `POST /ai/validate_lots` 只返回校验结果，不落库
  - 不得把候选结果当成已落库结果使用
- 页面核心数据围绕以下结构组织：
  - `production_order_header`
  - `production_order_line`
  - `lot_header`
  - `lot_line`
- 相关数据对象与字段命名应尽量贴合功能文档，不随意自造同义结构
- `lot_header` 典型关键字段至少保留：
  - `lot_id`
  - `source_order_id`
  - `production_line_id`
  - `status`
- `lot_line` 典型关键字段至少保留：
  - `lot_id`
  - `lot_line_id`
  - `source_order_id`
  - `source_order_line_id`
  - `color_separation_plan`
- `production_order` 与 `lot` 需要保留状态字段
- 标识符和关联关系应保持可追溯：
  - `order_id` 示例：`PO-20260206-01`
  - `lot_id` 示例：`LOT-20260206-001`
  - `lot` 必须能追溯到来源订单及订单行
- 校验结果需要显式呈现：
  - 成功/失败布尔结果 `passed`
  - `errors`
  - `risk_info` 或等价风险信息
  - 必要时展示后端 `message`
- 缺字段、结构不匹配或后端不可达时页面须给出明确提示（不得静默失败）
- 对现有模块采取增量方式接入，不为本次需求重写其它页面，不改变已有其它功能模块
- 不把本次文档扩展为其它功能的开发说明

## 关键目录
- `forms/import_page.ui`
- `import_page.py`
- `app.py`
- `utilities/backend_client.py`
- `specs/[FeatureDoc]批次单自动生成与校验B0.0.pdf`

## 必备命令
- 创建虚拟环境（Windows）：`python -m venv .venv_windows`
- 创建虚拟环境（WSL/Linux）：`python3 -m venv .venv_linux`
- 安装依赖：`pip install -r requirement.txt`
- 启动前端：`python app.py`
- 联调前确认后端已启动：`http://127.0.0.1:18000`
