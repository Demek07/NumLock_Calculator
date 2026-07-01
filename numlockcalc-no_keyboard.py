#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CalcNumLock v4.4 (без keyboard, без пульсации)
"""
import ctypes
import base64
import json
import sys
import re
import subprocess
from pathlib import Path
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QCloseEvent, QMouseEvent, QPixmap, QIcon, QColor
from PyQt5.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QAction,
    QWidget, QDialog, QPushButton, QMessageBox,
    QLineEdit, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem
)
import PyQt5.QtCore as QtCore

from numlockcalc_icon import ICON_B64

APP_NAME = "CalcNumLock"
APP_VERSION = "4.4"
DATA_DIR_NAME = "_calcnumlock_data"


def get_app_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    if "__file__" in globals():
        return Path(__file__).resolve().parent
    return Path(sys.argv[0]).resolve().parent


APP_ROOT = get_app_root()
DATA_DIR = APP_ROOT / DATA_DIR_NAME
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA_DIR / "config.json"
HISTORY_FILE = DATA_DIR / "history.json"

VK_NUMLOCK = 0x90
KEYEVENTF_KEYUP = 0x0002
user32 = ctypes.windll.user32
GetKeyState = user32.GetKeyState
keybd_event = user32.keybd_event

_programmatic_numlock = False


def load_embedded_icon():
    try:
        raw = base64.b64decode(ICON_B64)
        pix = QPixmap()
        if pix.loadFromData(raw, "ICO"):
            return QIcon(pix)
    except:
        pass
    pix = QPixmap(32, 32)
    pix.fill(QColor("#0078d7"))
    return QIcon(pix)


def is_numlock_on():
    try:
        return bool(GetKeyState(VK_NUMLOCK) & 1)
    except Exception:
        return False


def set_numlock_on():
    global _programmatic_numlock
    if not is_numlock_on():
        _programmatic_numlock = True
        keybd_event(VK_NUMLOCK, 0, 0, 0)
        keybd_event(VK_NUMLOCK, 0, KEYEVENTF_KEYUP, 0)
        QTimer.singleShot(50, lambda: set_programmatic_flag(False))


def set_programmatic_flag(value):
    global _programmatic_numlock
    _programmatic_numlock = value


def is_programmatic_numlock():
    global _programmatic_numlock
    return _programmatic_numlock


def format_number(num_str):
    if not num_str:
        return num_str
    try:
        if ',' in num_str:
            float(num_str.replace(',', '.'))
        else:
            float(num_str)
    except ValueError:
        return num_str
    if ',' in num_str:
        parts = num_str.split(',')
        int_part, frac_part = parts[0], ',' + parts[1] if len(parts) > 1 else ''
    elif '.' in num_str:
        parts = num_str.split('.')
        int_part, frac_part = parts[0], '.' + parts[1] if len(parts) > 1 else ''
    else:
        int_part, frac_part = num_str, ''
    sign = '-' if int_part.startswith('-') else ''
    int_part = int_part.lstrip('-').lstrip('0') or '0'
    int_part = ' '.join([int_part[max(0, i - 3):i] for i in range(len(int_part), 0, -3)][::-1])
    return sign + int_part + frac_part


def round_number(num_str, decimals=4):
    if not num_str:
        return num_str
    try:
        rounded = round(float(num_str.replace(',', '.')), decimals)
    except ValueError:
        return num_str
    if rounded.is_integer():
        return str(int(rounded))
    res = f"{rounded:.{decimals}f}".rstrip('0').rstrip('.')
    return res.replace('.', ',')


def get_startup_folder():
    try:
        return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    except:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x19, None, 0, buf)
        return Path(buf.value) / "Programs" / "Startup"


def get_shortcut_path():
    startup = get_startup_folder()
    if getattr(sys, 'frozen', False):
        return startup / (Path(sys.executable).stem + ".lnk")
    return startup / f"{APP_NAME}.lnk"


def is_autostart_enabled():
    try:
        return get_shortcut_path().exists()
    except:
        return False


def add_to_autostart():
    try:
        startup_folder = get_startup_folder()
        startup_folder.mkdir(parents=True, exist_ok=True)
        shortcut_path = get_shortcut_path()
        if getattr(sys, 'frozen', False):
            target, working_dir = sys.executable, str(APP_ROOT)
            script = f'$shell = New-Object -ComObject WScript.Shell; $shortcut = $shell.CreateShortCut("{shortcut_path}"); $shortcut.TargetPath = "{target}"; $shortcut.WorkingDirectory = "{working_dir}"; $shortcut.Description = "{APP_NAME}"; $shortcut.Save();'
        else:
            python_dir = Path(sys.executable).parent
            pythonw = python_dir / "pythonw.exe"
            target = str(pythonw if pythonw.exists() else sys.executable)
            script = f'$shell = New-Object -ComObject WScript.Shell; $shortcut = $shell.CreateShortCut("{shortcut_path}"); $shortcut.TargetPath = "{target}"; $shortcut.Arguments = "{Path(sys.argv[0]).resolve()}"; $shortcut.WorkingDirectory = "{str(APP_ROOT)}"; $shortcut.Description = "{APP_NAME}"; $shortcut.Save();'
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle",
                       "Hidden", "-Command", f"try {{ {script} }} catch {{ exit 1 }}; exit 0"], check=False)
        return True
    except Exception as e:
        print(f"[ERROR] add_to_autostart: {e}")
        return False


def remove_from_autostart():
    try:
        get_shortcut_path().unlink()
        return True
    except:
        return False


class HistoryDialog(QDialog):
    def __init__(self, history_list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("История вычислений")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("QDialog { background: #eee; color: #000; } QListWidget { background: #eee; color: #000; border: 2px solid #0078d7; border-radius: 4px; font-family: Arial; font-weight: bold; font-size: 13px; padding: 5px; } QListWidget::item { padding: 4px 8px; border-bottom: 1px solid #0078d7; } QListWidget::item:selected { background: #0078d7; color: white; } QPushButton { background: #eee; color: #000; border: 1px solid #0078d7; border-radius: 4px; padding: 6px 16px; } QPushButton:hover { background: #0078d7; }")
        self.history_list, self.selected_item = history_list, None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(QLabel(f"История ({len(history_list)} записей)"), alignment=Qt.AlignCenter)
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        for item in reversed(history_list):
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(QPushButton("Очистить историю", clicked=self.clear_history))
        btn_layout.addStretch()
        btn_layout.addWidget(QPushButton("Закрыть", clicked=self.close))
        layout.addLayout(btn_layout)

    def on_item_double_clicked(self, item):
        self.selected_item = item.text()
        self.accept()

    def clear_history(self):
        reply = QMessageBox.question(self, "Очистка истории", "Удалить все записи из истории?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.list_widget.clear()
            self.history_list.clear()
            self.selected_item = None
            self.accept()


class MiniCalcWindow(QWidget):
    _sig_toggle = QtCore.pyqtSignal()
    _pending_toggle = False  # ← Исправление: блокирует повторный эмит сигнала

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Калькулятор")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setFixedWidth(400)
        self.setFixedHeight(38)
        self.setWindowIcon(load_embedded_icon())
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        self.drag_label = QLabel("☰")
        self.drag_label.setFixedWidth(26)
        self.drag_label.setStyleSheet(
            "QLabel { color: #888; font-size: 15px; padding: 4px; font-weight: bold; } QLabel:hover { color: #0078d7; }")
        self.drag_label.setAlignment(Qt.AlignCenter)
        self.drag_label.mousePressEvent = self.mousePressEvent
        self.drag_label.mouseMoveEvent = self.mouseMoveEvent
        layout.addWidget(self.drag_label)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Введите выражение (например, 2,2+3,8)")
        self.input_field.setStyleSheet(
            "QLineEdit { background: #eee; color: #000; border: 2px solid #0078d7; border-radius: 4px; padding: 3px 10px; font-size: 13px; font-family: Arial; font-weight: bold; } QLineEdit:focus { border: 3px solid #0078d7; }")
        self.input_field.returnPressed.connect(self.calculate)
        self.input_field.textChanged.connect(self.on_text_changed)
        layout.addWidget(self.input_field, 1)

        self.btn_history = QPushButton("📋")
        self.btn_history.setFixedSize(26, 26)
        self.btn_history.setStyleSheet(
            "QPushButton { background: transparent; color: #888; border: none; font-size: 13px; border-radius: 4px; } QPushButton:hover { color: #eee; background: #0078d7; }")
        self.btn_history.clicked.connect(self.show_history)
        layout.addWidget(self.btn_history)

        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(26, 26)
        self.btn_close.setStyleSheet(
            "QPushButton { background: transparent; color: #888; border: none; font-size: 13px; border-radius: 4px; } QPushButton:hover { color: #fff; background: #c42b2b; }")
        self.btn_close.clicked.connect(self.hide_to_tray)
        layout.addWidget(self.btn_close)

        self.last_result = None
        self.last_expression = None
        self.is_result_displayed = False
        self.last_text = ""
        self.processing_operator = False
        self.history = []
        self.history_index = -1
        self.current_input = ""
        self._load_history()
        self.drag_pos = None
        self._load_settings()
        self.running = True

        # 🔁 ПЕРИОДИЧЕСКАЯ ПРОВЕРКА NumLock (без keyboard)
        self.numlock_hook_timer = QTimer()
        self.numlock_hook_timer.setInterval(100)
        self.numlock_hook_timer.timeout.connect(self._check_numlock_hook)
        self.numlock_hook_timer.start()

    def _check_numlock_hook(self):
        # ← ← ← ИСПРАВЛЕННЫЙ МЕТОД
        if not self.running or not is_numlock_on() or self._pending_toggle:
            return
        self._pending_toggle = True
        self._sig_toggle.emit()
        set_programmatic_flag(True)

    def _load_settings(self):
        if not CONFIG_FILE.exists():
            return
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            sp = data.get("window_pos")
            if isinstance(sp, list) and len(sp) == 2:
                self.move(sp[0], sp[1])
        except Exception:
            pass

    def _save_settings(self):
        try:
            CONFIG_FILE.write_text(
                json.dumps({"window_pos": [self.x(), self.y()]}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def _load_history(self):
        if HISTORY_FILE.exists():
            try:
                self.history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                self.history = []
        else:
            self.history = []

    def _save_history(self):
        try:
            HISTORY_FILE.write_text(
                json.dumps(self.history[-100:], ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def _add_to_history(self, text):
        if text and text not in self.history:
            self.history.append(text)
            if len(self.history) > 100:
                self.history = self.history[-100:]
            self._save_history()
            self.history_index = -1
            self.current_input = ""

    def show_history(self):
        if not self.history:
            QMessageBox.information(self, "История", "История вычислений пуста.", QMessageBox.Ok)
            return
        dialog = HistoryDialog(self.history, self)
        if dialog.exec_() == QDialog.Accepted and dialog.selected_item:
            self.input_field.setText(dialog.selected_item)
            self.input_field.setFocus()
            self.input_field.setCursorPosition(len(dialog.selected_item))
            if '=' in dialog.selected_item:
                parts = dialog.selected_item.split('=', 1)
                if len(parts) == 2:
                    self.last_expression = parts[0].strip()
                    self.last_result = parts[1].strip()
                    self.is_result_displayed = True
                    self.last_text = dialog.selected_item

    def hide_to_tray(self):
        self._save_settings()
        self.hide()

    def on_text_changed(self, text):
        if self.processing_operator:
            return
        if not self.is_result_displayed:
            self.last_text = text
            return
        if text == self.last_text:
            return
        cursor_pos = self.input_field.cursorPosition()
        if len(text) > len(self.last_text):
            added = text[len(self.last_text):]
            if added in '+-*/%^' and self.last_result is not None:
                self.processing_operator = True
                new_text = f"{self.last_result}{added}"
                self.input_field.setText(new_text)
                self.is_result_displayed = False
                self.last_text = new_text
                self.input_field.setCursorPosition(len(new_text))
                self.processing_operator = False
                return
        if '=' in text:
            eq_pos = text.rfind('=')
            if eq_pos < len(text) - 1:
                text_without_result = text[:eq_pos]
                self.processing_operator = True
                self.input_field.setText(text_without_result)
                self.is_result_displayed = False
                self.last_text = text_without_result
                self.input_field.setCursorPosition(cursor_pos)
                self.processing_operator = False
                return
        if '=' not in text:
            self.processing_operator = True
            self.input_field.setText(self.last_expression)
            self.is_result_displayed = False
            self.last_text = self.last_expression
            self.input_field.setCursorPosition(min(cursor_pos, len(self.last_expression)))
            self.processing_operator = False
            return
        self.last_text = text

    def _normalize_expression(self, expression):
        if not expression:
            return expression
        result = []
        for i, ch in enumerate(expression):
            if ch == ' ' and i > 0 and i < len(expression)-1 and expression[i-1].isdigit() and expression[i+1].isdigit():
                continue
            elif ch == ',' and i > 0 and i < len(expression)-1 and expression[i-1].isdigit() and expression[i+1].isdigit():
                result.append('.')
            elif ch == '^':
                result.append('**')
            else:
                result.append(ch)
        return ''.join(result)

    def _safe_eval(self, expression):
        if not expression or not expression.strip():
            return None, ""
        expr = expression.strip()
        expr = self._normalize_expression(expr)
        allowed = set("0123456789+-*/().% \t")
        for ch in expr:
            if ch not in allowed:
                return None, f"Ошибка: недопустимый символ '{ch}'"

        pattern = r'^(.+?)([\+\-\*\/])(\d+(?:\.\d+)?)%$'
        match = re.match(pattern, expr)
        if match:
            left_expr, op, num_str = match.groups()
            try:
                left_val = eval(self._normalize_expression(left_expr), {"__builtins__": {}}, {})
                num = float(num_str)
                if op == '+':
                    result = left_val + (num / 100 * left_val)
                elif op == '-':
                    result = left_val - (num / 100 * left_val)
                elif op == '*':
                    result = left_val * (num / 100)
                elif op == '/':
                    result = left_val / (num / 100)
                else:
                    result = None
            except Exception:
                return None, "Ошибка: неверное выражение с процентом"
        else:
            match2 = re.match(r'^(\d+(?:\.\d+)?)%$', expr)
            if match2:
                result = float(match2.group(1)) / 100
            else:
                expr_for_eval = re.sub(r'(?<=\d)%', r'/100', expr)
                try:
                    result = eval(expr_for_eval, {"__builtins__": {}}, {})
                except SyntaxError:
                    return None, "Ошибка: неверное выражение"
                except ZeroDivisionError:
                    return None, "Ошибка: деление на ноль"
                except Exception as e:
                    return None, f"Ошибка: {str(e)}"

        try:
            if isinstance(result, float):
                if result.is_integer():
                    result_str = str(int(result))
                else:
                    result_str = f"{result:.10g}"
                    result_str = round_number(result_str.replace('.', ','), 4)
                    if '.' in result_str:
                        result_str = result_str.replace('.', ',')
            else:
                result_str = str(result)
            result_str = format_number(result_str)
            return result_str, None
        except Exception as e:
            return None, f"Ошибка: {str(e)}"

    def calculate(self):
        current_text = self.input_field.text().strip()
        if self.is_result_displayed:
            if current_text == self.last_result and '=' not in current_text:
                return
            if '=' in current_text:
                parts = current_text.split('=', 1)
                expr_part = parts[0].strip()
                if expr_part == self.last_expression:
                    self.processing_operator = True
                    self.input_field.setText(self.last_result)
                    self.is_result_displayed = False
                    self.last_text = self.last_result
                    self.input_field.setCursorPosition(len(self.last_result))
                    self.processing_operator = False
                    return
        if '=' in current_text:
            parts = current_text.split('=', 1)
            if len(parts) == 2:
                expr_to_eval = parts[0].strip()
                result, error = self._safe_eval(expr_to_eval)
                if result and not error:
                    full_text = f"{expr_to_eval}={result}"
                    self.input_field.setText(full_text)
                    self.last_expression = expr_to_eval
                    self.last_result = result
                    self.is_result_displayed = True
                    self.last_text = full_text
                    self._add_to_history(full_text)
                    self.input_field.setCursorPosition(len(full_text))
                    return
                else:
                    self.input_field.setText(error or "Ошибка")
                    self.is_result_displayed = False
                    self.last_text = error or "Ошибка"
                    return
        result, error = self._safe_eval(current_text)
        if result and not error:
            self.last_expression = current_text
            self.last_result = result
            full_text = f"{current_text}={result}"
            self.input_field.setText(full_text)
            self.is_result_displayed = True
            self.last_text = full_text
            self._add_to_history(full_text)
            self.input_field.setCursorPosition(len(full_text))
        else:
            self.input_field.setText(error or "Ошибка")
            self.input_field.setFocus()
            self.input_field.selectAll()
            self.is_result_displayed = False
            self.last_text = error or "Ошибка"

    def navigate_history_down(self):
        if not self.history:
            return
        if self.history_index == -1:
            self.current_input = self.input_field.text()
            self.history_index = 0
        else:
            self.history_index += 1
            if self.history_index >= len(self.history):
                self.history_index = -1
                self.input_field.setText(self.current_input)
                self.input_field.setFocus()
                self.input_field.setCursorPosition(len(self.current_input))
                return
        self.input_field.setText(self.history[len(self.history) - 1 - self.history_index])
        self.input_field.setFocus()
        self.input_field.setCursorPosition(len(self.input_field.text()))

    def navigate_history_up(self):
        if not self.history or self.history_index == -1:
            return
        self.history_index -= 1
        if self.history_index < 0:
            self.history_index = -1
            self.input_field.setText(self.current_input)
            self.input_field.setFocus()
            self.input_field.setCursorPosition(len(self.current_input))
            return
        self.input_field.setText(self.history[len(self.history) - 1 - self.history_index])
        self.input_field.setFocus()
        self.input_field.setCursorPosition(len(self.input_field.text()))

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self.hide_to_tray()
            return
        if key == Qt.Key_Down:
            self.navigate_history_down()
            return
        elif key == Qt.Key_Up:
            self.navigate_history_up()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton and self.drag_pos is not None:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()

    def closeEvent(self, event: QCloseEvent):
        self._save_settings()
        self.hide()
        event.ignore()

    def hideEvent(self, event):
        # ← ← ← ИСПРАВЛЕНИЕ: сброс флага при скрытии окна
        self._pending_toggle = False
        super().hideEvent(event)

    def showEvent(self, event):
        self.input_field.setFocus()
        if not self.is_result_displayed:
            self.input_field.selectAll()
        self.history_index = -1
        self.current_input = ""
        self._pending_toggle = False  # ← ← ← сброс флага при показе
        super().showEvent(event)


class CalcTrayApp(QWidget):
    _sig_toggle = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.running = True
        self.calc_hotkey_enabled = True
        self._last_toggle = 0.0

        self.calc_window = MiniCalcWindow()
        self.calc_window._sig_toggle.connect(self._do_toggle)

        self._load_settings()
        self._build_tray()
        set_numlock_on()

        self.numlock_timer = QTimer()
        self.numlock_timer.setInterval(1000)
        self.numlock_timer.timeout.connect(self._check_numlock)
        self.numlock_timer.start()

    def _load_settings(self):
        if not CONFIG_FILE.exists():
            return
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            self.calc_hotkey_enabled = bool(data.get("calc_hotkey_enabled", True))
        except Exception:
            pass

    def _save_settings(self):
        data = {"calc_hotkey_enabled": self.calc_hotkey_enabled}
        try:
            CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _check_numlock(self):
        if self.running:
            set_numlock_on()

    def _icon(self):
        return load_embedded_icon()

    def _menu_css(self):
        return (
            "QMenu { background:#1e1e1e; color:#eee; border:1px solid rgba(255,255,255,55); }"
            "QMenu::item:selected { background:rgba(255,255,255,35); }"
            "QMenu::separator { height:1px; background:rgba(255,255,255,40); margin:4px 8px; }"
        )

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self._icon(), self)
        self.tray.setToolTip(APP_NAME)

        menu = QMenu()
        menu.setStyleSheet(self._menu_css())

        act_show = QAction("Показать / скрыть калькулятор", self)
        act_show.triggered.connect(self._do_toggle)
        menu.addAction(act_show)

        menu.addSeparator()

        self.autostart_action = QAction("Автозагрузка", self)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(is_autostart_enabled())
        self.autostart_action.triggered.connect(self._toggle_autostart)
        menu.addAction(self.autostart_action)

        menu.addSeparator()

        act_about = QAction("О программе…", self)
        act_about.triggered.connect(lambda: AboutDialog().exec_())
        menu.addAction(act_about)

        act_exit = QAction("Выход", self)
        act_exit.triggered.connect(self._exit)
        menu.addAction(act_exit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.Context):
            self.autostart_action.setChecked(is_autostart_enabled())
            self.tray.contextMenu().popup(QtGui.QCursor.pos())

    def _toggle_autostart(self):
        if is_autostart_enabled():
            if remove_from_autostart():
                self.autostart_action.setChecked(False)
                QMessageBox.information(self, APP_NAME, "Программа удалена из автозагрузки.")
            else:
                QMessageBox.warning(self, APP_NAME, "Не удалось удалить программу из автозагрузки.")
                self.autostart_action.setChecked(True)
        else:
            if add_to_autostart():
                self.autostart_action.setChecked(True)
                QMessageBox.information(
                    self, APP_NAME, f"Программа добавлена в автозагрузку.\nЯрлык создан в:\n{get_shortcut_path()}")
            else:
                QMessageBox.warning(
                    self, APP_NAME,
                    "Не удалось добавить программу в автозагрузку.\nПроверьте права доступа к папке автозагрузки.")
                self.autostart_action.setChecked(False)

    def _exit(self):
        self.running = False
        try:
            self.numlock_timer.stop()
        except Exception:
            pass
        self.calc_window.close()
        self.tray.hide()
        QApplication.quit()

    def _do_mouse_toggle(self):
        window = self.calc_window
        if window.isVisible():
            window.hide_to_tray()
        else:
            window.show()
            window.raise_()
            window.activateWindow()
            window.input_field.setFocus()
            if not window.is_result_displayed:
                window.input_field.selectAll()

    def _do_toggle(self):
        window = self.calc_window
        if not window.isVisible():
            set_programmatic_flag(True)  # ← Блокируем проверку
            window.show()
            window.raise_()
            window.activateWindow()
            window.input_field.setFocus()
            window.input_field.selectAll()
            # ← ← ← УБРАНО: QTimer.singleShot(...) — теперь флаг сбрасывается в hideEvent
        else:
            if window.isActiveWindow():
                window._save_settings()
                window.hide()
            else:
                window.raise_()
                window.activateWindow()
                window.input_field.setFocus()
                if not window.is_result_displayed:
                    window.input_field.selectAll()


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"О программе — {APP_NAME}")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setFixedWidth(340)
        self.setFixedHeight(180)
        self.setStyleSheet(
            "QDialog { background:#1e1e1e; color:#eee; } QLabel { color:#eee; } QPushButton { background:#2a2a2a; color:#eee; border:1px solid #555; padding:5px 18px; } QPushButton:hover { background:#383838; }")
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(22, 22, 22, 22)

        lbl = QLabel(f"<b>{APP_NAME}</b>&nbsp;&nbsp;v{APP_VERSION}")
        lbl.setStyleSheet("font-size:18px; color:#fff;")
        lay.addWidget(lbl, alignment=Qt.AlignCenter)

        desc = QLabel(
            "Создатель: d_e_m_e_k<br>"
            "На основе кода Андрей Кудлай<br>"
            '<a href="https://github.com/Akudlay-ru/CalcNumLock" style="color:#4a90e2; text-decoration:none;">GitHub: CalcNumLock</a>'
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setOpenExternalLinks(True)
        desc.setStyleSheet("color:#ccc; font-size:13px;")
        lay.addWidget(desc)

        btn = QPushButton("Закрыть")
        btn.clicked.connect(self.close)
        btn.setFixedWidth(100)
        lay.addWidget(btn, alignment=Qt.AlignCenter)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    try:
        app.setWindowIcon(load_embedded_icon())
    except Exception:
        pass

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "Системный трей недоступен.")
        sys.exit(1)

    tray_app = CalcTrayApp()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
