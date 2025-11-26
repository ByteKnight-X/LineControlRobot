from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QGraphicsScene, QGraphicsRectItem, QGraphicsLineItem, QGraphicsSimpleTextItem
from PyQt5.QtGui import QPen, QBrush, QColor, QPainter, QPolygonF
from PyQt5.QtCore import QRectF, QPointF, Qt
from utilities.constants import DEFAULT_ROUTINE_LISTS
import xml.etree.ElementTree as ET
from pathlib import Path


# simple Node item (rect with text)
class NodeItem(QGraphicsRectItem):
    def __init__(self, rect: QRectF, text: str):
        super().__init__(rect)
        self.node_text = text  # 保存节点文本
        self.setBrush(QBrush(QColor("#4A90E2")))  # 蓝色背景
        self.setPen(QPen(QColor("#1A3D6D"), 3))   # 深蓝描边，线宽3
        self.setRect(rect)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)

        # 圆角绘制（重写 paint 方法）
        self.round_radius = 24

        # 美观的文本
        txt = QGraphicsSimpleTextItem(text, self)
        font = txt.font()
        font.setPointSize(24)
        font.setBold(True)
        txt.setFont(font)
        txt.setBrush(QBrush(QColor("#fff")))  # 白色字体
        txt_rect = txt.boundingRect()
        txt.setPos(rect.x() + (rect.width() - txt_rect.width())/2,
                   rect.y() + (rect.height() - txt_rect.height())/2)

        # Ensure the text item does NOT consume mouse events so clicks go to the parent NodeItem
        txt.setAcceptedMouseButtons(Qt.NoButton)
        txt.setAcceptHoverEvents(False)

        # make sure parent item can still receive mouse events
        self.setAcceptHoverEvents(True)

    def paint(self, painter, option, widget=None):
        # 绘制圆角矩形
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        painter.drawRoundedRect(self.rect(), self.round_radius, self.round_radius)

    def mousePressEvent(self, ev):
        print("Clicked node:", self.node_text)
        QtWidgets.QMessageBox.information(None, "节点", f"你点击了节点: {self.node_text}")
        super().mousePressEvent(ev)


class RoutinePage(QtWidgets.QWidget):
    """Routine page."""

    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/routine_page.ui", self)
        self.controller = controller
        self.create_flow()
    
    def create_flow(self) -> None:
        """Load production_line.xml and render flow graph with loops in flowGraphicsView."""
        scene = QGraphicsScene(self)
        self.flowGraphicsView.setScene(scene)
        self.flowGraphicsView.setRenderHint(QPainter.Antialiasing)

        # Load and parse XML
        xml_path = Path(__file__).resolve().parent / "resource" / "production_line.xml"
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ns = {"gml": "http://graphml.graphdrawing.org/xmlns"}

        # Extract nodes and edges
        nodes_data = {}  # id -> {deviceId, deviceType, instruction}
        edges_data = []  # list of {source, target, edgeType, loopCount}

        graph = root.find("gml:graph", ns)
        for node in graph.findall("gml:node", ns):
            nid = node.get("id")
            data = {}
            for d in node.findall("gml:data", ns):
                key = d.get("key")
                if key == "k_deviceId":
                    data["deviceId"] = d.text
                elif key == "k_deviceType":
                    data["deviceType"] = d.text
                elif key == "k_instruction":
                    data["instruction"] = d.text
            nodes_data[nid] = data

        for edge in graph.findall("gml:edge", ns):
            src = edge.get("source")
            tgt = edge.get("target")
            etype = None
            lcount = None
            for d in edge.findall("gml:data", ns):
                key = d.get("key")
                if key == "k_edgeType":
                    etype = d.text
                elif key == "k_loopCount":
                    lcount = int(d.text) if d.text else None
            edges_data.append({"source": src, "target": tgt, "edgeType": etype, "loopCount": lcount})

        # Color map by device type
        color_map = {
            "上料工作站": "#4CAF50",   # green
            "丝印工作站": "#2196F3",   # blue
            "烘干机": "#FF9800",       # orange
            "下料工作站": "#9C27B0"    # purple
        }

        # Layout nodes horizontally with sufficient spacing for large flow
        node_w, node_h = 280, 120
        gap_x = 200
        start_x, start_y = 80, 250

        node_items = {}  # id -> NodeItem
        node_positions = {}  # id -> QPointF (center)

        ordered_ids = list(nodes_data.keys())
        for i, nid in enumerate(ordered_ids):
            x = start_x + i * (node_w + gap_x)
            y = start_y
            rect = QRectF(x, y, node_w, node_h)
            dtype = nodes_data[nid].get("deviceType", "")
            color = color_map.get(dtype, "#4A90E2")
            
            # Create custom node with color and device type as display text
            node_item = NodeItem(rect, dtype)
            node_item.setBrush(QBrush(QColor(color)))
            node_item.node_text = nodes_data[nid].get("instruction", dtype)
            scene.addItem(node_item)
            node_items[nid] = node_item
            node_positions[nid] = rect.center()

        # Identify loop groups: collect all loop edges and their participating nodes
        loop_groups = {}  # (source, target) -> loopCount
        forward_edges = []
        
        for e in edges_data:
            if e.get("edgeType") == "loop" and e.get("loopCount"):
                loop_groups[(e["source"], e["target"])] = e["loopCount"]
            elif e.get("edgeType") == "forward":
                forward_edges.append(e)

        # Draw forward edges first
        for e in forward_edges:
            src_id = e["source"]
            tgt_id = e["target"]
            if src_id not in node_positions or tgt_id not in node_positions:
                continue
            src_rect = node_items[src_id].rect()
            tgt_rect = node_items[tgt_id].rect()
            p1 = QPointF(src_rect.right(), src_rect.center().y())
            p2 = QPointF(tgt_rect.left(), tgt_rect.center().y())
            self._draw_arrow(scene, p1, p2, QColor("#333"), 4)

        # Draw loop groups: dashed rectangle around loop participants with "×N" label
        for (loop_src, loop_tgt), lcount in loop_groups.items():
            if loop_src not in node_items or loop_tgt not in node_items:
                continue
            
            # Determine bounding rect for loop group (src and tgt nodes)
            src_rect = node_items[loop_tgt].rect()  # target node in loop
            tgt_rect = node_items[loop_src].rect()  # source node in loop
            
            # Union bounding box with padding
            left = min(src_rect.left(), tgt_rect.left()) - 20
            top = min(src_rect.top(), tgt_rect.top()) - 20
            right = max(src_rect.right(), tgt_rect.right()) + 20
            bottom = max(src_rect.bottom(), tgt_rect.bottom()) + 20
            
            loop_rect = QRectF(left, top, right - left, bottom - top)
            
            # Draw dashed rectangle with no fill
            loop_box = QGraphicsRectItem(loop_rect)
            loop_box.setPen(QPen(QColor("#E91E63"), 3, Qt.DashLine))
            loop_box.setBrush(QBrush(Qt.transparent))
            scene.addItem(loop_box)
            
            # Add "×N" label at top-right corner of the loop box
            label = QGraphicsSimpleTextItem(f"×{lcount}")
            label.setBrush(QBrush(QColor("#E91E63")))
            font = label.font()
            font.setPointSize(18)
            font.setBold(True)
            label.setFont(font)
            label_rect = label.boundingRect()
            label.setPos(loop_rect.right() - label_rect.width() - 10, 
                        loop_rect.top() - label_rect.height() - 5)
            scene.addItem(label)

        # Adjust view to fit content with extra margin        
        bbox = scene.itemsBoundingRect().adjusted(-50, -50, 50, 50)
        scene.setSceneRect(bbox)
        self.flowGraphicsView.fitInView(bbox, Qt.KeepAspectRatio)


    def _draw_arrow(self, scene, p1: QPointF, p2: QPointF, color: QColor, width: int):
        """Draw straight line with arrow head."""
        line = QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
        line.setPen(QPen(color, width))
        scene.addItem(line)
        
        direction = p2 - p1
        self._draw_arrow_head(scene, p2, direction, color)

    def _draw_arrow_head(self, scene, tip: QPointF, direction: QPointF, color: QColor):
        """Draw arrow head at tip pointing in direction."""
        length = (direction.x()**2 + direction.y()**2)**0.5
        if length == 0:
            return
        ux, uy = direction.x()/length, direction.y()/length
        ah = 12.0
        perp_x, perp_y = -uy, ux
        left = QPointF(tip.x() - ux*ah + perp_x*(ah/2), tip.y() - uy*ah + perp_y*(ah/2))
        right = QPointF(tip.x() - ux*ah - perp_x*(ah/2), tip.y() - uy*ah - perp_y*(ah/2))
        poly = QPolygonF([tip, left, right])
        scene.addPolygon(poly, QPen(color), QBrush(color))

    def _bezier_curve(self, p0: QPointF, p1: QPointF, p2: QPointF, steps: int):
        """Generate points along quadratic Bezier curve."""
        points = []
        for i in range(steps + 1):
            t = i / steps
            x = (1-t)**2 * p0.x() + 2*(1-t)*t * p1.x() + t**2 * p2.x()
            y = (1-t)**2 * p0.y() + 2*(1-t)*t * p1.y() + t**2 * p2.y()
            points.append(QPointF(x, y))
        return points

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 重新适配视图内容
        scene = self.flowGraphicsView.scene()
        if scene:
            bbox = scene.itemsBoundingRect().adjusted(-50, -50, 50, 50)
            self.flowGraphicsView.fitInView(bbox, Qt.KeepAspectRatio)