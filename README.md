# 产线控制桌面端 V0

## 背景
本仓库用于实现《[PRD]产线控制软件V0》桌面端前端。当前开发主线切换为生产准备模块，对应设计文档为 `docs/[DesignDoc]生产准备B0.0.docx`，后端接口说明为 `docs/后端V0.md`。

当前阶段目标是基于历史工艺路线版本生成并维护生产准备指令集，完成“导入历史版本 → 编辑准备指令 → 校验 → 下发并落库”的最小闭环，覆盖网版、胶浆油墨、物料、设备四类准备指令。

## 关键目录
- `forms/prep_page.ui`：生产准备页面 UI 基准
- `prepare_page.py`：生产准备页面行为层
- `app.py`：主窗口与页面装配入口
- `utilities/backend_client.py`：统一后端客户端封装
- `docs/[DesignDoc]生产准备B0.0.docx`：生产准备设计文档
- `docs/后端V0.md`：后端接口说明
- `forms/main_window.ui`：主窗口 UI

## 启动方法
```bash
python3 -m venv .venv_linux
pip install -r requirement.txt
python app.py
```

Windows 可使用：

```bash
python -m venv .venv_windows
pip install -r requirement.txt
python app.py
```

联调前请确认后端已启动：`http://127.0.0.1:18000`
