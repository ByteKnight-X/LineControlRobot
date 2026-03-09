# AGENTS.md — 产线控制桌面端V0

## 背景
- 本仓库用于实现《[PRD]产线控制软件V0》的桌面端。当前阶段是完成《[DesignDoc]生产任务导入B0》定义的生产任务导入闭环能力。
- 当前任务是基于`forms/`中的设计高完成前端集成；首先你需要完成生产任务导入页`forms\import_page.ui`的集成
- 前端需与后端`127.0.0.1:18000`联调

## 目标
- 基于 forms/ 中的设计稿完成各页面的 Python 适配
- 让主窗口导航与新 UI 命名保持一致
- 完成生产任务导入页的本地导入、展示、搜索、校验反馈
- 将导入页与后端导入接口连接


## 技术约束
- Python 3.10+
- PyQt5>=5.15.7
- PyQtWebEngine>=5.15.7
- PyQt5-sip
- requests>=2.31.0
- 编码风格采用Google Python Guide

## 实现约束
- 优先修改页面控制层，使其匹配 forms/ 中已定稿的 UI 结构和控件命名
- 不擅自改动设计稿表达的信息架构、主要区块布局和按钮语义
- 修改页面流转时，必须同步维护主窗口导航与页面装配关系
- 后端接口地址、请求 payload、响应 key 若被前端依赖，需在代码中集中管理
- 页面逻辑改动应尽量围绕以下职责展开：
  1）导入页：订单/批次展示、校验反馈、导入与优化入口 
  2）网版页：方案展示、参数回填、下一步流转
  3）工艺路线页：路线展示、仿真结果/约束展示、下一步流转
  4）准备页：准备对象列表、指令内容展示、下发动作
- 若某页面设计稿已存在但后端数据未完全就绪，可保留占位行为，但必须在反馈区明确说明缺失点
- 未明确要求时，不做跨页面的大规模重构，不引入新的架构层级
- 与设计稿无关的历史版本文件（*_v0.py、*_v1.py、旧 .ui）只能作为参考，不应继续主导实现决策
- UI 结构以 forms/*.ui 为准，Python 层只负责：加载 UI、绑定事件、组织数据、调后端接口
- 不在生成后的 _ui.py 中手改逻辑
- 页面间共享状态统一走主窗口上下文，例如 controller.context
- 后端调用统一通过单独客户端封装，不在每个按钮槽函数里散落 URL 常量
- 路径处理必须兼容项目相对路径，不写死 Windows 绝对路径
- 若新设计稿已替换旧页面，旧控件命名不可继续作为主实现依据


## 关键目录
- forms/：当前阶段最重要的 UI 设计稿来源
- forms/import_page.ui：生产任务导入页
- forms/separation_page.ui：网版设计页
- forms/process_routine_page.ui：工艺路线页
- forms/prep_page.ui：生产准备页
- forms/main_window.ui：主窗口与导航容器
- app.py：主窗口装配与页面切换入口
- import_page.py：导入页行为层
- layering_page.py：网版页行为层
- routine_page.py：工艺路线页行为层
- prepare_page.py：准备页行为层
- monitor_page.py：监控页或占位页
- resource/：示例 XML、SVG、流程图等资源
- docs/：PRD、DesignDoc、数据模型
- test/：验证脚本


## 必备命令
- 创建 Windows 虚拟环境：python -m venv .venv_windows
- 创建 WSL 虚拟环境：python3 -m venv .venv_linux
- 安装依赖：pip install -r requirement.txt
- 启动前端：python app.py
- 运行验证脚本：python test/workflow_validation_v0.py
- 联调前确认本地后端已启动在 http://127.0.0.1:18000


