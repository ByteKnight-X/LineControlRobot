from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QGraphicsScene, QGraphicsRectItem, QGraphicsLineItem, QGraphicsSimpleTextItem
from PyQt5.QtGui import QPen, QBrush, QColor, QPainter, QPolygonF
from PyQt5.QtCore import QRectF, QPointF, Qt
from utilities.constants import DEFAULT_ROUTINE_LISTS


# simple Node item (rect with text)
class NodeItem(QGraphicsRectItem):
    def __init__(self, rect: QRectF, text: str):
        super().__init__(rect)
        self.node_text = text  # 保存节点文本
        # 更醒目的填充色和圆角
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
        self.setup_ui()
    
    def setup_ui(self) -> None:
        """Initialize a simple flow A -> B inside flowGraphicsView (QGraphicsView)."""
        # create scene and attach to view
        scene = QGraphicsScene(self)
        self.flowGraphicsView.setScene(scene)
        self.flowGraphicsView.setRenderHint(QPainter.Antialiasing)

        # positions and sizes (scale up 5x and ensure gap so nodes don't overlap)
        scale = 0.5
        base_w, base_h = 140 * 3, 48 * 3
        a_rect = QRectF(0, 0, base_w * scale, base_h * scale)
        # gap between nodes (scaled) to avoid overlap
        gap = 80 * scale
        b_rect = QRectF(a_rect.right() + gap, 0, base_w * scale, base_h * scale)

        nodeA = NodeItem(a_rect, "A")
        nodeB = NodeItem(b_rect, "B")
        scene.addItem(nodeA)
        scene.addItem(nodeB)

        # line from A -> B (center right of A to center left of B)
        p1 = QPointF(a_rect.right(), a_rect.center().y())
        p2 = QPointF(b_rect.left(), b_rect.center().y())
        line = QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
        line.setPen(QPen(QColor("#333"), 2))
        scene.addItem(line)

        # arrow head at p2
        dx = p1.x() - p2.x()
        dy = p1.y() - p2.y()
        length = (dx*dx + dy*dy)**0.5 or 1.0
        ux, uy = dx/length, dy/length
        ah = 10.0
        perp_x, perp_y = -uy, ux
        tip = p2
        left = QPointF(p2.x() + ux*ah + perp_x*(ah/2), p2.y() + uy*ah + perp_y*(ah/2))
        right = QPointF(p2.x() + ux*ah - perp_x*(ah/2), p2.y() + uy*ah - perp_y*(ah/2))
        poly = QPolygonF([tip, left, right])
        scene.addPolygon(poly, QPen(QColor("#333")), QBrush(QColor("#333")))

        # adjust view
        bbox = scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        scene.setSceneRect(bbox)
        # self.flowGraphicsView.fitInView(bbox, Qt.KeepAspectRatio)