"""PySide6 widgets that mimic the old CustomTkinter get/set/select/configure API."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

if sys.platform == "darwin":
    FONT_FAMILY = "PingFang SC"
elif sys.platform == "win32":
    FONT_FAMILY = "Microsoft YaHei UI"
else:
    FONT_FAMILY = "Noto Sans CJK SC"

_ACCENT = "#3498db"
_MUTED = "#9aa0a6"
_SELECTED_BG = "#1F6AA5"
_UNSELECTED_BG = "#3a3a3a"
_TEXT = "#e6e6e6"
_BORDER = "#4a4a4a"


def ui_font(size: int = 11, bold: bool = False) -> QFont:
    font = QFont(FONT_FAMILY, size)
    if bold:
        font.setBold(True)
    return font


def _invoke(callback, *args) -> None:
    if callback is None:
        return
    try:
        callback(*args)
    except TypeError:
        callback()


class ValueSlider(QWidget):
    """Label + numeric readout + discrete QSlider. get()/set() match CTk slider vars."""

    valueChanged = Signal(object)

    def __init__(
        self,
        parent,
        label,
        from_,
        to,
        default,
        resolution=None,
        tooltip=None,
        on_change=None,
    ):
        super().__init__(parent)
        self._from = float(from_)
        self._to = float(to)
        if self._to < self._from:
            self._from, self._to = self._to, self._from
        if resolution is None:
            resolution = 0.01 if (self._to - self._from) < 10 and isinstance(default, float) else 1
        self._resolution = 1 if not resolution else float(resolution)
        span = self._to - self._from
        self._steps = max(1, int(round(span / self._resolution)))
        self._on_change = on_change
        self._updating = False

        if self._resolution >= 1:
            self._fmt = "{:.0f}"
        elif self._resolution >= 0.1:
            self._fmt = "{:.1f}"
        else:
            self._fmt = "{:.2f}"

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 2)
        root.setSpacing(2)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel(str(label), self)
        self._label.setFont(ui_font(11))
        self._label.setStyleSheet(f"color: {_MUTED}; background: transparent;")
        if tooltip:
            self._label.setToolTip(str(tooltip))
        self._value_label = QLabel(self)
        self._value_label.setFont(ui_font(11, bold=True))
        self._value_label.setMinimumWidth(48)
        self._value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._value_label.setStyleSheet(
            f"color: {_ACCENT}; background: transparent; font-weight: bold;"
        )
        header.addWidget(self._label, 1)
        header.addWidget(self._value_label, 0)
        root.addLayout(header)

        self._slider = QSlider(Qt.Horizontal, self)
        self._slider.setRange(0, self._steps)
        self._slider.setSingleStep(1)
        self._slider.setPageStep(max(1, self._steps // 10))
        self._slider.setTickPosition(QSlider.NoTicks)
        self._slider.setStyleSheet(
            f"""
            QSlider::groove:horizontal {{
                height: 6px;
                background: {_UNSELECTED_BG};
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {_SELECTED_BG};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {_ACCENT};
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            """
        )
        root.addWidget(self._slider)
        self._slider.valueChanged.connect(self._on_slider)
        self._slider.sliderReleased.connect(self._on_released)

        self.set(default)

    def _value_from_tick(self, tick: int):
        raw = self._from + tick * self._resolution
        raw = max(self._from, min(self._to, raw))
        if self._resolution >= 1:
            return int(round(raw))
        if self._resolution >= 0.1:
            return round(raw, 1)
        return round(raw, 2)

    def _tick_from_value(self, value) -> int:
        tick = int(round((float(value) - self._from) / self._resolution))
        return max(0, min(self._steps, tick))

    def _refresh_label(self) -> None:
        self._value_label.setText(self._fmt.format(self.get()))

    def get(self):
        return self._value_from_tick(self._slider.value())

    def set(self, value) -> None:
        tick = self._tick_from_value(value)
        self._updating = True
        self._slider.blockSignals(True)
        self._slider.setValue(tick)
        self._slider.blockSignals(False)
        self._refresh_label()
        self._updating = False

    def _emit_change(self) -> None:
        value = self.get()
        _invoke(self._on_change, value)
        self.valueChanged.emit(value)

    def _on_slider(self, _tick: int) -> None:
        self._refresh_label()
        if self._updating:
            return
        # 拖动中只改数字，松手再通知，避免每格都跑一遍提取
        if self._slider.isSliderDown():
            return
        self._emit_change()

    def _on_released(self) -> None:
        if self._updating:
            return
        self._emit_change()


class CheckRow(QCheckBox):
    """Checkbox with CTk-style get()/select()/deselect() and optional toggle command."""

    def __init__(self, parent=None, text="", command=None):
        if isinstance(parent, str) and text == "":
            text, parent = parent, None
        super().__init__(str(text), parent)
        self._command = command
        self.setFont(ui_font(11))
        self.setStyleSheet(
            f"""
            QCheckBox {{
                color: {_TEXT};
                spacing: 8px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {_BORDER};
                border-radius: 3px;
                background: {_UNSELECTED_BG};
            }}
            QCheckBox::indicator:checked {{
                background: {_SELECTED_BG};
                border-color: {_SELECTED_BG};
            }}
            """
        )
        self.toggled.connect(self._on_toggled)

    def get(self) -> int:
        return 1 if self.isChecked() else 0

    def select(self) -> None:
        self.setChecked(True)

    def deselect(self) -> None:
        self.setChecked(False)

    def _on_toggled(self, _checked: bool) -> None:
        _invoke(self._command)


class SegmentedRow(QWidget):
    """Exclusive push-button row. get()/set()/configure(command=) match CTkSegmentedButton."""

    valueChanged = Signal(str)

    def __init__(self, parent, values, default=None, command=None, font_size=11):
        super().__init__(parent)
        self._values = [str(v) for v in values]
        self._command = command
        self._buttons: list[QPushButton] = []
        self._updating = False
        self._font_size = font_size

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        chosen = str(default) if default is not None else (self._values[0] if self._values else "")
        self._rebuild_buttons(self._values, chosen)

        self._group.idClicked.connect(self._on_user)
        self._apply_styles()
        QTimer.singleShot(0, self._apply_styles)

    def _rebuild_buttons(self, values, chosen) -> None:
        """按 values 重建按钮并选中 chosen（不触发 command）。"""
        self._updating = True
        for index, value in enumerate(values):
            button = QPushButton(value, self)
            button.setCheckable(True)
            button.setFont(ui_font(self._font_size))
            button.setCursor(Qt.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._group.addButton(button, index)
            self.layout().addWidget(button)
            self._buttons.append(button)
            if value == chosen:
                button.setChecked(True)
        self._apply_styles()
        self._updating = False

    def values(self) -> list:
        return [button.text() for button in self._buttons]

    def set_values(self, values, default=None) -> bool:
        """替换候选值。保留仍在列表中的当前选择；否则改选 default（缺省第一项）。

        返回选择是否变化。不触发 command。
        """
        new_values = [str(v) for v in values]
        if not new_values:
            return False
        current = self.get()
        for button in self._buttons:
            self._group.removeButton(button)
            self.layout().removeWidget(button)
            button.deleteLater()
        self._buttons = []
        chosen = current if current in new_values else None
        if chosen is None:
            fallback = str(default) if default is not None else new_values[0]
            chosen = fallback if fallback in new_values else new_values[0]
        self._rebuild_buttons(new_values, chosen)
        return current != chosen

    def get(self) -> str:
        button = self._group.checkedButton()
        return button.text() if button is not None else ""

    def set(self, value: str) -> None:
        target = str(value)
        self._updating = True
        for button in self._buttons:
            if button.text() == target:
                button.setChecked(True)
                break
        self._apply_styles()
        self._updating = False

    def configure(self, command=None) -> None:
        if command is not None:
            self._command = command

    def _on_user(self, _id: int) -> None:
        self._apply_styles()
        if self._updating:
            return
        value = self.get()
        _invoke(self._command, value)
        self.valueChanged.emit(value)

    def _apply_styles(self) -> None:
        for button in self._buttons:
            if button.isChecked():
                button.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {_SELECTED_BG};
                        color: white;
                        border: none;
                        padding: 6px 10px;
                        border-radius: 4px;
                    }}
                    """
                )
            else:
                button.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {_UNSELECTED_BG};
                        color: {_TEXT};
                        border: none;
                        padding: 6px 10px;
                        border-radius: 4px;
                    }}
                    QPushButton:hover {{
                        background-color: #4a4a4a;
                    }}
                    """
                )


class SectionCard(QGroupBox):
    """Titled card; body() is the inner column for child controls."""

    def __init__(self, parent, title, step=None, caption=None):
        if step is not None and str(step) != "":
            heading = f"{step}  {title}"
        else:
            heading = str(title)
        super().__init__(heading, parent)
        self.setFont(ui_font(13, bold=True))
        self.setStyleSheet(
            f"""
            QGroupBox {{
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 8px;
                margin-top: 14px;
                padding: 10px 8px 8px 8px;
                background: transparent;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }}
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 8, 6, 6)
        outer.setSpacing(6)
        if caption:
            cap = QLabel(str(caption), self)
            cap.setFont(ui_font(11))
            cap.setWordWrap(True)
            cap.setStyleSheet(f"color: {_MUTED}; background: transparent;")
            outer.addWidget(cap)

        self._body = QWidget(self)
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(6)
        outer.addWidget(self._body)

    def body(self) -> QWidget:
        return self._body


class ButtonAdapter(QPushButton):
    """QPushButton with CTk-style configure(state/text/command)."""

    def __init__(self, *args, command=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._command = None
        self.setFont(ui_font(12))
        if command is not None:
            self.configure(command=command)

    def configure(self, state=None, text=None, command=None) -> None:
        if state is not None:
            self.setEnabled(str(state).lower() != "disabled")
        if text is not None:
            self.setText(str(text))
        if command is not None:
            if self._command is not None:
                try:
                    self.clicked.disconnect(self._command)
                except (TypeError, RuntimeError):
                    pass
            self._command = command
            self.clicked.connect(self._command)


def make_slider(parent, label, from_, to, default, resolution=None, tooltip=None, on_change=None):
    return ValueSlider(parent, label, from_, to, default, resolution, tooltip, on_change)
