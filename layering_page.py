import re
from pathlib import Path
import requests
from PyQt5 import QtWidgets, uic
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QPixmap



class LayeringPage(QtWidgets.QWidget):
    """
    Layering page.
    """
    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/layering_page.ui", self)
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


    def _get_field(self, entry: dict, *keys):
        """"""
        if not isinstance(entry, dict):
            return None
        for k in keys:
            v = entry.get(k)
            if v is not None and v != "":
                return v
        return None

    def populate_thumbnails(self) -> None:
        """
        Populate directoryPanel from self.layer_data (list of dicts returned by backend).
        Resolves Windows absolute paths by basename lookup under resource/layers, supports
        POSIX absolute and project-relative paths. Displays name and optional icon.
        """
        # Clear existing
        self.thumbnailsList.clear()
        if not isinstance(self.layer_data, list):
            return

        project_root = Path(__file__).resolve().parent
        thumb_size = QSize(120, 90)

        for i, entry in enumerate(self.layer_data):
            # Entry expected to be a dict with keys like 'index' and 'imagePath'
            idx = i
            layer_idx = self._get_field(entry, "index", "layer_index")
            raw_path = self._get_field(entry, "imagePath", "image_path", "image") or ""

            # Normalize separators and treat leading "/" as project-relative
            s = str(raw_path).strip().strip('"').replace("\\", "/")
            if s.startswith("/") and not s.startswith("//"):
                s = s.lstrip("/")

            # Determine basename and attempt to resolve to a local file
            basename = Path(s).name
            candidate = None

            # Detect Windows drive like "C:/..." or UNC and try basename lookup
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

            # Prepare display name: prefer provided index + stem (e.g. "0_胶浆")
            name = Path(s).stem or basename or f"layer{i+1}"
            if layer_idx is not None:
                display_name = f"{layer_idx}_{name}"
            else:
                display_name = name or f"Layer {i+1}"

            itm = QtWidgets.QListWidgetItem(display_name)
            itm.setData(Qt.UserRole, idx)
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
        total = len(self.layer_data) if isinstance(self.layer_data, list) else 0
        if total == 0:
            self.layerPreview.setHtml("<html><body></body></html>", QUrl("about:blank"))
            self.layerIndexLabel.setText("0 / 0")
            return

        entry = self.layer_data[self.current_index]
        if isinstance(entry, dict):
            item = self._get_field(entry, "imagePath", "image_path", "image") or ""
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
        for i, entry in enumerate(self.layer_data):
            if isinstance(entry, dict):
                raw_path = self._get_field(entry, "imagePath", "image_path", "image") or ""
                s = str(raw_path).strip().replace("\\", "/")
                if s.startswith("/") and not s.startswith("//"):
                    s = s.lstrip("/")
                name = Path(s).stem if s else f"layer{i}"
                key = f"{i}_{name}"
                out[key] = {
                    "material": self._get_field(entry, "material") or "",
                    "model": self._get_field(entry, "model") or "",
                    "wire_diameter": _num(self._get_field(entry, "lineDiameter", "line_diameter", "wire_diameter", "wire") or ""),
                    "pulling_method": self._get_field(entry, "drawingMethod", "drawing_method", "pulling_method") or "",
                    "pulling_angle": self._get_field(entry, "drawAngle", "draw_angle", "pulling_angle"),
                    "mesh_count": _num(self._get_field(entry, "mesh_count", "mesh", "目数", "count") or ""),
                    "tension": _num(self._get_field(entry, "tension", "pull") or ""),
                    "frame_model": self._get_field(entry, "netFrameSpecification", "net_frame_specification", "frame_model") or "",
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
    
    def _set_params_editable(self, editable: bool) -> None:
        self._params_editing = editable
        # line edits
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
        # combo
        self.pullingMethodCombo.setEnabled(editable)

        self.btnSaveParams.setEnabled(editable)

    def _on_edit_params(self) -> None:
        self._set_params_editable(True)

    def _on_save_params(self) -> None:
        if not isinstance(self.layer_data, list) or not (0 <= self.current_index < len(self.layer_data)):
            return
        entry = self.layer_data[self.current_index]
        if not isinstance(entry, dict):
            return

        def _int_or_none(s):
            try:
                ss = str(s).strip()
                return int(ss) if ss != "" else None
            except Exception:
                return None

        # 写回后端 MeshInfo 认可的字段名（注意别名）
        entry["material"] = self.materialLineEdit.text().strip()
        entry["model"] = self.modelLineEdit.text().strip()
        entry["lineDiameter"] = self.wireDiameterLineEdit.text().strip()
        entry["drawingMethod"] = self.pullingMethodCombo.currentText().strip()
        entry["drawAngle"] = _int_or_none(self.pullingAngleLineEdit.text())
        entry["tension"] = self.tensionLineEdit.text().strip()
        entry["netFrameSpecification"] = self.frameModelLineEdit.text().strip()

        # 这里 UI 的“目数”后端 MeshInfo 没有 meshCount 字段；先落到 count（Optional[int]）
        entry["count"] = _int_or_none(self.meshCountLineEdit.text())

        # 同步回 context，便于后续页面/重进时还原
        layering = self.controller.context.get("layering_data") or {}
        layering["separationPlan"] = self.layer_data
        layering["sop"] = self.sop_data
        self.controller.context["layering_data"] = layering

        self._set_params_editable(False)
        self.refresh_display()

    def next_step(self) -> None:
        layering = self.controller.context.get("layering_data")
        task_id = layering.get("task_id")
        if not task_id:
            QtWidgets.QMessageBox.warning(self, "缺少 task_id", "未找到 task_id，无法生成工艺路线。")
            return
        
        # GenerateRouteRequest: separationPlan + SOP 必填
        payload = {
            "approved": True,
            "separationPlan": self.layer_data,
            "SOP": self.sop_data,
        }

        url = f"http://127.0.0.1:8000/tasks/{task_id}/generate_route"
        try:
            resp = requests.post(url, json=payload, timeout=10)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "请求失败", str(exc))
            return

        if not resp.ok:
            QtWidgets.QMessageBox.critical(self, "生成失败", f"状态码: {resp.status_code}\n{resp.text}")
            return

        data = resp.json()

        # 后端 GenerateRouteResponse 字段是 route（不是 processRouteXml）
        self.controller.context["route"] = data.get("route", "")

        # 也把最新 separationPlan/sop 回填，保持一致
        layering["separationPlan"] = data.get("separationPlan", self.layer_data)
        layering["sop"] = data.get("sop", self.sop_data)
        self.controller.context["layering_data"] = layering

        self.controller.show_page("routine_page", self.controller.btnRoutine)




