import re
from PyQt5 import QtWidgets, uic
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtCore import QUrl
from pathlib import Path
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QPixmap
from utilities.constants import DEFAULT_MESH_PARAMS
import requests, json


class LayeringPage(QtWidgets.QWidget):
    """
    Layering page.
    """
    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/layering_page.ui", self)
        self.controller = controller        
        layering = controller.context.get("layering_data", {}) or {}
        self.layer_data = layering.get("separationPlan") or layering.get("separation_plan") or []
        self.current_index = 0
        self.setup_ui()


    def setup_ui(self) -> None:
        """
        Initialize UI components and connect signals.
        """
        self.btnPrevLayer.clicked.connect(self.show_previous)
        self.btnNextLayer.clicked.connect(self.show_next)
        self.btnNextStep.clicked.connect(self.next_step)
        self.populate_thumbnails()
        self.refresh_display()


    # helper: pick first non-empty key variant from entry dict
    def _get_field(self, entry: dict, *keys):
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
    
    def next_step(self) -> None:
        """
        Proceed to the next step in the workflow.
        """
        # obtain task_id from context set by import_page
        layering = self.controller.context.get("layering_data") or {}
        task_id = layering.get("task_id")
        if not task_id:
            QtWidgets.QMessageBox.warning(self, "缺少 task_id", "未找到 task_id，无法确认分层方案。")
            return

        url = f"http://127.0.0.1:8000/tasks/{task_id}/separation/confirm"
        payload = {"approved": True}
        try:
            resp = requests.post(url, json=payload, timeout=10)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "请求失败", str(exc))
            return

        # show response in dialog
        if not resp.ok:
            QtWidgets.QMessageBox.critical(self, "确认失败", f"状态码: {resp.status_code}\n{resp.text}")
            return

        try:
            data = resp.json()
            pretty = json.dumps(data, ensure_ascii=False, indent=2)
            self.controller.context["route"] = data.get("processRouteXml", "")
            QtWidgets.QMessageBox.information(self, "确认成功", data.get("processRouteXml", ""))
        except Exception:
            QtWidgets.QMessageBox.information(self, "确认成功", resp.text)
            self.controller.context["layering_data"] = resp.text
        self.controller.show_page('routine_page', self.controller.btnRoutine)




