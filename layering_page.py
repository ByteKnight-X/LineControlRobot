import re
from pathlib import Path
from PyQt5 import QtWidgets, uic
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QPixmap
from utilities.backend_client import BackendError



class LayeringPage(QtWidgets.QWidget):
    """
    Layering page.
    """
    def __init__(self, controller):
        super().__init__()
        uic.loadUi(str(Path(__file__).resolve().parent / "forms" / "separation_page.ui"), self)
        self.controller = controller
        self.separation_plan = controller.context.get("separation_plan")
        self.sop = controller.context.get("sop")     
        self.current_index = 0
        self._params_editing = False
        self.setup_ui()


    def setup_ui(self) -> None:
        """
        Initialize UI components and connect signals.
        """
        self.btnPrevLayer.clicked.connect(self.show_previous)
        self.btnNextLayer.clicked.connect(self.show_next)
        self.btnNextStep.clicked.connect(self.next_step)

        # Connect edit/save params
        self.btnEditParams.clicked.connect(self._on_edit_params)
        self.btnSaveParams.clicked.connect(self._on_save_params)

        # Initialize mesh data
        self.populate_thumbnails()
        self.refresh_display()


    def populate_thumbnails(self) -> None:
        """
        Populate directoryPanel from self.separation_plan (list of dicts returned by backend).
        Resolves Windows absolute paths by basename lookup under resource/layers, supports
        POSIX absolute and project-relative paths. Displays name and optional icon.
        """
        # Clear existing
        self.thumbnailsList.clear()

        # Render entries
        project_root = Path(__file__).resolve().parent
        thumb_size = QSize(120, 90)

        for idx, entry in enumerate(self.separation_plan):
            # Entry expected to be a dict with keys like 'index' and 'imagePath'
            layer_idx = entry.get("index")
            raw_path = entry.get("imagePath")
            
            # Normalize Windows / Mac path string
            s = str(raw_path).strip().strip('"').replace("\\", "/")
            if s.startswith("/") and not s.startswith("//"):
                s = s.lstrip("/")
                
            basename = Path(s).name
            candidate = None

            if re.match(r"^[A-Za-z]:/", s) or s.startswith("//") or s.startswith("\\\\"):
                candidates = [
                    project_root / "resource" / "layers" / basename,
                    project_root / "resource" / basename,
                    project_root / basename,
                ]
                for c in candidates:
                    if c.exists():
                        candidate = c.resolve()
                        break
                if candidate is None:
                    p = Path(s)
                    if p.exists():
                        candidate = p.resolve()
            else:
                p = Path(s)
                if p.is_absolute():
                    if p.exists():
                        candidate = p.resolve()
                else:
                    rel = (project_root / s).resolve()
                    if rel.exists():
                        candidate = rel
                    else:
                        layers_dir = project_root / "resource" / "layers"
                        if layers_dir.exists():
                            for f in layers_dir.iterdir():
                                if f.name.lower() == basename.lower():
                                    candidate = f.resolve()
                                    break

            display_name = f"layer{layer_idx+1}"
            itm = QtWidgets.QListWidgetItem(display_name)
            itm.setData(Qt.UserRole, layer_idx)
            itm.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

            # Set icon if resolved file exists and is loadable
            if candidate is not None and candidate.exists():
                try:
                    pix = QPixmap(str(candidate))
                    if not pix.isNull():
                        icon = QIcon(pix.scaled(thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                        itm.setIcon(icon)
                except Exception:
                    pass

            self.thumbnailsList.addItem(itm)

        # Connect handler (safe: disconnect previous if connected)
        try:
            self.thumbnailsList.itemClicked.disconnect(self._on_directory_item_clicked)
        except Exception:
            pass
        self.thumbnailsList.itemClicked.connect(self._on_directory_item_clicked)

        # Keep selection in sync
        if self.separation_plan:
            row = min(getattr(self, "current_index", 0), len(self.separation_plan) - 1)
            self.thumbnailsList.setCurrentRow(row)
            self.current_index = row

    def _on_directory_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        idx = item.data(Qt.UserRole)
        if isinstance(idx, int) and 0 <= idx < len(self.separation_plan):
            self.current_index = idx
            self.refresh_display()

    def refresh_display(self) -> None:
        """Render current SVG (path or bytes) into layerPreview (QWebEngineView)."""
        total = len(self.separation_plan) if isinstance(self.separation_plan, list) else 0
        if total == 0:
            self.layerPreview.setHtml("<html><body></body></html>", QUrl("about:blank"))
            self.layerIndexLabel.setText("0 / 0")
            return

        entry = self.separation_plan[self.current_index]
        if isinstance(entry, dict):
            item = entry.get("imagePath")
        else:
            item = entry

        # bytes -> inline SVG
        if isinstance(item, (bytes, bytearray)):
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
            params = self._mesh_params_from_layer_data()
            self._populate_mesh_params(params)
            return

        s = str(item or "").strip().strip('"').replace("\\", "/")
        # treat leading slash as project-relative
        if s.startswith("/") and not s.startswith("//"):
            s = s.lstrip("/")
        project_root = Path(__file__).resolve().parent
        basename = Path(s).name
        candidate = None

        # Windows absolute (C:/...) or UNC
        if re.match(r"^[A-Za-z]:/", s) or s.startswith("//") or s.startswith("\\\\"):
            candidates = [
                project_root / "resource" / "layers" / basename,
                project_root / "resource" / basename,
                project_root / basename,
            ]
            for c in candidates:
                if c.exists():
                    candidate = c.resolve()
                    break
            if candidate is None:
                p = Path(s)
                if p.exists():
                    candidate = p.resolve()
        else:
            p = Path(s)
            if p.is_absolute():
                if p.exists():
                    candidate = p.resolve()
            else:
                rel = (project_root / s).resolve()
                if rel.exists():
                    candidate = rel
                else:
                    layers_dir = project_root / "resource" / "layers"
                    if layers_dir.exists():
                        for f in layers_dir.iterdir():
                            if f.name.lower() == basename.lower():
                                candidate = f.resolve()
                                break

        if candidate is None or not candidate.exists():
            attempted = str(candidate) if candidate is not None else s
            self.layerPreview.setHtml(f"<html><body><div style='padding:12px;color:#900;'>File not found: {attempted}</div></body></html>", QUrl("about:blank"))
            self.layerIndexLabel.setText(f"{self.current_index + 1} / {total}")
            params = self._mesh_params_from_layer_data()
            self._populate_mesh_params(params)
            return

        # load resolved file
        self.layerPreview.load(QUrl.fromLocalFile(str(candidate)))
        self.layerIndexLabel.setText(f"{self.current_index + 1} / {total}")
        params = self._mesh_params_from_layer_data()
        self._populate_mesh_params(params)


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
            val = entry.get(key, "")
            if isinstance(widget, QtWidgets.QLineEdit):
                widget.setText("" if val is None else str(val))
                widget.setReadOnly(True)
            elif isinstance(widget, QtWidgets.QComboBox):
                # try to set matching text, else clear selection; then disable
                idx = widget.findText(str(val)) if val != "" else -1
                if idx >= 0:
                    widget.setCurrentIndex(idx)
                else:
                    widget.setCurrentIndex(-1)
                widget.setEnabled(False)
            else:
                # generic handling for other widget types
                try:
                    widget.setDisabled(True)
                except Exception:
                    pass

    def _mesh_params_from_layer_data(self) -> dict:
        """
        Build params dict keyed like DEFAULT_MESH_PARAMS ("{index}_{name}") from self.layer_data.
        Extracts mesh_count, tension, wire_diameter when available.
        """
        def _num(s):
            if s is None:
                return ""
            ss = str(s)
            m = re.search(r"[\d\.]+", ss)
            if not m:
                return ss
            val = m.group(0)
            # return int if no dot, else float
            return int(val) if val.isdigit() else float(val)

        out = {}
        for i, entry in enumerate(self.separation_plan):
            if isinstance(entry, dict):
                raw_path = entry.get("imagePath")
                s = str(raw_path).strip().replace("\\", "/")
                if s.startswith("/") and not s.startswith("//"):
                    s = s.lstrip("/")
                name = Path(s).stem if s else f"layer{i}"
                key = f"{i}_{name}"                
                out[key] = {
                    "material": entry.get("material"),
                    "model": entry.get("model"),
                    "wire_diameter": float(entry.get("lineDiameter")),
                    "pulling_method": entry.get("drawingMethod"),
                    "pulling_angle": entry.get("drawAngle"),
                    "mesh_count": int(entry.get("count")),
                    "tension": float(entry.get("tension")),
                    "frame_model": entry.get("netFrameSpecification"),
                }
            else:
                name = Path(str(entry)).stem
                key = f"{i}_{name or f'layer{i}'}"
                out[key] = {}
        return out

    def show_previous(self) -> None:
        """
        Show the previous layer.
        """
        if not self.separation_plan:
            return
        self.current_index = (self.current_index - 1) % len(self.separation_plan)
        self.thumbnailsList.setCurrentRow(self.current_index)
        self.refresh_display()

    def show_next(self) -> None:
        """
        Show the next layer.
        """
        if not self.separation_plan:
            return
        self.current_index = (self.current_index + 1) % len(self.separation_plan)
        self.thumbnailsList.setCurrentRow(self.current_index)
        self.refresh_display()
    
    def _set_params_editable(self, editable: bool) -> None:
        """
        Enable or disable editing of mesh params fields.
        """
        self._params_editing = editable
        for w in (
            self.materialLineEdit,
            self.modelLineEdit,
            self.wireDiameterLineEdit,
            self.pullingAngleLineEdit,
            self.meshCountLineEdit,
            self.tensionLineEdit,
            self.frameModelLineEdit,
        ):
            w.setReadOnly(not editable)
        self.pullingMethodCombo.setEnabled(editable)
        self.btnSaveParams.setEnabled(editable)

    def _on_edit_params(self) -> None:
        """
        Enable editing of mesh params.
        """
        self._set_params_editable(True)

    def _on_save_params(self) -> None:
        """
        Save edited mesh params back to self.separation_plan and disable editing.
        """
        if not isinstance(self.separation_plan, list) or not (0 <= self.current_index < len(self.separation_plan)):
            return
        entry = self.separation_plan[self.current_index]
        if not isinstance(entry, dict):
            return
        
        # 更新字段而非替换整个字典，保留 imagePath、index 等关键字段
        entry.update({
            "material": self.materialLineEdit.text().strip(),
            "model": self.modelLineEdit.text().strip(),
            "lineDiameter": self.wireDiameterLineEdit.text().strip(),
            "drawingMethod": self.pullingMethodCombo.currentText().strip(),
            "drawAngle": int(self.pullingAngleLineEdit.text()) if self.pullingAngleLineEdit.text().strip() else 0,
            "tension": self.tensionLineEdit.text().strip(),
            "netFrameSpecification": self.frameModelLineEdit.text().strip(),
            "count": int(self.meshCountLineEdit.text()) if self.meshCountLineEdit.text().strip() else 0,
        })
        
        self.controller.context["separationPlan"] = self.separation_plan
        self._set_params_editable(False)
        self.refresh_display()

    def next_step(self) -> None:
        """
        Start routing inference.
        """
        task_id = self.controller.context.get("task_id")
        if not task_id:
            QtWidgets.QMessageBox.warning(self, "缺少 task_id", "未找到 task_id，无法生成工艺路线。")
            return
        
        # GenerateRouteRequest: separationPlan + sop
        payload = {
            "approved": True,
            "separationPlan": self.separation_plan,
            "sop": self.sop,
        }

        try:
            data = self.controller.backend.workflow.generate_route(str(task_id), payload)
        except BackendError as exc:
            QtWidgets.QMessageBox.critical(self, "请求失败", str(exc))
            return

        # Fill context with response data
        self.controller.context["route"] = data.get("route")
        self.controller.context["sop"] = self.sop
        self.controller.context["separation_plan"] = self.separation_plan        
        self.controller.show_page("route_page")




