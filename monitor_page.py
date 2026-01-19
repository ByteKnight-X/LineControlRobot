from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import Qt, QRectF, QTimer, QDateTime, QUrl
from PyQt5.QtGui import QPen, QBrush, QColor, QFont
from PyQt5.QtWidgets import QGraphicsScene, QGraphicsRectItem, QGraphicsSimpleTextItem, QTableWidgetItem
from pathlib import Path


class MonitorPage(QtWidgets.QWidget):
    """Production monitoring page (loads forms/monitor_page.ui)."""

    def __init__(self, controller=None):
        super().__init__()
        uic.loadUi(str(Path(__file__).resolve().parent / "forms" / "monitor_page.ui"), self)
        self.controller = controller
        self._init_scene()
        self._connect_signals()
        # periodic refresh (controller may update context from backend)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(2000)  # 2s refresh
        self.refresh()

    def _init_scene(self) -> None:
        """Prepare QGraphicsScene used by lineMimicView as a simple placeholder topology renderer."""
        self._scene = QGraphicsScene(self)
        self.lineMimicView.setScene(self._scene)
        self.lineMimicView.setRenderHint(self.lineMimicView.renderHints() | Qt.Antialiasing)
        self._font = QFont()
        self._font.setPointSize(9)
        self._build_mimic_template()

    def _build_mimic_template(self) -> None:
        """Draw a simple linear topology with grouped stations and placeholders for loop segments."""
        self._scene.clear()
        margin = 12
        w = max(640, self.lineMimicView.width() - 2 * margin)
        node_w, node_h = 120, 60
        gap = 18
        x = margin
        y = margin + 20

        def add_node(label, color=QColor("#e0f7fa"), tag=None):
            nonlocal x
            rect = QGraphicsRectItem(x, y, node_w, node_h)
            rect.setPen(QPen(QColor("#607d8b")))
            rect.setBrush(QBrush(color))
            self._scene.addItem(rect)
            txt = QGraphicsSimpleTextItem(label)
            txt.setFont(self._font)
            txt.setPos(x + 8, y + 18)
            self._scene.addItem(txt)
            if tag:
                tag_txt = QGraphicsSimpleTextItem(tag)
                tag_txt.setFont(self._font)
                tag_txt.setBrush(QBrush(QColor("#004d40")))
                tag_txt.setPos(x + node_w - 28, y - 10)
                self._scene.addItem(tag_txt)
            x += node_w + gap

        # loader
        add_node("上料", QColor("#c8e6c9"))
        # groups with loop markers in parentheses per spec
        add_node("丝印1\n烘干1", QColor("#fff9c4"), tag="循环?")
        add_node("丝印2\n烘干2", QColor("#fff9c4"), tag="循环?")
        add_node("丝印3\n烘干3", QColor("#fff9c4"), tag="循环?")
        add_node("丝印4\n烘干4", QColor("#fff9c4"))
        add_node("丝印5\n烘干5", QColor("#fff9c4"))
        add_node("丝印6\n烘干6", QColor("#fff9c4"))
        add_node("丝印7\n烘干7", QColor("#fff9c4"))
        add_node("下料", QColor("#ffcdd2"))

        # bounding rect
        total_w = x + margin
        self._scene.setSceneRect(QRectF(0, 0, total_w, node_h + 3 * margin))

    def _connect_signals(self) -> None:
        """Wire UI signals to handlers."""
        try:
            self.tblEvents.cellClicked.disconnect()
        except Exception:
            pass
        self.tblEvents.cellClicked.connect(self.on_event_table_clicked)

        self.btnToggleLoop.clicked.connect(self.on_toggle_loop)
        self.btnChangeRecipe.clicked.connect(self.on_change_recipe)
        self.btnResetAlarm.clicked.connect(self.on_reset_alarm)
        self.btnCallAssist.clicked.connect(self.on_call_assist)

    def refresh(self) -> None:
        """Refresh UI from controller.context (events, selected_station, KPIs)."""
        ctx = getattr(self.controller, "context", {}) if self.controller else {}
        self._refresh_kpi(ctx.get("kpi", {}))
        self._refresh_events(ctx.get("events", []))
        sel = ctx.get("selected_station", {})
        if sel:
            self._update_station_detail(sel)

    def _refresh_kpi(self, kpi: dict) -> None:
        """Update top bar KPI labels (safe defaults)."""
        order = kpi.get("order_batch", "订单：—")
        runmode = kpi.get("run_mode_wip", "运行模式：—")
        stats = kpi.get("stats", "节拍：—  产出：—  停机：—  良率：—  OEE：—")
        self.lblOrderBatch.setText(order)
        self.lblRunModeWip.setText(runmode)
        self.lblKpi.setText(stats)

    def _refresh_events(self, events: list) -> None:
        """Populate events table. Expect list of dicts with keys: priority, time, source, summary, confirmed"""
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
        """Select event row and reflect its source station into station detail."""
        try:
            src_item = self.tblEvents.item(row, 2)
            if src_item:
                station = src_item.text()
                # attempt to find station details in controller.context
                ctx = getattr(self.controller, "context", {}) if self.controller else {}
                stations = ctx.get("stations", {})
                details = stations.get(station) if isinstance(stations, dict) else None
                if details:
                    self._update_station_detail(details)
                else:
                    # minimal fallback: set name
                    self._update_station_detail({"name": station})
        except Exception:
            pass

    def _update_station_detail(self, info: dict) -> None:
        """Fill station detail labels from info dict."""
        name = info.get("name", "选中工站：—")
        if not name.startswith("选中工站"):
            name = f"选中工站：{name}"
        self.lblStationName.setText(name)
        state = info.get("state", "状态：—")
        rate = info.get("recent_takt", "")
        if rate:
            state = f"{state}  近5min节拍：{rate}"
        self.lblStationState.setText(state)
        recipe = info.get("recipe", info.get("recipe_id", "—"))
        self.lblRecipe.setText(f"当前工艺：{recipe}")
        params = info.get("params", info.get("auto_params", ""))
        self.lblParams.setText(f"自动参数：{params}")
        count = info.get("count", info.get("tray_count", "—"))
        self.lblCount.setText(f"托盘计数：已处理 {count} 托盘（本班）")

        # visually mark station on mimic if deviceId given
        dev = info.get("device_id") or info.get("device")
        if dev:
            self._highlight_station_by_name(info.get("name"))

    def _highlight_station_by_name(self, name: str) -> None:
        """Simple highlight: redraw template and overlay a red border on matching text item if found."""
        # rebuild base template for deterministic state
        self._build_mimic_template()
        # try to find matching text and add a highlight rect
        for it in self._scene.items():
            if isinstance(it, QGraphicsSimpleTextItem):
                if name and name in it.text():
                    br = QGraphicsRectItem(it.x() - 6, it.y() - 6, 132, 72)
                    br.setPen(QPen(QColor("#d32f2f"), 2))
                    br.setBrush(QBrush(QColor(0, 0, 0, 0)))
                    self._scene.addItem(br)
                    break

    # Command handlers (emit simple context changes or call controller endpoints if available)
    def on_toggle_loop(self) -> None:
        ctx = getattr(self.controller, "context", {}) if self.controller else {}
        cur = ctx.get("selected_station", {}) or {}
        enabled = not bool(cur.get("loop_enabled"))
        cur["loop_enabled"] = enabled
        if self.controller:
            self.controller.context["selected_station"] = cur
        self.lblLegend.setText(f"循环段 {'已启用' if enabled else '已停用'}")
        # optional: notify backend via controller if method exists
        try:
            if hasattr(self.controller, "notify") and callable(self.controller.notify):
                self.controller.notify("toggle_loop", cur)
        except Exception:
            pass

    def on_change_recipe(self) -> None:
        # placeholder: open dialog to input recipe id (simple built-in)
        rid, ok = QtWidgets.QInputDialog.getText(self, "更换工艺配方", "输入 Recipe ID:")
        if ok and rid:
            ctx = getattr(self.controller, "context", {}) if self.controller else {}
            sel = ctx.get("selected_station", {}) or {}
            sel["recipe"] = rid
            if self.controller:
                self.controller.context["selected_station"] = sel
            self._update_station_detail(sel)

    def on_reset_alarm(self) -> None:
        # mark selected station alarm reset in context
        ctx = getattr(self.controller, "context", {}) if self.controller else {}
        sel = ctx.get("selected_station", {}) or {}
        sel["alarm"] = None
        if self.controller:
            self.controller.context["selected_station"] = sel

    def on_call_assist(self) -> None:
        # signal assistance request (store in context)
        ctx = getattr(self.controller, "context", {}) if self.controller else {}
        sel = ctx.get("selected_station", {}) or {}
        sel["assist_requested"] = True
        if self.controller:
            self.controller.context["selected_station"] = sel