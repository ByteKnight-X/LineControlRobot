from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import Qt, QRectF, QTimer, QDateTime, QPointF
from PyQt5.QtGui import QPen, QBrush, QColor, QFont, QPainter, QPolygonF
from PyQt5.QtWidgets import (
    QGraphicsScene, QGraphicsRectItem, QGraphicsSimpleTextItem, 
    QTableWidgetItem, QHeaderView, QGraphicsLineItem, QGraphicsPolygonItem
)
from pathlib import Path
import xml.etree.ElementTree as ET


class MonitorPage(QtWidgets.QWidget):
    """Production monitoring page"""

    def __init__(self, controller=None):
        super().__init__()
        uic.loadUi(str(Path(__file__).resolve().parent / "forms" / "monitor_page.ui"), self)
        self.controller = controller
        self.setup_ui()
    
    def setup_ui(self) -> None:
        """ Setup ui for monitoring page """
        # Setup stretch factors for main layout
        layout = self.findChild(QtWidgets.QHBoxLayout, "mainLayout")
        if layout:
            layout.setStretch(0, 10)  # frameCanvas
            layout.setStretch(1, 1)   # frameControls
        
        # Setup layout
        self._init_line_view()
        self._setup_tables()
        self._connect_signals()
        
        # Periodic refresh (controller may update context from backend)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(2000)  # 2s refresh
        self.refresh()

    def _init_line_view(self) -> None:
        """ Initialize QGraphicsScene for digital twin view (lineMimicView). """
        self._scene = QGraphicsScene(self)
        self.lineMimicView.setScene(self._scene)
        self.lineMimicView.setRenderHint(QPainter.Antialiasing)
        self._font = QFont()
        self._font.setPointSize(9)
        self._build_mimic_template()

    def _build_mimic_template(self) -> None:
        """ Render production line topology from flow_v2.xml or context route. """
        self._scene.clear()
        
        # Try to get route from controller context
        ctx = getattr(self.controller, "context", {}) if self.controller else {}
        route_xml = ctx.get("route")
        
        # Fallback to local flow_v2.xml
        if not route_xml:
            xml_path = Path(__file__).resolve().parent / "resource" / "flow_v2.xml"
            if xml_path.exists():
                route_xml = xml_path.read_text(encoding="utf-8")
            else:
                raise ValueError("No flow chart generated.")
        
        # Parse XML
        try:
            root = ET.fromstring(route_xml)
        except ET.ParseError:
            raise ValueError("Failed to parse flow chart.")
        
        ns = {"gml": "http://graphml.graphdrawing.org/xmlns"}
        graph = root.find("gml:graph", ns)
        if graph is None:
            raise ValueError("failed to identify nodes.")
        
        # Extract nodes and edges
        nodes_data = {}  # node_id -> {deviceId, deviceType, instruction}
        edges_data = []  # list of {source, target, edgeType, loopCount}
        
        for node in graph.findall("gml:node", ns):
            nid = node.get("id")
            data = {}
            for d in node.findall("gml:data", ns):
                key = d.get("key")
                text = d.text.strip() if d.text else ""
                if key == "k_deviceId":
                    data["deviceId"] = text
                elif key == "k_deviceType":
                    data["deviceType"] = text
                elif key == "k_instruction":
                    data["instruction"] = text
            nodes_data[nid] = data
        
        for edge in graph.findall("gml:edge", ns):
            src = edge.get("source")
            tgt = edge.get("target")
            etype = None
            lcount = None
            for d in edge.findall("gml:data", ns):
                key = d.get("key")
                if key == "k_edgeType":
                    etype = d.text.strip() if d.text else None
                elif key == "k_loopCount":
                    lcount = int(d.text.strip()) if d.text else None
            edges_data.append({
                "source": src,
                "target": tgt,
                "edgeType": etype,
                "loopCount": lcount
            })
        
        # Render nodes and edges
        self._render_topology(nodes_data, edges_data)

    def _render_topology(self, nodes_data: dict, edges_data: list) -> None:
        """Render nodes in snake-like layout with forward/loop edges."""
        # Layout parameters
        node_w, node_h = 140, 80
        gap_x = 60
        gap_y = 100
        start_x = 40
        start_y = 40
        max_per_row = 6
        
        # Color mapping
        color_map = {
            "上料工作站": "#4CAF50",
            "丝印工作站": "#2196F3",
            "烘干机": "#FF9800",
            "质检工作站": "#9C27B0",
            "下料工作站": "#E91E63"
        }
        
        # Position nodes in snake-like layout
        node_items = {}
        node_positions = {}
        ordered_ids = list(nodes_data.keys())
        
        # Precompute node row/col
        node_row_col = {}  # node_id -> (row, col)
        
        for i, nid in enumerate(ordered_ids):
            row = i // max_per_row
            col = i % max_per_row
            node_row_col[nid] = (row, col)
            
            # Alternate direction for odd/even rows (snake pattern)
            if row % 2 == 0:
                x = start_x + col * (node_w + gap_x)
            else:
                x = start_x + (max_per_row - 1 - col) * (node_w + gap_x)
            
            y = start_y + row * (node_h + gap_y)
            
            # Create node rectangle
            rect = QRectF(x, y, node_w, node_h)
            dtype = nodes_data[nid].get("deviceType", "")
            color = color_map.get(dtype, "#4A90E2")
            
            node_item = QGraphicsRectItem(rect)
            node_item.setPen(QPen(QColor("#607d8b"), 2))
            node_item.setBrush(QBrush(QColor(color)))
            node_item.setData(0, nid)  # Store node_id for click events
            self._scene.addItem(node_item)
            
            node_items[nid] = node_item
            node_positions[nid] = rect.center()
            
            # Display device type as label
            label = QGraphicsSimpleTextItem(dtype, node_item)
            label_font = QFont(self._font)
            label_font.setPointSize(10)
            label_font.setBold(True)
            label.setFont(label_font)
            label.setBrush(QBrush(QColor("#ffffff")))
            label_rect = label.boundingRect()
            label.setPos(
                (node_w - label_rect.width()) / 2,
                (node_h - label_rect.height()) / 2
            )
        
        # Separate forward and loop edges
        forward_edges = [e for e in edges_data if e["edgeType"] == "forward"]
        loop_edges = [e for e in edges_data if e["edgeType"] == "loop"]
        
        # Build forward/prev adjacency lists
        fwd_next = {}   # node_id -> next_node_id
        fwd_prev = {}   # node_id -> prev_node_id
        for e in forward_edges:
            s, t = e["source"], e["target"]
            fwd_next[s] = t
            fwd_prev[t] = s
        
        # Draw forward edges
        for e in forward_edges:
            src_id = e["source"]
            tgt_id = e["target"]
            if src_id not in node_positions or tgt_id not in node_positions:
                continue
            
            src_rect = node_items[src_id].rect()
            tgt_rect = node_items[tgt_id].rect()
            
            # Use precomputed row/col
            src_row, src_col = node_row_col[src_id]
            tgt_row, tgt_col = node_row_col[tgt_id]
            
            # Complete arrow connection logic
            if src_row == tgt_row:
                # Same row: need to check direction
                if src_row % 2 == 0:
                    # Forward row: left→right
                    p1 = QPointF(src_rect.right(), src_rect.center().y())
                    p2 = QPointF(tgt_rect.left(), tgt_rect.center().y())
                else:
                    # Backward row: right→left
                    p1 = QPointF(src_rect.left(), src_rect.center().y())
                    p2 = QPointF(tgt_rect.right(), tgt_rect.center().y())
            else:
                # Different rows: vertical connection
                p1 = QPointF(src_rect.center().x(), src_rect.bottom())
                p2 = QPointF(tgt_rect.center().x(), tgt_rect.top())
            
            self._draw_arrow(p1, p2, QColor("#333"), 3)
        
        # Complete loop path finding
        loop_groups = []
        visited_loops = set()
        
        for e in loop_edges:
            src = e["source"]
            tgt = e["target"]
            lcount = e["loopCount"] or 1
            
            if (src, tgt) in visited_loops:
                continue
            visited_loops.add((src, tgt))
            
            # From tgt to src
            path_nodes = []
            cur = tgt
            safety = 0
            max_steps = len(nodes_data) + 5
            
            while cur is not None and safety < max_steps:
                path_nodes.append(cur)
                if cur == src:
                    break
                cur = fwd_next.get(cur)
                safety += 1
            
            # If not found, try reverse
            if path_nodes and path_nodes[-1] != src:
                path_nodes = []
                cur = src
                safety = 0
                while cur is not None and safety < max_steps:
                    path_nodes.append(cur)
                    if cur == tgt:
                        break
                    cur = fwd_prev.get(cur)
                    safety += 1
                # Reverse path
                path_nodes.reverse()
            
            # Backup plan
            if not path_nodes or path_nodes[0] != tgt or path_nodes[-1] != src:
                path_nodes = [tgt, src]
            
            loop_groups.append({"nodes": path_nodes, "loopCount": lcount})
        
        # Draw loop group rectangles
        for group in loop_groups:
            node_ids = group["nodes"]
            lcount = group["loopCount"]
            rects = [node_items[nid].rect() for nid in node_ids if nid in node_items]
            
            if not rects:
                continue
            
            # Calculate bounding box
            left = min(r.left() for r in rects) - 20
            top = min(r.top() for r in rects) - 20
            right = max(r.right() for r in rects) + 20
            bottom = max(r.bottom() for r in rects) + 20
            
            loop_rect = QRectF(left, top, right - left, bottom - top)
            loop_box = QGraphicsRectItem(loop_rect)
            loop_box.setPen(QPen(QColor("#E91E63"), 3, Qt.DashLine))
            loop_box.setBrush(QBrush(Qt.transparent))
            self._scene.addItem(loop_box)
            
            # Add loop count label
            label = QGraphicsSimpleTextItem(f"×{lcount}")
            label.setBrush(QBrush(QColor("#E91E63")))
            label_font = QFont(self._font)
            label_font.setPointSize(16)
            label_font.setBold(True)
            label.setFont(label_font)
            label_rect = label.boundingRect()
            label.setPos(
                loop_rect.right() - label_rect.width() - 10,
                loop_rect.top() - label_rect.height() - 5
            )
            self._scene.addItem(label)
        
        # Set scene bounds
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))

    def _find_loop_path(self, start: str, end: str, forward_edges: list) -> list:
        """Find path from start to end following forward edges."""
        # Build forward graph
        fwd_next = {e["source"]: e["target"] for e in forward_edges}
        
        path = []
        current = start
        visited = set()
        max_steps = len(fwd_next) + 5
        
        while current and current not in visited and len(path) < max_steps:
            path.append(current)
            if current == end:
                return path
            visited.add(current)
            current = fwd_next.get(current)
        
        return path if end in path else [start, end]

    def _draw_arrow(self, p1: QPointF, p2: QPointF, color: QColor, width: int) -> None:
        """Draw straight line with arrow head from p1 to p2."""
        # Draw line
        line = QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
        line.setPen(QPen(color, width))
        self._scene.addItem(line)
        
        # Draw arrow head
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = (dx**2 + dy**2)**0.5
        
        if length < 1e-6:
            return
        
        # Unit direction vector
        ux = dx / length
        uy = dy / length
        
        # Arrow head parameters
        arrow_size = 12
        
        # Calculate arrow points
        left_x = p2.x() - arrow_size * (ux * 0.866 + uy * 0.5)
        left_y = p2.y() - arrow_size * (uy * 0.866 - ux * 0.5)
        right_x = p2.x() - arrow_size * (ux * 0.866 - uy * 0.5)
        right_y = p2.y() - arrow_size * (uy * 0.866 + ux * 0.5)
        
        arrow_head = QPolygonF([
            p2,
            QPointF(left_x, left_y),
            QPointF(right_x, right_y)
        ])
        
        arrow_item = QGraphicsPolygonItem(arrow_head)
        arrow_item.setPen(QPen(color, 1))
        arrow_item.setBrush(QBrush(color))
        self._scene.addItem(arrow_item)

    def _setup_tables(self) -> None:
        """Configure table views with proper column widths and styling."""
        # Tab 1: Events table (tblEvents)
        if hasattr(self, 'tblEvents'):
            self.tblEvents.setColumnCount(5)
            self.tblEvents.setHorizontalHeaderLabels([
                "优先级", "时间", "来源工位", "简述", "确认"
            ])
            self.tblEvents.horizontalHeader().setStretchLastSection(True)
            self.tblEvents.setColumnWidth(0, 50)
            self.tblEvents.setColumnWidth(1, 150)
            self.tblEvents.setColumnWidth(2, 100)
            self.tblEvents.setColumnWidth(3, 300)
            self.tblEvents.setColumnWidth(4, 100)
            self.tblEvents.setAlternatingRowColors(True)
            self.tblEvents.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.tblEvents.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.tblEvents.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        # Tab 3: Stations table (tblStations)
        if hasattr(self, 'tblStations'):
            self.tblStations.setColumnCount(6)
            self.tblStations.setHorizontalHeaderLabels([
                "工站ID", "工站名称", "状态", "工艺", "托盘", "备注"
            ])
            self.tblStations.horizontalHeader().setStretchLastSection(True)
            self.tblStations.setColumnWidth(0, 80)
            self.tblStations.setColumnWidth(1, 120)
            self.tblStations.setColumnWidth(2, 80)
            self.tblStations.setColumnWidth(3, 80)
            self.tblStations.setColumnWidth(4, 60)
            self.tblStations.setAlternatingRowColors(True)
            self.tblStations.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.tblStations.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.tblStations.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        # Tab 4: Alarms table (tblAlarms)
        if hasattr(self, 'tblAlarms'):
            self.tblAlarms.setColumnCount(5)
            self.tblAlarms.setHorizontalHeaderLabels([
                "级别", "时间戳", "工站", "消息", "确认"
            ])
            self.tblAlarms.horizontalHeader().setStretchLastSection(True)
            self.tblAlarms.setColumnWidth(0, 60)
            self.tblAlarms.setColumnWidth(1, 150)
            self.tblAlarms.setColumnWidth(2, 100)
            self.tblAlarms.setColumnWidth(3, 400)
            self.tblAlarms.setColumnWidth(4, 80)
            self.tblAlarms.setAlternatingRowColors(True)
            self.tblAlarms.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.tblAlarms.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.tblAlarms.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

    def _connect_signals(self) -> None:
        """Wire UI signals to handlers."""
        if hasattr(self, 'tblEvents'):
            try:
                self.tblEvents.cellClicked.disconnect()
            except Exception:
                pass
            self.tblEvents.cellClicked.connect(self.on_event_table_clicked)

        if hasattr(self, 'btnStart'):
            self.btnStart.clicked.connect(self.on_start)
        if hasattr(self, 'btnPause'):
            self.btnPause.clicked.connect(self.on_pause)
        if hasattr(self, 'btnStop'):
            self.btnStop.clicked.connect(self.on_stop)
        if hasattr(self, 'btnReset'):
            self.btnReset.clicked.connect(self.on_reset)
        
        if hasattr(self, 'btnApplyProfile'):
            self.btnApplyProfile.clicked.connect(self.on_apply_profile)
        
        if hasattr(self, 'btnAckAlarm'):
            self.btnAckAlarm.clicked.connect(self.on_ack_alarm)
        if hasattr(self, 'btnMuteAlarm'):
            self.btnMuteAlarm.clicked.connect(self.on_mute_alarm)
        if hasattr(self, 'btnExportAlarm'):
            self.btnExportAlarm.clicked.connect(self.on_export_alarm)

        if hasattr(self, 'btnLocateBottleneck'):
            self.btnLocateBottleneck.clicked.connect(self.on_locate_bottleneck)
        if hasattr(self, 'btnResetView'):
            self.btnResetView.clicked.connect(self.on_reset_view)

    def refresh(self) -> None:
        ctx = getattr(self.controller, "context", {}) if self.controller else {}
        self._refresh_kpi(ctx.get("kpi", {}))
        self._refresh_events(ctx.get("events", []))
        sel = ctx.get("selected_station", {})
        if sel:
            self._update_station_detail(sel)

    def _refresh_kpi(self, kpi: dict) -> None:
        order_batch = kpi.get("order_batch", "WO-2026-0114-B12")
        run_mode = kpi.get("run_mode", "全线")
        wip = kpi.get("wip", "在制 18 / 总 30")
        takt = kpi.get("takt", "38s")
        output = kpi.get("output", "960双")
        downtime = kpi.get("downtime", "2次")
        yield_rate = kpi.get("yield", "98.5%")
        oee = kpi.get("oee", "87.3%")
        status = kpi.get("status", "运行中")

        if hasattr(self, 'lblOrderBatchValue'):
            self.lblOrderBatchValue.setText(order_batch)
        if hasattr(self, 'lblTaktValue'):
            self.lblTaktValue.setText(takt)
        if hasattr(self, 'lblProgressValue'):
            self.lblProgressValue.setText(output)
        if hasattr(self, 'lblEtaValue'):
            self.lblEtaValue.setText(f"ETA: {oee}")
        if hasattr(self, 'lblAlarmCountValue'):
            self.lblAlarmCountValue.setText(downtime)
        if hasattr(self, 'lblRunStatusValue'):
            self.lblRunStatusValue.setText(status)

    def _refresh_events(self, events: list) -> None:
        if not hasattr(self, 'tblEvents'):
            return
        tbl = self.tblEvents
        tbl.setRowCount(0)
        for i, ev in enumerate(events):
            tbl.insertRow(i)
            pri = QTableWidgetItem(str(ev.get("priority", "")))
            t = QTableWidgetItem(ev.get("time", QDateTime.currentDateTime().toString(Qt.ISODate)))
            src = QTableWidgetItem(ev.get("source", ""))
            summ = QTableWidgetItem(ev.get("summary", ""))
            conf = QTableWidgetItem("已确认" if ev.get("confirmed") else "待确认")
            
            for c, item in enumerate((pri, t, src, summ, conf)):
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                tbl.setItem(i, c, item)

    def on_event_table_clicked(self, row: int, column: int) -> None:
        try:
            src_item = self.tblEvents.item(row, 2)
            if src_item:
                station = src_item.text()
                ctx = getattr(self.controller, "context", {}) if self.controller else {}
                stations = ctx.get("stations", {})
                details = stations.get(station) if isinstance(stations, dict) else None
                if details:
                    self._update_station_detail(details)
                else:
                    self._update_station_detail({"name": station})
        except Exception:
            pass

    def _update_station_detail(self, info: dict) -> None:
        name = info.get("name", "—")
        if not name.startswith("选中工站"):
            name = f"选中工站：{name}"
        
        if hasattr(self, 'lblStationName'):
            self.lblStationName.setText(name)
        
        state = info.get("state", "—")
        rate = info.get("recent_takt", "")
        if rate:
            state = f"{state}  近5min节拍：{rate}"
        if hasattr(self, 'lblStationState'):
            self.lblStationState.setText(f"状态：{state}")
        
        recipe = info.get("recipe", info.get("recipe_id", "—"))
        if hasattr(self, 'lblRecipe'):
            self.lblRecipe.setText(f"工艺：{recipe}")
        
        params = info.get("params", info.get("auto_params", "—"))
        if hasattr(self, 'lblParams'):
            self.lblParams.setText(f"参数：{params}")
        
        count = info.get("count", info.get("tray_count", "—"))
        if hasattr(self, 'lblCount'):
            self.lblCount.setText(f"计数：{count}")
        
        alarm = info.get("alarm", "—")
        if hasattr(self, 'lblAlarm'):
            self.lblAlarm.setText(f"告警：{alarm}")

        if hasattr(self, 'textStationDetail'):
            detail_text = f"工站: {name}\n状态: {state}\n工艺: {recipe}\n参数: {params}\n计数: {count}\n告警: {alarm}"
            self.textStationDetail.setPlainText(detail_text)

        dev = info.get("device_id") or info.get("device")
        if dev:
            self._highlight_station_by_name(info.get("name"))

    def _highlight_station_by_name(self, name: str) -> None:
        self._build_mimic_template()
        for it in self._scene.items():
            if isinstance(it, QGraphicsSimpleTextItem):
                if name and name in it.text():
                    br = QGraphicsRectItem(it.x() - 6, it.y() - 6, 132, 72)
                    br.setPen(QPen(QColor("#d32f2f"), 2))
                    br.setBrush(QBrush(QColor(0, 0, 0, 0)))
                    self._scene.addItem(br)
                    break

    def on_start(self) -> None:
        print("Start command issued")
        if self.controller and hasattr(self.controller, 'notify'):
            self.controller.notify("start", {})

    def on_pause(self) -> None:
        print("Pause command issued")
        if self.controller and hasattr(self.controller, 'notify'):
            self.controller.notify("pause", {})

    def on_stop(self) -> None:
        print("Stop command issued")
        if self.controller and hasattr(self.controller, 'notify'):
            self.controller.notify("stop", {})

    def on_reset(self) -> None:
        print("Reset command issued")
        if self.controller and hasattr(self.controller, 'notify'):
            self.controller.notify("reset", {})

    def on_apply_profile(self) -> None:
        if hasattr(self, 'cmbEnableProfile'):
            profile = self.cmbEnableProfile.currentText()
            print(f"Applying profile: {profile}")
            if self.controller and hasattr(self.controller, 'notify'):
                self.controller.notify("apply_profile", {"profile": profile})

    def on_ack_alarm(self) -> None:
        print("Acknowledge alarm")
        if self.controller and hasattr(self.controller, 'notify'):
            self.controller.notify("ack_alarm", {})

    def on_mute_alarm(self) -> None:
        print("Mute alarm")
        if self.controller and hasattr(self.controller, 'notify'):
            self.controller.notify("mute_alarm", {})

    def on_export_alarm(self) -> None:
        print("Export alarm logs")
        if self.controller and hasattr(self.controller, 'notify'):
            self.controller.notify("export_alarm", {})

    def on_locate_bottleneck(self) -> None:
        print("Locate bottleneck")
        ctx = getattr(self.controller, "context", {}) if self.controller else {}
        stations = ctx.get("stations", {})
        for name, info in stations.items():
            if "blocked" in str(info.get("state", "")).lower():
                self._update_station_detail(info)
                break

    def on_reset_view(self) -> None:
        self.lineMimicView.resetTransform()
        self._build_mimic_template()
        bbox = self._scene.itemsBoundingRect()
        self.lineMimicView.fitInView(bbox.adjusted(-20, -20, 20, 20), Qt.KeepAspectRatio)