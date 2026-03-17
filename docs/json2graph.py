# sql2graph.py
import sys
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Tuple

from PyQt5.QtWidgets import (
    QApplication,
    QAction,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import xml_flow_viewer as viewer

NS = "http://graphml.graphdrawing.org/xmlns"
G = "{" + NS + "}"
ET.register_namespace("g", NS)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_params(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return {}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": value}
    return value


def normalize_route_data(
    header: Dict[str, Any],
    loops: List[Dict[str, Any]],
    steps: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    normalized_header = dict(header)

    normalized_loops: List[Dict[str, Any]] = []
    for loop in loops:
        item = dict(loop)
        item["loop_index"] = _to_int(item.get("loop_index"), 0)
        item["loop_count"] = _to_int(item.get("loop_count"), 1)
        normalized_loops.append(item)

    normalized_loops.sort(key=lambda item: (item["loop_index"], item.get("loop_id", "")))

    # build a lookup map from loop_id -> loop_index so steps can inherit loop_index
    loop_index_map: Dict[str, int] = {l.get("loop_id"): l.get("loop_index", 0) for l in normalized_loops}

    normalized_steps: List[Dict[str, Any]] = []
    for step in steps:
        item = dict(step)
        # prefer explicit loop_index on step if present; otherwise look up from loop table
        explicit_li = step.get("loop_index")
        if explicit_li is not None:
            item["loop_index"] = _to_int(explicit_li, 0)
        else:
            item["loop_index"] = _to_int(loop_index_map.get(step.get("loop_id")), 0)
        item["node_index"] = _to_int(item.get("node_index"), 0)
        item["params"] = _normalize_params(item.get("params", {}))
        normalized_steps.append(item)

    normalized_steps.sort(
        key=lambda item: (item["loop_index"], item["node_index"], item.get("node_id", ""))
    )

    return normalized_header, normalized_loops, normalized_steps


def parse_json(json_path: Path) -> Tuple[Dict, List[Dict], List[Dict]]:
    text = json_path.read_text(encoding="utf-8")
    data = json.loads(text)

    header = data.get("process_route_header") or {}
    loops = data.get("process_route_loop_line") or []
    steps = data.get("process_route_loop_step") or []

    return normalize_route_data(header, loops, steps)


def write_graphml_from_data(
    header: Dict,
    loops: List[Dict],
    steps: List[Dict],
    out_xml: Path,
) -> None:
    # Normalize & sort so loops are left->right by loop_index
    header, loops, steps = normalize_route_data(header, loops, steps)

    # build lookup and grouping to write nodes grouped by loop_index and node_index
    from collections import defaultdict

    nodes_by_loop: Dict[str, List[Dict]] = defaultdict(list)
    for s in steps:
        nodes_by_loop[s.get("loop_id", "")].append(s)

    # ensure nodes inside each loop are sorted by node_index, then node_id
    for lid, lst in nodes_by_loop.items():
        lst.sort(key=lambda r: (r.get("node_index", 0), r.get("node_id", "")))

    # loop order by loop_index, then loop_id
    loop_order = [l["loop_id"] for l in sorted(loops, key=lambda x: (x.get("loop_index", 0), x.get("loop_id", "")))]

    root = ET.Element(G + "graphml")
    keys = {
        "k_loop_id": "loop_id",
        "k_loop_index": "loop_index",
        "k_node_index": "node_index",
        "k_node_type": "node_type",
        "k_instruction": "instruction",
        "k_params": "params",
        "k_edge_type": "edge_type",
        "k_loop_count": "loop_count",
    }
    for kid, name in keys.items():
        ET.SubElement(root, G + "key", id=kid, attrib={"attr.name": name})

    graph = ET.SubElement(
        root,
        G + "graph",
        id=header.get("process_route_id", "graph"),
        edgedefault="directed",
    )

    # Write nodes grouped by loop, and within each loop by node_index
    for loop_id in loop_order:
        for row in nodes_by_loop.get(loop_id, []):
            node = ET.SubElement(graph, G + "node", id=row["node_id"])
            values = {
                "k_loop_id": row.get("loop_id", ""),
                "k_loop_index": str(row.get("loop_index", 0)),
                "k_node_index": str(row.get("node_index", 0)),
                "k_node_type": row.get("node_type", "") or "",
                "k_instruction": row.get("instruction", "") or "",
            }
            for kid, value in values.items():
                data = ET.SubElement(node, G + "data", key=kid)
                data.text = value

            params_value = row.get("params", {}) or {}
            if isinstance(params_value, (dict, list)):
                params_text = json.dumps(params_value, ensure_ascii=False)
            else:
                params_text = str(params_value)

            data_params = ET.SubElement(node, G + "data", key="k_params")
            data_params.text = params_text

    # Build edges using same loop ordering (within-loop forward, bridge between loops, loop edges)
    edges = []

    for loop_id in loop_order:
        node_list = [n["node_id"] for n in nodes_by_loop.get(loop_id, [])]
        for a, b in zip(node_list, node_list[1:]):
            edges.append((f"e_fw_{a}_{b}", a, b, "forward", None))

    for cur_loop, next_loop in zip(loop_order, loop_order[1:]):
        cur_nodes = [n["node_id"] for n in nodes_by_loop.get(cur_loop, [])]
        next_nodes = [n["node_id"] for n in nodes_by_loop.get(next_loop, [])]
        if cur_nodes and next_nodes:
            edges.append((f"e_bridge_{cur_nodes[-1]}_{next_nodes[0]}", cur_nodes[-1], next_nodes[0], "forward", None))

    for loop in loops:
        if loop.get("loop_count", 1) > 1:
            src = loop.get("exit_node_id")
            tgt = loop.get("entry_node_id")
            if src and tgt:
                edges.append((f"e_loop_{loop['loop_id']}", src, tgt, "loop", str(loop["loop_count"])))

    valid_node_ids = {s["node_id"] for s in steps}
    for eid, src, tgt, etype, lcount in edges:
        if src not in valid_node_ids or tgt not in valid_node_ids:
            continue
        e = ET.SubElement(graph, G + "edge", id=eid, source=src, target=tgt)
        dt = ET.SubElement(e, G + "data", key="k_edge_type")
        dt.text = etype
        if lcount is not None:
            dl = ET.SubElement(e, G + "data", key="k_loop_count")
            dl.text = lcount

    tree = ET.ElementTree(root)
    tree.write(str(out_xml), encoding="utf-8", xml_declaration=True)


def export_json_from_data(out_json: Path, header: Dict, loops: List[Dict], steps: List[Dict]) -> None:
    # Normalize for consistent ordering, but do NOT write loop_index into each step in output.
    header, loops, steps = normalize_route_data(header, loops, steps)

    loops_out = []
    for loop in loops:
        item = dict(loop)
        item["loop_index"] = _to_int(item.get("loop_index"), 0)
        item["loop_count"] = _to_int(item.get("loop_count"), 1)
        loops_out.append(item)

    steps_out = []
    for step in steps:
        # preserve original metadata fields where present, but do not include loop_index
        item = {k: v for k, v in step.items() if k != "loop_index"}
        # normalize node_index and params
        item["node_index"] = _to_int(item.get("node_index"), 0)
        item["params"] = _normalize_params(item.get("params", {}))
        steps_out.append(item)

    output = {
        "process_route_header": dict(header),
        "process_route_loop_line": loops_out,
        "process_route_loop_step": steps_out,
    }
    out_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


def rebind_node_editors(window, header, loops, steps_list, out_xml):
    for _, item in window.node_items.items():
        try:
            item.clicked.disconnect()
        except Exception:
            pass
        item.clicked.connect(
            lambda node_obj=item.node, s=steps_list, h=header, ls=loops, ox=out_xml, w=window:
            open_node_editor(w, node_obj, s, h, ls, ox, w)
        )


def open_node_editor(parent, node_obj, steps_list, header, loops, out_xml, window):
    dlg = QDialog(parent)
    dlg.setWindowTitle(f"编辑节点 {node_obj.node_id}")
    layout = QFormLayout(dlg)

    instr_edit = QLineEdit(node_obj.instruction or "")
    if isinstance(node_obj.params, dict):
        params_str = json.dumps(node_obj.params, ensure_ascii=False, indent=2)
    elif isinstance(node_obj.params, str) and node_obj.params.strip():
        params_str = node_obj.params
    else:
        params_str = "{}"

    params_edit = QTextEdit(params_str)

    layout.addRow(QLabel("instruction:"), instr_edit)
    layout.addRow(QLabel("params (JSON):"), params_edit)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    layout.addRow(buttons)

    def on_ok():
        instruction = instr_edit.text().strip()
        params_text = params_edit.toPlainText().strip() or "{}"

        try:
            parsed_params = json.loads(params_text)
        except Exception as exc:
            QMessageBox.critical(dlg, "JSON 解析错误", f"params 不是合法 JSON：\n{exc}")
            return

        node_obj.instruction = instruction
        node_obj.params = parsed_params

        for step in steps_list:
            if step.get("node_id") == node_obj.node_id:
                step["instruction"] = instruction
                step["params"] = parsed_params
                break

        write_graphml_from_data(header, loops, steps_list, out_xml)
        window.load_xml(out_xml)
        rebind_node_editors(window, header, loops, steps_list, out_xml)
        dlg.accept()

    buttons.accepted.connect(on_ok)
    buttons.rejected.connect(dlg.reject)
    dlg.exec_()


def open_loops_editor(parent, header, loops, steps_list, out_xml, window):
    dlg = QDialog(parent)
    dlg.setWindowTitle("编辑循环 (loop_count)")
    layout = QVBoxLayout(dlg)

    spin_map = {}
    for loop in sorted(loops, key=lambda item: (_to_int(item.get("loop_index"), 0), item.get("loop_id", ""))):
        row_widget = QWidget()
        row_layout = QFormLayout(row_widget)

        label = QLabel(f"{loop['loop_id']} (index {loop['loop_index']})")
        spin = QSpinBox()
        spin.setRange(0, 999)
        spin.setValue(_to_int(loop.get("loop_count"), 1))

        row_layout.addRow(label, spin)
        layout.addWidget(row_widget)
        spin_map[loop["loop_id"]] = spin

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    layout.addWidget(buttons)

    def on_ok():
        for loop in loops:
            loop["loop_count"] = int(spin_map[loop["loop_id"]].value())

        write_graphml_from_data(header, loops, steps_list, out_xml)
        window.load_xml(out_xml)
        rebind_node_editors(window, header, loops, steps_list, out_xml)
        dlg.accept()

    buttons.accepted.connect(on_ok)
    buttons.rejected.connect(dlg.reject)
    dlg.exec_()


def main(argv: List[str]) -> int:
    if len(argv) > 1:
        json_path = Path(argv[1])
    else:
        json_path = Path(__file__).with_name("flow_v2_aug.json")

    if not json_path.exists():
        print("JSON file not found:", json_path)
        return 2

    header, loops, steps = parse_json(json_path)

    out_xml = Path(__file__).with_name("flow_from_json.xml")
    write_graphml_from_data(header, loops, steps, out_xml)

    app = QApplication(sys.argv)
    win = viewer.FlowWindow(out_xml)

    save_action = QAction("保存 JSON", win)

    def on_save():
        out_json = Path(__file__).with_name("flow_v2_rev.json")
        export_json_from_data(out_json, header, loops, steps)
        QMessageBox.information(win, "已保存", f"导出到: {out_json}")

    save_action.triggered.connect(on_save)

    edit_loops_action = QAction("编辑循环", win)
    edit_loops_action.triggered.connect(
        lambda: open_loops_editor(win, header, loops, steps, out_xml, win)
    )

    toolbar = win.addToolBar("JSON Controls")
    toolbar.addAction(edit_loops_action)
    toolbar.addAction(save_action)

    rebind_node_editors(win, header, loops, steps, out_xml)

    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))