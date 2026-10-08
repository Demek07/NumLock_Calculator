#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CalcNumLock — миникалькулятор по NumLock
=======================================================================
Версия: 4.6

Функционал:
  • NumLock — показать / скрыть миникалькулятор
  • NumLock всегда включен (принудительно, без влияния на окно)
  • Однострочный ввод выражений (+, -, *, /, %, **)
  • Поддержка десятичной запятой (автозамена на точку)
  • Разрядность чисел (разделение тысяч пробелом)
  • Округление до 4 знаков после запятой
  • Результат вычисляется при нажатии Enter
  • Формат вывода: выражение=результат
  • После вычисления текст выделяется — ввод цифры заменяет всё
  • Enter фиксирует результат (снимает выделение, отключает замену)
  • После фиксации цифры дописываются к результату, оператор — тоже
  • При вводе оператора после «свежего» результата — результат + оператор
  • История вычислений (сохраняется в файл)
  • Навигация по истории: стрелки вверх/вниз
  • Кнопка истории рядом с полем ввода
  • Без шапки окна, все элементы в одной строке
  • Позиция окна запоминается
  • Окно сворачивается в трей, а не закрывается
  • Добавление в автозагрузку Windows
"""

import ctypes
import base64
import json
import sys
import time
import re
from pathlib import Path

import keyboard

# Убираем консольное окно pyw.exe
try:
    ctypes.windll.kernel32.FreeConsole()
except Exception:
    pass

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, QTimer, QPoint, QEvent
from PyQt5.QtGui import QGuiApplication, QCloseEvent, QMouseEvent
from PyQt5.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QAction,
    QWidget, QDialog, QPushButton, QMessageBox,
    QLineEdit, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem
)

# Импорт иконки из отдельного файла
from numlockcalc_icon import ICON_B64

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
APP_NAME = "NumLockCalc"
APP_VERSION = "4.6"

DATA_DIR_NAME = "_calcnumlock_data"


def get_app_root() -> Path:
    """Папка, где лежит exe (после сборки PyInstaller) или сам .pyw."""
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

# WinAPI константы для NumLock
VK_NUMLOCK = 0x90
KEYEVENTF_KEYUP = 0x0002

# WinAPI для форсирования фокуса
SW_RESTORE = 9

# Получаем доступ к WinAPI
user32 = ctypes.windll.user32
GetKeyState = user32.GetKeyState
keybd_event = user32.keybd_event
SetForegroundWindow = user32.SetForegroundWindow
ShowWindow = user32.ShowWindow


def load_embedded_icon() -> QtGui.QIcon:
    """Загружает иконку из вшитого base64."""
    try:
        raw = base64.b64decode(ICON_B64)
        pix = QtGui.QPixmap()
        if pix.loadFromData(raw, "ICO"):
            return QtGui.QIcon(pix)
    except Exception:
        pass
    pix = QtGui.QPixmap(32, 32)
    pix.fill(QtGui.QColor("#0078d7"))
    return QtGui.QIcon(pix)


def is_numlock_on() -> bool:
    try:
        return bool(GetKeyState(VK_NUMLOCK) & 1)
    except Exception:
        return False


_programmatic_numlock = False


def set_numlock_on():
    """Принудительно включает NumLock, если выключен."""
    global _programmatic_numlock
    try:
        if not is_numlock_on():
            _programmatic_numlock = True
            keybd_event(VK_NUMLOCK, 0, 0, 0)
            keybd_event(VK_NUMLOCK, 0, KEYEVENTF_KEYUP, 0)
            QTimer.singleShot(50, lambda: set_programmatic_flag(False))
    except Exception:
        pass


def set_programmatic_flag(value: bool):
    global _programmatic_numlock
    _programmatic_numlock = value


def is_programmatic_numlock() -> bool:
    global _programmatic_numlock
    return _programmatic_numlock


def force_foreground(hwnd: int):
    """Принудительно выводит окно на передний план через AttachThreadInput."""
    try:
        if not hwnd:
            return
        fg = user32.GetForegroundWindow()
        cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        tgt_thread = user32.GetWindowThreadProcessId(hwnd, None)

        attached = []
        if fg_thread and fg_thread != cur_thread:
            if user32.AttachThreadInput(fg_thread, cur_thread, True):
                attached.append(fg_thread)
        if tgt_thread and tgt_thread != cur_thread:
            if user32.AttachThreadInput(tgt_thread, cur_thread, True):
                attached.append(tgt_thread)

        ShowWindow(hwnd, SW_RESTORE)
        SetForegroundWindow(hwnd)

        for th in attached:
            try:
                user32.AttachThreadInput(th, cur_thread, False)
            except Exception:
                pass
    except Exception:
        pass


def format_number(num_str: str) -> str:
    """Форматирует число с разделением разрядов пробелами."""
    if not num_str:
        return num_str
    if 'e' in num_str.lower():
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
        int_part = parts[0]
        frac_part = ',' + parts[1] if len(parts) > 1 else ''
    elif '.' in num_str:
        parts = num_str.split('.')
        int_part = parts[0]
        frac_part = '.' + parts[1] if len(parts) > 1 else ''
    else:
        int_part = num_str
        frac_part = ''

    if int_part.startswith('-'):
        sign = '-'
        int_part = int_part[1:]
    else:
        sign = ''

    if not int_part or int_part == '0':
        formatted_int = '0'
    else:
        int_part = int_part.lstrip('0') or '0'
        groups = []
        for i in range(len(int_part), 0, -3):
            start = max(0, i - 3)
            groups.insert(0, int_part[start:i])
        formatted_int = ' '.join(groups)

    return sign + formatted_int + frac_part


def round_number(num_str: str, decimals: int = 4) -> str:
    """Округляет число до указанного количества знаков после запятой."""
    if not num_str:
        return num_str
    try:
        num = float(num_str.replace(',', '.'))
    except ValueError:
        return num_str

    rounded = round(num, decimals)

    if rounded.is_integer():
        result = str(int(rounded))
    else:
        result = f"{rounded:.{decimals}f}".rstrip('0').rstrip('.')
        result = result.replace('.', ',')

    return result


# -----------------------------------------------------------------------
# Автозагрузка
# -----------------------------------------------------------------------
def get_startup_folder() -> Path:
    try:
        return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    except Exception:
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x19, None, 0, buf)
        return Path(buf.value) / "Programs" / "Startup"


def get_shortcut_path() -> Path:
    return get_startup_folder() / "NumLockCalc.lnk"


def is_autostart_enabled() -> bool:
    try:
        return get_shortcut_path().exists()
    except Exception:
        return False


def add_to_autostart() -> bool:
    try:
        import win32com.client
    except ImportError:
        print("[ERROR] pywin32 not installed. Please run: pip install pywin32")
        return False

    try:
        startup_folder = get_startup_folder()
        shortcut_path = get_shortcut_path()
        startup_folder.mkdir(parents=True, exist_ok=True)

        if getattr(sys, 'frozen', False):
            target = sys.executable
            working_dir = str(APP_ROOT)
        else:
            python_dir = Path(sys.executable).parent
            pythonw = python_dir / "pythonw.exe"
            target = str(pythonw if pythonw.exists() else sys.executable)
            working_dir = str(APP_ROOT)

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.TargetPath = target
        shortcut.WorkingDirectory = working_dir
        shortcut.Description = APP_NAME
        shortcut.save()
        return True
    except Exception as e:
        print(f"[ERROR] add_to_autostart: {e}")
        import traceback
        traceback.print_exc()
        return False


def remove_from_autostart() -> bool:
    try:
        shortcut_path = get_shortcut_path()
        if shortcut_path.exists():
            shortcut_path.unlink()
            return True
        return False
    except Exception as e:
        print(f"[ERROR] remove_from_autostart: {e}")
        return False


# ---------------------------------------------------------------------------
# Диалог истории
# ---------------------------------------------------------------------------
class HistoryDialog(QDialog):
    def __init__(self, history_list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("История вычислений")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.setMinimumSize(400, 300)

        self.setStyleSheet("""
            QDialog { background: #eee; color: #000000; }
            QListWidget {
                background: #eee; color: #000000;
                border: 2px solid #0078d7; border-radius: 4px;
                font-family: Arial, sans-serif; font-weight: bold;
                font-size: 13px; padding: 5px;
            }
            QListWidget::item { padding: 4px 8px; border-bottom: 1px solid #0078d7; }
            QListWidget::item:selected { background: #0078d7; color: white; }
            QPushButton {
                background: #eee; color: #000000;
                border: 1px solid #0078d7; border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover { background: #0078d7; }
            QLabel { color: #aaa; }
        """)

        self.history_list = history_list
        self.selected_item = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 16)
        layout.setSpacing(8)

        title = QLabel(f"История ({len(history_list)} записей)")
        title.setStyleSheet("font-size: 14px; color: #eee;")
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        for item in reversed(history_list):
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        btn_clear = QPushButton("Очистить историю")
        btn_clear.clicked.connect(self.clear_history)
        btn_layout.addWidget(btn_clear)
        btn_layout.addStretch()
        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def on_item_double_clicked(self, item):
        self.selected_item = item.text()
        self.accept()

    def clear_history(self):
        reply = QMessageBox.question(
            self, "Очистка истории",
            "Удалить все записи из истории?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.list_widget.clear()
            self.history_list.clear()
            self.selected_item = None
            self.accept()


# ---------------------------------------------------------------------------
# Кастомный QLineEdit
# ---------------------------------------------------------------------------
class CalcLineEdit(QLineEdit):
    """
    keyPressEvent:
      • _pending_clear == True (результат свежий, выделен):
          - цифра / Backspace / Delete / прочие печатные → clear_input + ввод
          - оператор (+, -, *, /, %, ^) → восстановить полный текст,
            пропустить символ — on_text_changed обработает как результат+оператор
      • _pending_clear == False — обычная обработка
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self._pending_clear = False

    def keyPressEvent(self, event):
        key = event.key()

        if self._pending_clear and self.parent_window:
            modifiers = (
                Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta,
                Qt.Key_CapsLock, Qt.Key_NumLock, Qt.Key_ScrollLock,
                Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right,
                Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown,
                Qt.Key_Insert,
                Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter,
                Qt.Key_Tab,
            )
            is_function = Qt.Key_F1 <= key <= Qt.Key_F35

            operator_chars = {
                Qt.Key_Plus, Qt.Key_Minus, Qt.Key_Asterisk,
                Qt.Key_Slash, Qt.Key_Percent, Qt.Key_AsciiCircum,
            }

            # Оператор на свежем результате — восстановить текст, пропустить символ
            if key in operator_chars and self.parent_window.is_result_displayed:
                self.parent_window.restore_result_text()
                self._pending_clear = False
                super().keyPressEvent(event)
                return

            # Всё остальное печатное и Backspace/Delete — очищают поле
            if key in (Qt.Key_Backspace, Qt.Key_Delete) or (
                key not in modifiers and not is_function
            ):
                self.parent_window.clear_input()
                self._pending_clear = False
                if key in (Qt.Key_Backspace, Qt.Key_Delete):
                    event.accept()
                    return
                super().keyPressEvent(event)
                return

        super().keyPressEvent(event)

    def set_pending_clear(self, value):
        self._pending_clear = value


# ---------------------------------------------------------------------------
# Окно миникалькулятора
# ---------------------------------------------------------------------------
class MiniCalcWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Калькулятор")
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Window
        )
        self.setFixedWidth(400)
        self.setFixedHeight(38)

        try:
            self.setWindowIcon(load_embedded_icon())
        except Exception:
            pass

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(3)

        # ☰ — перетаскивание
        self.drag_label = QLabel("☰")
        self.drag_label.setFixedWidth(26)
        self.drag_label.setStyleSheet("""
            QLabel {
                color: #888; font-size: 15px; padding: 4px 4px;
                background: transparent; font-weight: bold;
            }
            QLabel:hover { color: #0078d7; }
        """)
        self.drag_label.setAlignment(Qt.AlignCenter)
        self.drag_label.mousePressEvent = self.mousePressEvent
        self.drag_label.mouseMoveEvent = self.mouseMoveEvent
        main_layout.addWidget(self.drag_label)

        # Поле ввода
        self.input_field = CalcLineEdit(self)
        self.input_field.setPlaceholderText("Введите выражение (например, 2,2+3,8)")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: #eee; color: #000000;
                border: 2px solid #0078d7; border-radius: 4px;
                padding: 3px 10px;
                font-size: 13px; font-family: Arial, sans-serif;
                font-weight: bold;
                selection-background-color: #0078d7;
            }
            QLineEdit:focus { border: 3px solid #0078d7; }
        """)
        self.input_field.returnPressed.connect(self.calculate)
        self.input_field.textChanged.connect(self.on_text_changed)
        main_layout.addWidget(self.input_field, 1)

        # История
        self.btn_history = QPushButton("📋")
        self.btn_history.setFixedSize(26, 26)
        self.btn_history.setStyleSheet("""
            QPushButton {
                background: transparent; color: #888;
                border: none; font-size: 13px;
                padding: 0px; border-radius: 4px;
            }
            QPushButton:hover { color: #eee; background: #0078d7; }
        """)
        self.btn_history.clicked.connect(self.show_history)
        main_layout.addWidget(self.btn_history)

        # Закрыть
        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(26, 26)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: transparent; color: #888;
                border: none; font-size: 13px;
                padding: 0px; border-radius: 4px;
            }
            QPushButton:hover { color: #fff; background: #c42b2b; }
        """)
        self.btn_close.clicked.connect(self.hide_to_tray)
        main_layout.addWidget(self.btn_close)

        # Состояние
        self.last_result = None
        self.last_expression = None
        self.is_result_displayed = False
        self.last_text = ""
        self.processing_operator = False
        self._suppress_text_changed = False
        self._cleared_once = False
        self._select_pending = False

        # История
        self.history = []
        self.history_index = -1
        self.current_input = ""
        self._load_history()

        # Перетаскивание
        self.drag_pos = None

        # Позиция
        self.session_pos = None
        self._load_settings()

        # Переиспользуемый таймер для отложенного выделения
        self._select_timer = QTimer(self)
        self._select_timer.setSingleShot(True)
        self._select_timer.setInterval(0)
        self._select_timer.timeout.connect(self._apply_selection_now)

    # ------------------------------------------------------------------
    # Настройки
    # ------------------------------------------------------------------
    def _load_settings(self):
        if not CONFIG_FILE.exists():
            return
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            sp = data.get("window_pos")
            if isinstance(sp, list) and len(sp) == 2:
                self.session_pos = tuple(sp)
                self.move(sp[0], sp[1])
        except Exception:
            pass

    def _save_settings(self):
        data = {}
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data["window_pos"] = [self.x(), self.y()]
        try:
            CONFIG_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # История
    # ------------------------------------------------------------------
    def _load_history(self):
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except Exception:
                self.history = []
        else:
            self.history = []

    def _save_history(self):
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.history[-100:], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _add_to_history(self, text: str):
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
            self._suppress_text_changed = True
            self.input_field.setText(dialog.selected_item)
            self._suppress_text_changed = False
            self.input_field.setFocus()
            self.input_field.setCursorPosition(len(dialog.selected_item))
            if '=' in dialog.selected_item:
                parts = dialog.selected_item.split('=', 1)
                if len(parts) == 2:
                    self.last_expression = parts[0].strip()
                    self.last_result = parts[1].strip()
                    self.is_result_displayed = True
                    self.last_text = dialog.selected_item
                    self.input_field.set_pending_clear(True)
                    self._select_pending = True
                    self._select_timer.start()
            else:
                self.is_result_displayed = False
                self.last_text = dialog.selected_item
                self.input_field.set_pending_clear(False)

    def hide_to_tray(self):
        self._save_settings()
        self.hide()

    def _apply_selection_now(self):
        """Безопасное отложенное выделение — без raise/activateWindow."""
        try:
            f = self.input_field
            if f is None:
                return
            f.setFocus(Qt.OtherFocusReason)
            f.selectAll()
        except (RuntimeError, AttributeError):
            pass

    # ------------------------------------------------------------------
    # Восстановление полного текста результата (для операторов)
    # ------------------------------------------------------------------
    def restore_result_text(self):
        """
        Вызывается при вводе оператора на «свежем» результате.
        Восстанавливает 'выражение=результат' и сбрасывает флаг
        запланированного выделения, чтобы следующий textChanged
        (от дописанного оператора) отработал штатно.
        """
        if self.last_expression and self.last_result:
            full = f"{self.last_expression}={self.last_result}"
            self._select_pending = False
            self._suppress_text_changed = True
            self.input_field.setText(full)
            self._suppress_text_changed = False
            self.last_text = full
            self.input_field.setCursorPosition(len(full))

    # ------------------------------------------------------------------
    # Обработка изменения текста
    # ------------------------------------------------------------------
    def on_text_changed(self, text: str):
        if self._suppress_text_changed:
            return
        if self.processing_operator:
            return

        # Если запланировано выделение — применим его в следующий тик
        if self._select_pending:
            self._select_pending = False
            self._select_timer.start()
            return

        if not self.is_result_displayed:
            self.last_text = text
            return

        if text == self.last_text:
            return

        if not text:
            self.is_result_displayed = False
            self.last_text = text
            return

        cursor_pos = self.input_field.cursorPosition()

        # Добавление оператора после результата — результат + оператор
        if len(text) > len(self.last_text):
            added = text[len(self.last_text):]
            if added in '+-*/%^' and self.last_result is not None:
                self.processing_operator = True
                new_text = f"{self.last_result}{added}"
                self._suppress_text_changed = True
                self.input_field.setText(new_text)
                self._suppress_text_changed = False
                self.is_result_displayed = False
                self.last_text = new_text
                self.input_field.setCursorPosition(len(new_text))
                self.processing_operator = False
                return

        # Результат зафиксирован (Enter, _pending_clear = False) —
        # пользователь редактирует его как обычный текст.
        if not self.input_field._pending_clear:
            self.is_result_displayed = False
            self.last_text = text
            return

        if '=' in text:
            eq_pos = text.rfind('=')
            if eq_pos < len(text) - 1:
                text_without_result = text[:eq_pos]
                self.processing_operator = True
                self._suppress_text_changed = True
                self.input_field.setText(text_without_result)
                self._suppress_text_changed = False
                self.is_result_displayed = False
                self.last_text = text_without_result
                self.input_field.setCursorPosition(cursor_pos)
                self.processing_operator = False
                return

        if '=' not in text:
            self.processing_operator = True
            if self.last_expression:
                self._suppress_text_changed = True
                self.input_field.setText(self.last_expression)
                self._suppress_text_changed = False
                self.is_result_displayed = False
                self.last_text = self.last_expression
                if cursor_pos > len(self.last_expression):
                    cursor_pos = len(self.last_expression)
                self.input_field.setCursorPosition(cursor_pos)
            self.processing_operator = False
            return

        self.last_text = text

    # ------------------------------------------------------------------
    # Нормализация и вычисление
    # ------------------------------------------------------------------
    def _normalize_expression(self, expression: str) -> str:
        if not expression:
            return expression

        result = []
        i = 0
        length = len(expression)

        while i < length:
            ch = expression[i]

            if ch == ' ':
                if 0 < i < length - 1:
                    prev = expression[i - 1]
                    next_ch = expression[i + 1]
                    if prev.isdigit() and next_ch.isdigit():
                        i += 1
                        continue
                result.append(ch)
            elif ch == ',':
                if 0 < i < length - 1:
                    prev = expression[i - 1]
                    next_ch = expression[i + 1]
                    if prev.isdigit() and next_ch.isdigit():
                        result.append('.')
                        i += 1
                        continue
                result.append(ch)
            elif ch == '^':
                result.append('**')
            else:
                result.append(ch)
            i += 1

        return ''.join(result)

    def _safe_eval(self, expression: str):
        if not expression or not expression.strip():
            return None, ""

        expr = expression.strip()
        expr = self._normalize_expression(expr)

        if len(expr) > 500:
            return None, "Ошибка: выражение слишком длинное"

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
                num = float(match2.group(1))
                result = num / 100
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

    # ------------------------------------------------------------------
    # Вычисление по Enter
    # ------------------------------------------------------------------
    def calculate(self):
        current_text = self.input_field.text().strip()
        if not current_text:
            return

        # --- Уже показан результат ---
        if self.is_result_displayed:
            # Чистый результат (без '='), нажат Enter → фиксируем
            if current_text == self.last_result and '=' not in current_text:
                self.input_field.deselect()
                self.input_field.set_pending_clear(False)
                self.input_field.setCursorPosition(len(current_text))
                self.last_text = current_text
                self._select_pending = False
                return

            # Есть '=', нажат Enter → оставляем только результат
            if '=' in current_text:
                parts = current_text.split('=', 1)
                expr_part = parts[0].strip()
                if expr_part == self.last_expression:
                    self.processing_operator = True
                    self._suppress_text_changed = True
                    self.input_field.setText(self.last_result)
                    self._suppress_text_changed = False
                    self.is_result_displayed = True
                    self.last_text = self.last_result
                    self.input_field.setCursorPosition(len(self.last_result))
                    self.processing_operator = False
                    self.input_field.deselect()
                    self.input_field.set_pending_clear(False)
                    self._select_pending = False
                    return

        # --- Есть '=' в тексте, но не в режиме результата ---
        if '=' in current_text:
            parts = current_text.split('=', 1)
            if len(parts) == 2:
                expr_to_eval = parts[0].strip()
                result, error = self._safe_eval(expr_to_eval)
                if result and not error:
                    full_text = f"{expr_to_eval}={result}"
                    self._suppress_text_changed = True
                    self.input_field.setText(full_text)
                    self._suppress_text_changed = False
                    self.last_expression = expr_to_eval
                    self.last_result = result
                    self.is_result_displayed = True
                    self.last_text = full_text
                    self._add_to_history(full_text)
                    self.input_field.setFocus()
                    self.input_field.set_pending_clear(True)
                    self._select_pending = True
                    self._select_timer.start()
                    return
                else:
                    self._suppress_text_changed = True
                    self.input_field.setText(error or "Ошибка")
                    self._suppress_text_changed = False
                    self.is_result_displayed = False
                    self.last_text = error or "Ошибка"
                    self.input_field.setFocus()
                    self.input_field.set_pending_clear(False)
                    self._select_pending = True
                    self._select_timer.start()
                    return

        # --- Обычное вычисление ---
        result, error = self._safe_eval(current_text)
        if result and not error:
            self.last_expression = current_text
            self.last_result = result
            full_text = f"{current_text}={result}"
            self._suppress_text_changed = True
            self.input_field.setText(full_text)
            self._suppress_text_changed = False
            self.is_result_displayed = True
            self.last_text = full_text
            self._add_to_history(full_text)
            self.input_field.setFocus()
            self.input_field.set_pending_clear(True)
            self._select_pending = True
            self._select_timer.start()
        else:
            self._suppress_text_changed = True
            self.input_field.setText(error or "Ошибка")
            self._suppress_text_changed = False
            self.is_result_displayed = False
            self.last_text = error or "Ошибка"
            self.input_field.setFocus()
            self.input_field.set_pending_clear(False)
            self._select_pending = True
            self._select_timer.start()

    def clear_input(self):
        """Полная очистка поля и сброс состояния."""
        self._suppress_text_changed = True
        self.last_result = None
        self.last_expression = None
        self.is_result_displayed = False
        self.last_text = ""
        self.processing_operator = False
        self.history_index = -1
        self.current_input = ""
        self._select_pending = False
        self.input_field._pending_clear = False
        self.input_field.clear()
        self._suppress_text_changed = False
        self.input_field.setFocus()
        self._cleared_once = False

    # ------------------------------------------------------------------
    # Клавиши окна
    # ------------------------------------------------------------------
    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key_Escape:
            if not self._cleared_once:
                self.clear_input()
                self._cleared_once = True
            else:
                self.hide_to_tray()
            return

        if key == Qt.Key_Down:
            self.navigate_history_down()
            return
        elif key == Qt.Key_Up:
            self.navigate_history_up()
            return

        super().keyPressEvent(event)

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
                self._suppress_text_changed = True
                self.input_field.setText(self.current_input)
                self._suppress_text_changed = False
                self.input_field.setFocus()
                self.input_field.setCursorPosition(len(self.current_input))
                return

        self._suppress_text_changed = True
        self.input_field.setText(self.history[len(self.history) - 1 - self.history_index])
        self._suppress_text_changed = False
        self.input_field.setFocus()
        self.input_field.setCursorPosition(len(self.input_field.text()))

    def navigate_history_up(self):
        if not self.history or self.history_index == -1:
            return
        self.history_index -= 1
        if self.history_index < 0:
            self.history_index = -1
            self._suppress_text_changed = True
            self.input_field.setText(self.current_input)
            self._suppress_text_changed = False
            self.input_field.setFocus()
            self.input_field.setCursorPosition(len(self.current_input))
            return

        self._suppress_text_changed = True
        self.input_field.setText(self.history[len(self.history) - 1 - self.history_index])
        self._suppress_text_changed = False
        self.input_field.setFocus()
        self.input_field.setCursorPosition(len(self.input_field.text()))

    # ------------------------------------------------------------------
    # Перетаскивание
    # ------------------------------------------------------------------
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

    def showEvent(self, event):
        # Флаг замены — по состоянию результата
        if self.is_result_displayed and self.input_field.text():
            self.input_field.set_pending_clear(True)
        else:
            self.input_field.set_pending_clear(False)

        self.input_field.setFocus()
        self._select_pending = True
        self._select_timer.start()

        self.history_index = -1
        self.current_input = ""
        self._cleared_once = False
        super().showEvent(event)


# ---------------------------------------------------------------------------
# Главный класс приложения с треем
# ---------------------------------------------------------------------------
class CalcTrayApp(QWidget):

    _sig_toggle = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()

        self.running = True
        self.calc_hotkey_enabled = True
        self._last_toggle = 0.0

        self.calc_window = MiniCalcWindow()
        self.calc_window.hide()

        self._load_settings()
        self._build_tray()
        self._sig_toggle.connect(self._do_toggle)

        # Принудительно включаем NumLock при старте
        set_numlock_on()

        # Хук NumLock
        try:
            keyboard.on_press(self._on_key)
        except Exception:
            pass

        # Таймер для контроля NumLock
        self.numlock_timer = QTimer()
        self.numlock_timer.setInterval(1000)
        self.numlock_timer.timeout.connect(self._check_numlock)
        self.numlock_timer.start()

    # ------------------------------------------------------------------
    # Настройки
    # ------------------------------------------------------------------
    def _load_settings(self):
        if not CONFIG_FILE.exists():
            return
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            self.calc_hotkey_enabled = bool(data.get("calc_hotkey_enabled", True))
        except Exception:
            pass

    def _save_settings(self):
        data = {}
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data["calc_hotkey_enabled"] = self.calc_hotkey_enabled
        try:
            CONFIG_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def _check_numlock(self):
        """Безусловная проверка — NumLock всегда включён."""
        if self.running:
            set_numlock_on()

    # ------------------------------------------------------------------
    # Трей
    # ------------------------------------------------------------------
    def _icon(self) -> QtGui.QIcon:
        return load_embedded_icon()

    def _menu_css(self) -> str:
        return (
            "QMenu { background:#1e1e1e; color:#eee;"
            "        border:1px solid rgba(255,255,255,55); }"
            "QMenu::item:selected { background:rgba(255,255,255,35); }"
            "QMenu::separator { height:1px;"
            "  background:rgba(255,255,255,40); margin:4px 8px; }"
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
        if reason == QSystemTrayIcon.Trigger:
            self._do_mouse_toggle()
        elif reason == QSystemTrayIcon.Context:
            self.autostart_action.setChecked(is_autostart_enabled())
            self.tray.contextMenu().popup(QtGui.QCursor.pos())

    # ------------------------------------------------------------------
    # Автозагрузка
    # ------------------------------------------------------------------
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
                    self, APP_NAME,
                    "Программа добавлена в автозагрузку.\n"
                    f"Ярлык создан в:\n{get_shortcut_path()}"
                )
            else:
                QMessageBox.warning(
                    self, APP_NAME,
                    "Не удалось добавить программу в автозагрузку.\n"
                    "Проверьте права доступа к папке автозагрузки."
                )
                self.autostart_action.setChecked(False)

    # ------------------------------------------------------------------
    # Выход
    # ------------------------------------------------------------------
    def _exit(self):
        self.running = False
        try:
            self.numlock_timer.stop()
            keyboard.unhook_all()
        except Exception:
            pass
        self.calc_window.close()
        self.tray.hide()
        QApplication.quit()

    # ------------------------------------------------------------------
    # Хук клавиатуры
    # ------------------------------------------------------------------
    def _on_key(self, event):
        if not self.running:
            return
        if event.name != "num lock":
            return
        # Только down — иначе двойное срабатывание
        if getattr(event, "event_type", "down") != "down":
            return

        if is_programmatic_numlock():
            return

        now = time.time()
        if now - self._last_toggle < 0.15:
            return
        self._last_toggle = now

        # emit потокобезопасен — Qt сам поставит вызов в очередь главного потока
        self._sig_toggle.emit()

    # ------------------------------------------------------------------
    # Показ/скрытие
    # ------------------------------------------------------------------
    def _show_calc(self):
        w = self.calc_window
        w.show()
        w.raise_()
        force_foreground(int(w.winId()))
        w.activateWindow()
        w.input_field.setFocus()

        if w.is_result_displayed and w.input_field.text():
            w.input_field.set_pending_clear(True)
        w._select_pending = True
        w._select_timer.start()

    def _do_mouse_toggle(self):
        w = self.calc_window
        if w.isVisible():
            w.hide_to_tray()
        else:
            self._show_calc()

    def _do_toggle(self):
        w = self.calc_window

        if not w.isVisible():
            self._show_calc()
        else:
            if w.isActiveWindow():
                w._save_settings()
                w.hide()
            else:
                w.raise_()
                force_foreground(int(w.winId()))
                w.activateWindow()
                w.input_field.setFocus()
                if w.is_result_displayed and w.input_field.text():
                    w.input_field.set_pending_clear(True)
                w._select_pending = True
                w._select_timer.start()


# ---------------------------------------------------------------------------
# Диалог «О программе»
# ---------------------------------------------------------------------------
class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"О программе — {APP_NAME}")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.setFixedWidth(340)
        self.setFixedHeight(180)
        self.setStyleSheet("""
            QDialog     { background:#eee; color:#000000; }
            QLabel      { color:#aaa; }
            QPushButton { background:#eee; color:#000000;
                          border:1px solid #0078d7; padding:5px 18px; }
            QPushButton:hover { background:#0078d7; }
        """)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(22, 22, 22, 22)

        lbl = QLabel(f"<b>{APP_NAME}</b>&nbsp;&nbsp;v{APP_VERSION}")
        lbl.setStyleSheet("font-size:18px; color:#000000;")
        lay.addWidget(lbl, alignment=Qt.AlignCenter)

        desc = QLabel(
            "Создатель: d_e_m_e_k<br>"
            "На основе кода Андрей Кудлай<br>"
            'GitHub: <a href="https://github.com/Akudlay-ru/CalcNumLock" style="color:#4a90e2; text-decoration:none;">CalcNumLock</a>'
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setOpenExternalLinks(True)
        desc.setStyleSheet("color:#000000; font-size:13px;")
        lay.addWidget(desc)

        btn = QPushButton("Закрыть")
        btn.clicked.connect(self.close)
        btn.setFixedWidth(100)
        lay.addWidget(btn, alignment=Qt.AlignCenter)


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
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