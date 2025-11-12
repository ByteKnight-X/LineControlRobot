# pip install langgraph langchain  # 仅用到 LangGraph；后续替换为真智能体时可引入 langchain 等
from typing import TypedDict, List, Literal, Optional, Dict, Any
from datetime import date
from langgraph.graph import StateGraph, END
from pprint import pprint

# =============== 1) 定义工作流的全局 State（可增量合并） ===============
class ProductionOrder(TypedDict, total=False):
    # 用户填写的生产任务单
    deliver_date: str            # 交付日期（ISO 字符串即可）
    sku: str                     # 货号
    part: str                    # 部件（例如：前片 / 后片 / 袖子）
    colorway: str                # 配色（例如：红/黑/白）
    size_range: str              # 码段（例如：S-XL，或 36-44）
    quantity: int                # 数量
    design_doc: str              # 设计文档（路径/URL/ID）
    qa_requirements: str         # 质检要求（自然语言）

class ScreenPlan(TypedDict, total=False):
    # 网版设计方案（示例字段，按你工艺需要扩展）
    screens: List[Dict[str, Any]]   # [{name, ink_color, layer_id, notes}, ...]
    registration_marks: bool        # 是否包含商标

class ProductionList(TypedDict, total=False):
    # 生产清单（工艺规划产出）
    bom: List[Dict[str, Any]]       # 物料清单
    process_routes: List[Dict[str, Any]]  # 工序/设备/参数
    work_steps: List[str]           # 关键作业步骤
    human_resources: Dict[str, int]  # 所需人力资源

class QAList(TypedDict, total=False):
    # 质检清单（质检规划产出）
    checkpoints: List[Dict[str, Any]]  # 检验点、抽检比例、判定标准
    instruments: List[str]             # 量具/治具
    # 新增字段：抽样方法、检验项目、缺陷顶级分类、接收条件
    sampling_method: Dict[str, Any]    # 例如 {"method": "AQL", "level": "II", "sample_rate": "5%"}
    inspection_items: List[Dict[str, Any]]  # [{"name": "...", "method": "...", "sample_rate": "..."}]
    defect_categories: List[Dict[str, Any]] # [{"code":"D1","desc":"色差"}, ...]
    acceptance_criteria: Dict[str, Any] # {"色差": {"metric": "ΔE", "threshold": 2.0}, ...}


class ProductionPreparationCmds(TypedDict, total=False):
    # 生产准备指令与结构化准备项
    # 物料准备：[{ "item": str, "qty": int, "location": Optional[str], "note": Optional[str]}, ...]
    material_prep: List[Dict[str, Any]]
    # 设备准备：[{ "machine": str, "checks": List[str], "params": Dict[str, Any], "note": Optional[str]}, ...]
    equipment_prep: List[Dict[str, Any]]
    # 人员准备：[{ "role": str, "count": int, "shift": Optional[str], "note": Optional[str]}, ...]
    personnel_prep: List[Dict[str, Any]]


class ProductionExectuionCmds(TypedDict, total=False):
    # 执行元数据（按请求新增）
    sku: str                     # 货号
    colorway: str                # 配色
    size_range: str              # 尺码/码段
    quantity: int                # 数量
    planned_start: Optional[str] # 计划开始时间（ISO 格式字符串）
    planned_end: Optional[str]   # 计划结束时间（ISO 格式字符串）
    # 指令序列：结构化列表，允许每条指令包含 step/cmd/params/note 等
    command_sequence: List[Dict[str, Any]]


class WorkflowState(ProductionOrder, ScreenPlan, ProductionList, QAList, ProductionExectuionCmds, ProductionPreparationCmds):
    # 把所有字段“并到一个大状态里”，节点只更新自己负责的键
    pass


# =============== 2) 定义各个“智能体”节点（当前用 dummy） ===============
def screen_design_agent(state: WorkflowState) -> ScreenPlan:
    """
    输入：ProductionOrder (colorway / design_doc / part 等)
    输出：ScreenPlan（网版设计方案）
    """
    # —— dummy 逻辑：基于配色给出若干网版 —— #
    color_tokens = [c.strip() for c in state.get("colorway", "").replace("/", ",").split(",") if c.strip()]
    if not color_tokens:
        color_tokens = ["Black"]

    screens = []
    for idx, color in enumerate(color_tokens, start=1):
        screens.append({
            "name": f"Screen-{idx}",
            "ink_color": color,
            "layer_id": f"{state.get('part','Part')}_L{idx}",
            "notes": f"Auto-generated for {state.get('design_doc','<no-doc>')}"
        })

    return {
        "screens": screens,
        "registration_marks": False
    }


def process_planning_agent(state: WorkflowState) -> ProductionList:
    """
    输入：ScreenPlan
    输出：ProductionList（BOM、工序、作业步骤）
    """
    screens = state.get("screens", [])
    bom = [{"item": f"Ink-{s['ink_color']}", "qty": max(1, state.get("quantity", 100)//500)} for s in screens]
    bom.append({"item": "Substrate", "qty": state.get("quantity", 100)})

    process_routes = [
        {"op": 10, "name": "Frame Prep", "machine": "FrameWasher", "params": {"tension": "25N"}},
        {"op": 20, "name": "Coating/Exposure", "machine": "Coater/UV", "params": {"emulsion": "SBQ"}},
        {"op": 30, "name": "Registration", "machine": "RegTable", "params": {"marks": state.get("registration_marks", True)}},
        {"op": 40, "name": "Printing", "machine": "ScreenPress", "params": {"passes": 1}},
        {"op": 50, "name": "Curing", "machine": "TunnelDryer", "params": {"temp": "160C", "time_s": 45}},
    ]

    work_steps = [f"Print with {len(screens)} screens", "Dry & cure", "Final inspection"]
    return {
        "bom": bom,
        "process_routes": process_routes,
        "work_steps": work_steps
    }


def qa_planning_agent(state: WorkflowState) -> QAList:
    """
    输入：qa_requirements（自然语言）
    输出：QAList（检验点、抽检比例、判定标准等）
    """
    req = (state.get("qa_requirements") or "外观/色差/尺寸/附着力")
    checkpoints = [
        {"name": "外观缺陷", "method": "目检", "sample_rate": "AQL 1.5", "criteria": "无明显脏污、漏印、重影"},
        {"name": "色差",   "method": "比色卡/分光", "sample_rate": "每批抽5%", "criteria": "ΔE ≤ 2.0"},
        {"name": "尺寸",   "method": "卡尺/样板", "sample_rate": "每码段抽2件", "criteria": "±1.5mm"},
        {"name": "附着力", "method": "百格/胶带", "sample_rate": "每色每班1次", "criteria": "0-1级"},
    ]
    instruments = ["分光测色仪", "卡尺", "百格刀", "放大镜"]

    # 抽样方法（示例，可根据 req 转换）
    sampling_method = {"method": "AQL", "level": "II", "sample_rate_policy": "参照 AQL 表；一般按批次抽样"}

    # 检验项目（结构化）
    inspection_items = [
        {"name": "外观", "method": "目检", "sample_rate": "AQL 1.5"},
        {"name": "色差", "method": "分光测色", "sample_rate": "5%/批"},
        {"name": "尺寸", "method": "卡尺/样板", "sample_rate": "按码段抽样"},
        {"name": "附着力", "method": "百格试验", "sample_rate": "每色每班1次"},
    ]

    # 缺陷顶级分类（示例）
    defect_categories = [
        {"code": "D1", "name": "功能性缺陷", "examples": ["未印/断开", "尺寸超差"]},
        {"code": "D2", "name": "外观缺陷", "examples": ["污点", "褪色", "印痕"]},
        {"code": "D3", "name": "工艺缺陷", "examples": ["叠印", "移位"]},
    ]

    # 接收条件（示例映射到检验项目）
    acceptance_criteria = {
        "色差": {"metric": "ΔE", "threshold": 2.0},
        "尺寸": {"metric": "mm", "tolerance": "±1.5"},
        "附着力": {"method": "百格", "max_grade": 1},
        "外观": {"allowable": ["轻微毛糙"], "reject_if": ["明显污点", "漏印"]},
    }

    return {
        "checkpoints": checkpoints,
        "instruments": instruments,
        "sampling_method": sampling_method,
        "inspection_items": inspection_items,
        "defect_categories": defect_categories,
        "acceptance_criteria": acceptance_criteria,
    }


def scheduling_agent(state: WorkflowState) -> (ProductionExectuionCmds, ProductionExectuionCmds):
    """
    输入：ProductionList + QAList
    输出：ScheduleCommands（准备/执行指令）
    """
    qty = state.get("quantity", 100)
    part = state.get("part", "Part")
    screens = state.get("screens", [])

    preparation = [
        "校核设计文档与最新网版方案一致",
        f"准备网版：{', '.join(s['name'] for s in screens) or 'N/A'}",
        "确认油墨、基材到位（参考 BOM）",
        "确认量具/治具到位（参考质检清单）",
    ]
    execution = [
        "按工序路线开线生产",
        "关键工位首件确认并记录",
        "过程抽检与结果记录（参考质检清单）",
        f"完工入库并回写批次（部件：{part}，数量：{qty}）",
    ]
    return {
        "preparation_cmds": preparation,
        "execution_cmds": execution,
        "hints": "如需多产线并行或跨班次排程，可在此节点接入 APS/排产算法。"
    }


# =============== 3) 用 LangGraph 编排节点/边 ===============
def build_graph():
    graph = StateGraph(WorkflowState)

    # 注册节点
    graph.add_node("screen_design", screen_design_agent)
    graph.add_node("process_planning", process_planning_agent)
    graph.add_node("qa_planning", qa_planning_agent)
    graph.add_node("scheduling", scheduling_agent)

    # 入口：先做网版方案
    graph.set_entry_point("screen_design")
    # 顺序编排（简单串行：网版方案 -> 工艺规划 -> 质检规划 -> 排程）
    # 也可以把 qa_planning 并到 process_planning 前后，这里示范最直观的串行
    graph.add_edge("screen_design", "process_planning")
    graph.add_edge("process_planning", "qa_planning")
    graph.add_edge("qa_planning", "scheduling")
    graph.add_edge("scheduling", END)

    return graph.compile()


# =============== 4) 演示调用（示例输入） ===============
if __name__ == "__main__":
    app = build_graph()
    input_state: WorkflowState = {
        "deliver_date": "2025-11-20",
        "sku": "TP-8801",
        "part": "FrontPanel",
        "colorway": "Red/Black/White",
        "size_range": "S-XL",
        "quantity": 1200,
        "design_doc": "s3://designs/8Pro_OneItem.svg",
        "qa_requirements": "外观、色差、尺寸和附着力需重点关注"
    }
    result = app.invoke(input_state)
    
    # 你可以把 result 中的各字段落盘/下发到系统：
    pprint(result)


