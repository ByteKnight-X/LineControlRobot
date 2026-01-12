"""
Contains global constants for the application.
"""

STYLE = (
    "QMainWindow {"
    "    background: #f7f8fa;"
    "}"
    "QWidget#stackedRight {"
    "    border: 1px solid #e0e0e0;"
    "    background: #ffffff;"
    "}"
    "QPushButton {"
    "    background: transparent;"
    "    border: none;"
    "    padding: 10px 18px;"
    "    font-size: 15px;"
    "    color: #333;"
    "    border-radius: 6px;"
    "}"
    "QPushButton:hover {"
    "    background: #e3e8ee;"
    "}"
    "QPushButton:pressed {"
    "    background: #cfd8dc;"
    "}"
    "QPushButton[styleSheet*=\"font-weight: bold;\"] {"
    "    color: #1976d2;"
    "    background: #e3e8ee;"
    "}"
)


DEFAULT_ROUTINE_LIST = """
\n
工序流程单：
1. 涂抹处理剂（网版ID:0, 层厚: 0.1mm, 刮印次数: 2）
2. 打底胶浆（网版ID:1, 层厚: 0.2mm, 刮印次数: 3）
3. 印刷护眼（网版ID:2, 层厚: 0.1mm, 刮印次数: 2， 色号：1234#）
\n
"""

DEFAULT_MATERIAL_LIST = """
\n
物料清单:
1. 处理剂 - 型号A - 数量: 5L
2. 打底胶浆 - 型号B - 数量: 10L
3. 油墨 - 色号: 1234# - 数量: 8L
4. 裁片 - A - 1000片
\n
"""

DEFAULT_TALENT_LIST = """
\n
人才清单:
1. 技工 x 1
2. 普工 x 2
\n
"""


DEFAULT_ROUTINE_LISTS = DEFAULT_ROUTINE_LIST + "*" * 20 + DEFAULT_MATERIAL_LIST + "*" * 20 + DEFAULT_TALENT_LIST


DEFAULT_FEEDING_ROBOT_INSTRUCTIONS = """
\n
任务类型: 上料机器人操作指令
任务描述：将上料区域的4只鞋面放置于托盘上。托盘每次能放2只鞋面。
设计图案：resource\layers\OneItem_1.svg
速度：80%
\n
"""

DEFAULT_PRITING_0_ROBOT_INSTRUCTIONS = """
\n
工作站ID: 0
任务类型: 丝印工作站指令
任务描述：印刷4只鞋面图案
设计图案：resource\layers\OneItem_1.svg
层厚: 0.1mm
次数：
刮印次数：2
\n
"""

DEFAULT_PRITING_1_ROBOT_INSTRUCTIONS = """
\n
工作站ID: 1
任务类型: 丝印工作站指令
任务描述：印刷4只鞋面图案
设计图案：resource\layers\OneItem_1.svg
层厚: 0.1mm
次数：
刮印次数：2
\n
"""

DEFAULT_DRYING_1_ROBOT_INSTRUCTIONS = """
\n
工作站ID: 1
任务类型: 烘干工作站指令
任务描述：基于以下参数烘烤4只鞋面
烘烤温度: 80℃
烘烤时间: 120s
\n
"""

DEFAULT_EQUIPMENT_INSTRUCTION_LISTS = DEFAULT_FEEDING_ROBOT_INSTRUCTIONS + "#" * 20 + DEFAULT_PRITING_0_ROBOT_INSTRUCTIONS + "*" * 20 + DEFAULT_PRITING_1_ROBOT_INSTRUCTIONS + "*" * 20 + DEFAULT_DRYING_1_ROBOT_INSTRUCTIONS

DEFAULT_MESH_PARAMS = {
    "0_处理剂": {
        "material": "polyester",        # 网纱材质
        "model": "PET-90T-48",          # 示例型号
        "wire_diameter": 55,            # 线径(µm)
        "pulling_method": "斜拉",       # 拉线方法：气动拉网机
        "pulling_angle": 22.5,          # 拉线/装网角度
        "mesh_count": 90,               # 目数(T/cm)
        "tension": 25.0,                # 张力(N/cm)
        "frame_model": 13245,       # 外框尺寸 (W, H)
        "mesh_thickness": 80,           # 网纱厚度
    },
    "1_胶浆": {
        "material": "polyester",
        "model": "PET-77T-55",
        "wire_diameter": 62,
        "pulling_method": "斜拉",
        "pulling_angle": 22.5,
        "mesh_count": 77,
        "tension": 28.0,
        "frame_model": 13245,
        "mesh_thickness": 90,
    },
    "2_深蓝": {        
        "material": "polyester",
        "model": "PET-77T-55",
        "wire_diameter": 62,
        "pulling_method": "斜拉",
        "pulling_angle": 22.5,
        "mesh_count": 77,
        "tension": 28.0,
        "frame_model": 13245,
        "mesh_thickness": 90,
    },
    "3_深绿": {
        "material": "polyester",
        "model": "PET-77T-55",
        "wire_diameter": 62,
        "pulling_method": "斜拉",
        "pulling_angle": 22.5,
        "mesh_count": 77,
        "tension": 28.0,
        "frame_model": 13245,
        "mesh_thickness": 90,
    },
    "4_浅蓝": {
        "material": "polyester",
        "model": "PET-77T-55",
        "wire_diameter": 62,
        "pulling_method": "斜拉",
        "pulling_angle": 22.5,
        "mesh_count": 77,
        "tension": 28.0,
        "frame_model": 13245,
        "mesh_thickness": 90,
    },
    "5_粉色": {
        "material": "polyester",
        "model": "PET-77T-55",
        "wire_diameter": 62,
        "pulling_method": "斜拉",
        "pulling_angle": 22.5,
        "mesh_count": 77,
        "tension": 28.0,
        "frame_model": 13245,
        "mesh_thickness": 90,
    },
    "6_浅绿": {
        "material": "polyester",
        "model": "PET-77T-55",
        "wire_diameter": 62,
        "pulling_method": "斜拉",
        "pulling_angle": 22.5,
        "mesh_count": 77,
        "tension": 28.0,
        "frame_model": 13245,
        "mesh_thickness": 90,
    }
}
