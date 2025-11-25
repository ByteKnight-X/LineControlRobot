from typing import List, Optional
from PyQt5 import QtWidgets, uic
from PyQt5.QtGui import QPixmap, QImage, QIcon, QPainter  # 增加 QIcon
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl
from pathlib import Path
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QPixmap
from utilities.constants import DEFAULT_MESH_PARAMS


class LayeringPage(QtWidgets.QWidget):
    """
    Layering page.
    """
    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/layering_page.ui", self)
        self.controller = controller
        self.layer_data = controller.context.get("layering_data", [])
        self.current_index = 0
        self.setup_ui()
    
    def setup_ui(self) -> None:
        self.btnPrevLayer.clicked.connect(self.show_previous)
        self.btnNextLayer.clicked.connect(self.show_next)
        self.btnNextStep.clicked.connect(self.next_step)
        self.populate_thumbnails()
        self.refresh_display()

    def populate_thumbnails(self) -> None:
        """
        Populate directoryPanel as a text-based list: each entry shows image name.
        Clicking an entry sets current_index and refreshes preview.
        """
        # clear existing
        self.thumbnailsList.clear()
        self.layer_data = self.controller.context.get("layering_data", [])

        # Use list mode so text appears as a vertical list
        self.thumbnailsList.setViewMode(QtWidgets.QListView.ListMode)
        # optional: allow icons if available; set a reasonable icon size
        self.thumbnailsList.setIconSize(QSize(120, 90))

        for i, item in enumerate(self.layer_data):
            if isinstance(item, str):
                display_name = Path(item).name
            elif isinstance(item, (bytes, bytearray)):
                # if bytes, try to use a stored name in metadata or fallback
                display_name = f"Layer {i+1}"
            else:
                display_name = f"Item {i+1}"

            itm = QtWidgets.QListWidgetItem(display_name)
            # store index so handler can find the image
            itm.setData(Qt.UserRole, i)
            itm.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.thumbnailsList.addItem(itm)

        # connect handler (safe: disconnect previous if connected)
        try:
            self.thumbnailsList.itemClicked.disconnect(self._on_directory_item_clicked)
        except Exception:
            pass
        self.thumbnailsList.itemClicked.connect(self._on_directory_item_clicked)

        # keep selection in sync
        if self.layer_data:
            row = min(getattr(self, "current_index", 0), len(self.layer_data) - 1)
            self.thumbnailsList.setCurrentRow(row)
            self.current_index = row

    def _on_directory_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        idx = item.data(Qt.UserRole)
        if isinstance(idx, int) and 0 <= idx < len(self.layer_data):
            self.current_index = idx
            self.refresh_display()

    def refresh_display(self) -> None:
        """Render current SVG (path or bytes) into layerPreview (QWebEngineView)."""
        self.layer_data = self.controller.context.get("layering_data", []) or []
        total = len(self.layer_data)
        if total == 0:
            self.layerPreview.setHtml("<html><body></body></html>", QUrl("about:blank"))
            self.layerIndexLabel.setText("0 / 0")
            return
        
        item = self.layer_data[self.current_index]
        if not item:
            self.layerPreview.setHtml("<html><body><div style='padding:12px;color:#900;'>Missing data</div></body></html>", QUrl("about:blank"))
            self.layerIndexLabel.setText(f"{self.current_index + 1} / {total}")
            return
        
        # Render SVG
        if isinstance(item, str):
            p = Path(item)
            if not p.is_absolute():
                p = (Path(__file__).resolve().parent / item).resolve()
            if not p.exists():
                self.layerPreview.setHtml(f"<html><body><div style='padding:12px;color:#900;'>File not found: {p}</div></body></html>", QUrl("about:blank"))
            else:
                self.layerPreview.load(QUrl.fromLocalFile(str(p)))
            self.layerIndexLabel.setText(f"{self.current_index + 1} / {total}")
        elif isinstance(item, (bytes, bytearray)):
            try:
                svg_text = item.decode("utf-8")
            except Exception:
                svg_text = item.decode("utf-8", errors="replace")
            html = (
                "<!doctype html><html><head><meta charset='utf-8'>"
                "<style>html,body{margin:0;height:100%;background:#fff;}svg{width:100%;height:100%;display:block;margin:auto;}</style>"
                "</head><body>"
                f"{svg_text}"
                "</body></html>"
            )
            self.layerPreview.setHtml(html, QUrl("about:blank"))
            self.layerIndexLabel.setText(f"{self.current_index + 1} / {total}")
        else:
            self.layerPreview.setHtml("<html><body><div style='padding:12px;color:#900;'>Unsupported layer data</div></body></html>", QUrl("about:blank"))
            self.layerIndexLabel.setText(f"{self.current_index + 1} / {total}")
        
        # Load DEFAULT_MESH_PARAMS into the parameter form on the right panel
        self._populate_mesh_params(DEFAULT_MESH_PARAMS)

    def _populate_mesh_params(self, params: dict) -> None:
        """Fill right-panel fields using params entry matching current_index (e.g. '0_处理剂'). 
        Selected fields are set non-editable."""
        # choose key that starts with "<index>_"
        target_prefix = f"{self.current_index}_"
        entry = None
        for k, v in params.items():
            if str(k).startswith(target_prefix):
                entry = v if isinstance(v, dict) else {}
                break

        # map logical names to widgets
        field_map = {
            "material": self.materialLineEdit,
            "model": self.modelLineEdit,
            "wire_diameter": self.wireDiameterLineEdit,
            "pulling_method": self.pullingMethodCombo,
            "pulling_angle": self.pullingAngleLineEdit,
            "mesh_count": self.meshCountLineEdit,
            "tension": self.tensionLineEdit,
            "frame_model": self.frameModelLineEdit,
        }

        for key, widget in field_map.items():
            print(entry)
            val = entry.get(key, "")
            if isinstance(widget, QtWidgets.QLineEdit):
                print("lineedit", key, val)
                widget.setText("" if val is None else str(val))
                widget.setReadOnly(True)
            elif isinstance(widget, QtWidgets.QComboBox):
                print("combobox", key, val)
                # try to set matching text, else clear selection; then disable
                idx = widget.findText(str(val)) if val != "" else -1
                if idx >= 0:
                    widget.setCurrentIndex(idx)
                else:
                    widget.setCurrentIndex(-1)
                widget.setEnabled(False)
            else:
                print("failuere")
                # generic handling for other widget types
                try:
                    widget.setDisabled(True)
                except Exception:
                    pass

    def show_previous(self) -> None:
        """
        Show the previous layer.
        """
        if not self.layer_data:
            return
        self.current_index = (self.current_index - 1) % len(self.layer_data)
        self.refresh_display()

    def show_next(self) -> None:
        """
        Show the next layer.
        """
        if not self.layer_data:
            return
        self.current_index = (self.current_index + 1) % len(self.layer_data)
        self.refresh_display()
    
    def next_step(self) -> None:
        """
        Proceed to the next step in the workflow.
        """
        print("Proceeding to the next step...")
        self.controller.show_page('routine_page', self.controller.btnRoutine)




