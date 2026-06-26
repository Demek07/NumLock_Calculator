#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CalcNumLock — миникалькулятор по NumLock
=======================================================================
Версия: 4.2

Функционал:
  • NumLock — показать / скрыть миникалькулятор
  • NumLock всегда включен (принудительно, без влияния на окно)
  • Однострочный ввод выражений (+, -, *, /, %, **)
  • Поддержка десятичной запятой (автозамена на точку)
  • Разрядность чисел (разделение тысяч пробелом)
  • Округление до 4 знаков после запятой
  • Результат вычисляется при нажатии Enter
  • Формат вывода: выражение=результат
  • Повторный Enter оставляет только результат
  • При вводе оператора после результата - результат + оператор
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
import os
import subprocess
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
from numlockcalc_icon8 import ICON_B64

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
APP_NAME = "CalcNumLock"
APP_VERSION = "4.2"

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

# Получаем доступ к WinAPI
user32 = ctypes.windll.user32
GetKeyState = user32.GetKeyState
keybd_event = user32.keybd_event


def load_embedded_icon() -> QtGui.QIcon:
    """Загружает иконку из вшитого base64."""
    try:
        raw = base64.b64decode(ICON_B64)
        pix = QtGui.QPixmap()
        if pix.loadFromData(raw, "ICO"):
            return QtGui.QIcon(pix)
    except Exception:
        pass
    # Фоллбэк — синий квадрат
    pix = QtGui.QPixmap(32, 32)
    pix.fill(QtGui.QColor("#0078d7"))
    return QtGui.QIcon(pix)


def is_numlock_on() -> bool:
    """Проверяет, включен ли NumLock."""
    try:
        return bool(GetKeyState(VK_NUMLOCK) & 1)
    except Exception:
        return False


# Глобальный флаг для отслеживания программного нажатия NumLock
_programmatic_numlock = False


def set_numlock_on():
    """Принудительно включает NumLock без генерации дополнительных событий."""
    global _programmatic_numlock
    try:
        if not is_numlock_on():
            _programmatic_numlock = True
            # Имитируем нажатие NumLock
            keybd_event(VK_NUMLOCK, 0, 0, 0)
            keybd_event(VK_NUMLOCK, 0, KEYEVENTF_KEYUP, 0)
            # Сбрасываем флаг через минимальную задержку
            QTimer.singleShot(50, lambda: set_programmatic_flag(False))
    except Exception:
        pass


def set_programmatic_flag(value: bool):
    """Устанавливает флаг программного нажатия."""
    global _programmatic_numlock
    _programmatic_numlock = value


def is_programmatic_numlock() -> bool:
    """Проверяет, является ли текущее нажатие программным."""
    global _programmatic_numlock
    return _programmatic_numlock


def format_number(num_str: str) -> str:
    """
    Форматирует число с разделением разрядов пробелами.
    Поддерживает целые числа и числа с плавающей точкой.
    """
    if not num_str:
        return num_str

    # Проверяем, является ли строка числом
    try:
        # Пробуем преобразовать в число
        if ',' in num_str:
            # Если есть запятая, пробуем как число с плавающей точкой
            float(num_str.replace(',', '.'))
        else:
            float(num_str)
    except ValueError:
        return num_str

    # Разделяем целую и дробную части
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

    # Форматируем целую часть с разделением тысяч
    if int_part.startswith('-'):
        sign = '-'
        int_part = int_part[1:]
    else:
        sign = ''

    # Если целая часть пустая или состоит только из нулей
    if not int_part or int_part == '0':
        formatted_int = '0'
    else:
        # Удаляем ведущие нули
        int_part = int_part.lstrip('0') or '0'
        # Разделяем на группы по 3 цифры справа налево
        groups = []
        for i in range(len(int_part), 0, -3):
            start = max(0, i - 3)
            groups.insert(0, int_part[start:i])
        formatted_int = ' '.join(groups)

    return sign + formatted_int + frac_part


def round_number(num_str: str, decimals: int = 4) -> str:
    """
    Округляет число до указанного количества знаков после запятой.
    """
    if not num_str:
        return num_str

    # Проверяем, является ли строка числом
    try:
        # Заменяем запятую на точку для преобразования
        num = float(num_str.replace(',', '.'))
    except ValueError:
        return num_str

    # Округляем
    rounded = round(num, decimals)

    # Форматируем результат
    if rounded.is_integer():
        result = str(int(rounded))
    else:
        # Преобразуем в строку с нужным количеством знаков
        result = f"{rounded:.{decimals}f}".rstrip('0').rstrip('.')
        # Заменяем точку на запятую
        result = result.replace('.', ',')

    return result

# -----------------------------------------------------------------------
# Функции для автозагрузки (без winshell — работает в .py и .exe)
# -----------------------------------------------------------------------


def get_startup_folder() -> Path:
    """Возвращает путь к папке автозагрузки текущего пользователя."""
    try:
        return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    except Exception:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x19, None, 0, buf)
        return Path(buf.value) / "Programs" / "Startup"


def get_shortcut_path() -> Path:
    startup = get_startup_folder()
    if getattr(sys, 'frozen', False):
        exe_name = Path(sys.executable).name
        shortcut_name = exe_name.replace('.exe', '.lnk')
    else:
        shortcut_name = f"{APP_NAME}.lnk"
    return startup / shortcut_name


def is_autostart_enabled() -> bool:
    try:
        return get_shortcut_path().exists()
    except Exception:
        return False


def add_to_autostart() -> bool:
    try:
        startup_folder = get_startup_folder()
        shortcut_path = get_shortcut_path()

        # Проверяем, существует ли папка
        startup_folder.mkdir(parents=True, exist_ok=True)

        # Определяем целевой файл и параметры
        if getattr(sys, 'frozen', False):
            # Запущено как exe
            target = sys.executable
            working_dir = str(APP_ROOT)
            script = f'''
            $shell = New-Object -ComObject WScript.Shell;
            $shortcut = $shell.CreateShortCut("{shortcut_path}");
            $shortcut.TargetPath = "{target}";
            $shortcut.WorkingDirectory = "{working_dir}";
            $shortcut.Description = "{APP_NAME}";
            $shortcut.Save();
            '''
        else:
            python_dir = Path(sys.executable).parent
            pythonw = python_dir / "pythonw.exe"
            target = str(pythonw if pythonw.exists() else sys.executable)
            script_path = Path(sys.argv[0]).resolve()
            working_dir = str(APP_ROOT)
            script = f'''
            $shell = New-Object -ComObject WScript.Shell;
            $shortcut = $shell.CreateShortCut("{shortcut_path}");
            $shortcut.TargetPath = "{target}";
            $shortcut.Arguments = "{script_path}";
            $shortcut.WorkingDirectory = "{working_dir}";
            $shortcut.Description = "{APP_NAME}";
            $shortcut.Save();
            '''

        # Оборачиваем в try/catch и используем -WindowStyle Hidden
        full_script = f"""
        try {{
            {script}
        }} catch {{
            Write-Error $_.Exception.Message;
            exit 1;
        }}
        exit 0;
        """

        # Запускаем PowerShell без окна
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-WindowStyle", "Hidden",
                "-Command", full_script
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )

        if result.returncode != 0:
            print(f"[ERROR] PowerShell exit code: {result.returncode}")
            if result.stderr:
                print(f"[ERROR] PowerShell stderr: {result.stderr}")
            return False

        return True

    except subprocess.TimeoutExpired:
        print("[ERROR] PowerShell timed out")
        return False
    except Exception as e:
        import traceback
        print(f"[ERROR] add_to_autostart: {e}")
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
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setMinimumSize(400, 300)

        self.setStyleSheet("""
            QDialog {
                background: #eee;
                color: #000000;
            }
            QListWidget {
                background: #eee;
                color: #000000;
                border: 2px solid #0078d7;
                border-radius: 4px;
                font-family: Consolas, monospace;
                font-size: 13px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #0078d7;
            }
            QListWidget::item:selected {
                background: #0078d7;
                color: white;
            }
            QPushButton {
                background: #eee;
                color: #000000;
                border: 1px solid #0078d7;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background: #0078d7;
            }
            QLabel {
                color: #aaa;
            }
        """)

        self.history_list = history_list
        self.selected_item = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 16)
        layout.setSpacing(8)

        # Заголовок
        title = QLabel(f"История ({len(history_list)} записей)")
        title.setStyleSheet("font-size: 14px; color: #eee;")
        layout.addWidget(title)

        # Список истории
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)

        for item in reversed(history_list):
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        # Кнопки
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
# Окно миникалькулятора без шапки
# ---------------------------------------------------------------------------
class MiniCalcWindow(QWidget):
    """Окно с однострочным калькулятором без шапки."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Калькулятор")
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setFixedWidth(400)
        self.setFixedHeight(38)

        # Загружаем иконку
        try:
            self.setWindowIcon(load_embedded_icon())
        except Exception:
            pass

        # Основной layout - одна строка
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(3)

        # ☰ - область для перетаскивания
        self.drag_label = QLabel("☰")
        self.drag_label.setFixedWidth(26)
        self.drag_label.setStyleSheet("""
            QLabel {
                color: #888;
                font-size: 15px;
                padding: 4px 4px;
                background: transparent;
                font-weight: bold;
            }
            QLabel:hover {
                color: #0078d7;
            }
        """)
        self.drag_label.setAlignment(Qt.AlignCenter)
        self.drag_label.mousePressEvent = self.mousePressEvent
        self.drag_label.mouseMoveEvent = self.mouseMoveEvent
        main_layout.addWidget(self.drag_label)

        # Строка ввода
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Введите выражение (например, 2,2+3,8)")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: #eee;
                color: #000000;
                border: 2px solid #0078d7;
                border-radius: 4px;
                padding: 3px 10px;
                font-size: 14px;
                font-family: Consolas, monospace;
                selection-background-color: #0078d7;
            }
            QLineEdit:focus {
                border: 3px solid #0078d7;
            }
        """)
        self.input_field.returnPressed.connect(self.calculate)
        self.input_field.textChanged.connect(self.on_text_changed)
        main_layout.addWidget(self.input_field, 1)

        # Кнопка истории
        self.btn_history = QPushButton("📋")
        self.btn_history.setFixedSize(26, 26)
        self.btn_history.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                border: none;
                font-size: 13px;
                padding: 0px;
                border-radius: 4px;
            }
            QPushButton:hover {
                color: #eee;
                background: #0078d7;
            }
        """)
        self.btn_history.clicked.connect(self.show_history)
        main_layout.addWidget(self.btn_history)

        # Кнопка закрыть (спрятать в трей)
        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(26, 26)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                border: none;
                font-size: 13px;
                padding: 0px;
                border-radius: 4px;
            }
            QPushButton:hover {
                color: #fff;
                background: #c42b2b;
            }
        """)
        self.btn_close.clicked.connect(self.hide_to_tray)
        main_layout.addWidget(self.btn_close)

        # Состояние
        self.last_result = None
        self.last_expression = None
        self.is_result_displayed = False
        self.last_text = ""
        self.processing_operator = False

        # История и навигация
        self.history = []
        self.history_index = -1
        self.current_input = ""
        self._load_history()

        # Для перетаскивания окна
        self.drag_pos = None

        # Настройки позиции
        self.session_pos = None
        self._load_settings()

    def _load_settings(self):
        """Загружает сохраненную позицию окна."""
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
        """Сохраняет позицию окна."""
        data = {"window_pos": [self.x(), self.y()]}
        try:
            CONFIG_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def _load_history(self):
        """Загружает историю из файла."""
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except Exception:
                self.history = []
        else:
            self.history = []

    def _save_history(self):
        """Сохраняет историю в файл."""
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.history[-100:], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _add_to_history(self, text: str):
        """Добавляет запись в историю."""
        if text and text not in self.history:
            self.history.append(text)
            if len(self.history) > 100:
                self.history = self.history[-100:]
            self._save_history()
            self.history_index = -1
            self.current_input = ""

    def show_history(self):
        """Показывает диалог истории."""
        if not self.history:
            QMessageBox.information(
                self, "История",
                "История вычислений пуста.",
                QMessageBox.Ok
            )
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
        """Прячет окно в трей."""
        self._save_settings()
        self.hide()

    def on_text_changed(self, text: str):
        """Обрабатывает изменение текста в поле ввода."""
        if self.processing_operator:
            return

        if not self.is_result_displayed:
            self.last_text = text
            return

        if text == self.last_text:
            return

        if len(text) > len(self.last_text):
            added = text[len(self.last_text):]
            if added in '+-*/%^':
                if self.last_result and self.last_result in text:
                    pos = text.find(self.last_result)
                    if pos >= 0:
                        self.processing_operator = True
                        new_text = self.last_result + added
                        self.input_field.setText(new_text)
                        self.is_result_displayed = False
                        self.last_text = new_text
                        self.input_field.setFocus()
                        self.input_field.setCursorPosition(len(new_text))
                        self.processing_operator = False
                        return

        self.last_text = text

    def _normalize_expression(self, expression: str) -> str:
        """
        Нормализует выражение для вычисления:
        - Удаляет пробелы из чисел (разрядность)
        - Заменяет запятую на точку в числах
        - Заменяет ^ на **
        """
        if not expression:
            return expression

        result = []
        i = 0
        length = len(expression)

        while i < length:
            ch = expression[i]

            if ch == ' ':
                if i > 0 and i < length - 1:
                    prev = expression[i-1]
                    next_ch = expression[i+1]
                    if prev.isdigit() and next_ch.isdigit():
                        i += 1
                        continue
                result.append(ch)
            elif ch == ',':
                if i > 0 and i < length - 1:
                    prev = expression[i-1]
                    next_ch = expression[i+1]
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

    def _safe_eval(self, expression: str) -> tuple:
        """
        Безопасно вычисляет математическое выражение.
        Возвращает (результат, ошибка)
        """
        if not expression or not expression.strip():
            return None, ""

        expr = expression.strip()
        expr = self._normalize_expression(expr)

        allowed = set("0123456789+-*/().% \t")
        for ch in expr:
            if ch not in allowed:
                return None, f"Ошибка: недопустимый символ '{ch}'"

        try:
            result = eval(expr, {"__builtins__": {}}, {})

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
        except ZeroDivisionError:
            return None, "Ошибка: деление на ноль"
        except SyntaxError:
            return None, "Ошибка: неверное выражение"
        except Exception as e:
            return None, f"Ошибка: {str(e)}"

    def calculate(self):
        """Вычисляет выражение и показывает результат."""
        current_text = self.input_field.text().strip()

        # Если в поле уже есть результат (только число, без '=')
        if self.is_result_displayed and current_text == self.last_result:
            self.input_field.setCursorPosition(len(current_text))
            self.is_result_displayed = False
            self.last_text = current_text
            return

        # Если в поле есть выражение с результатом (содержит '=')
        if '=' in current_text:
            if self.is_result_displayed:
                if self.last_result:
                    self.input_field.setText(self.last_result)
                    self.is_result_displayed = False
                    self.input_field.setCursorPosition(len(self.last_result))
                    self.last_text = self.last_result
                    return

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

        # Обычное вычисление
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

    def clear_input(self):
        """Очищает поле ввода (по Escape)."""
        self.input_field.clear()
        self.last_result = None
        self.last_expression = None
        self.is_result_displayed = False
        self.last_text = ""
        self.history_index = -1
        self.current_input = ""
        self.input_field.setFocus()

    def keyPressEvent(self, event):
        """Обработка клавиш."""
        key = event.key()

        if key == Qt.Key_Escape:
            self.hide_to_tray()
            return

        # Стрелки для навигации по истории
        if key == Qt.Key_Down:
            self.navigate_history_down()
            return
        elif key == Qt.Key_Up:
            self.navigate_history_up()
            return

        super().keyPressEvent(event)

    def navigate_history_down(self):
        """
        Навигация по истории вниз.
        Загружает от последнего к первому.
        """
        if not self.history:
            return

        # Если не в режиме просмотра истории, сохраняем текущий ввод
        if self.history_index == -1:
            self.current_input = self.input_field.text()
            # Начинаем с последней записи (индекс 0 в обратном порядке)
            self.history_index = 0
        else:
            # Перемещаемся к следующей более ранней записи
            self.history_index += 1
            if self.history_index >= len(self.history):
                # Достигли конца - выходим из режима истории
                self.history_index = -1
                self.input_field.setText(self.current_input)
                self.input_field.setFocus()
                self.input_field.setCursorPosition(len(self.current_input))
                return

        # Показываем запись из истории (индекс идет с конца)
        self.input_field.setText(self.history[len(self.history) - 1 - self.history_index])
        self.input_field.setFocus()
        self.input_field.setCursorPosition(len(self.input_field.text()))

    def navigate_history_up(self):
        """
        Навигация по истории вверх.
        Загружает от первого к последнему (обратно).
        """
        if not self.history or self.history_index == -1:
            return

        # Перемещаемся к более поздней записи
        self.history_index -= 1
        if self.history_index < 0:
            # Достигли начала - выходим из режима истории
            self.history_index = -1
            self.input_field.setText(self.current_input)
            self.input_field.setFocus()
            self.input_field.setCursorPosition(len(self.current_input))
            return

        # Показываем запись из истории (индекс идет с конца)
        self.input_field.setText(self.history[len(self.history) - 1 - self.history_index])
        self.input_field.setFocus()
        self.input_field.setCursorPosition(len(self.input_field.text()))

    # ------------------------------------------------------------------
    # Перетаскивание окна
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
        """При закрытии окна сохраняем позицию и прячем в трей."""
        self._save_settings()
        self.hide()
        event.ignore()

    def showEvent(self, event):
        """При показе окна фокус на поле ввода."""
        self.input_field.setFocus()
        if not self.is_result_displayed:
            self.input_field.selectAll()
        self.history_index = -1
        self.current_input = ""
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

        # Создаем окно калькулятора
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

        # Таймер для контроля NumLock (проверяем каждую секунду)
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
        data = {
            "calc_hotkey_enabled": self.calc_hotkey_enabled,
        }
        try:
            CONFIG_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def _check_numlock(self):
        """Периодически проверяет и включает NumLock."""
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

        # Автозагрузка
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
            # Обновляем состояние автозагрузки
            self.autostart_action.setChecked(is_autostart_enabled())
            self.tray.contextMenu().popup(QtGui.QCursor.pos())

    # ------------------------------------------------------------------
    # Автозагрузка
    # ------------------------------------------------------------------
    def _toggle_autostart(self):
        """Включает/выключает автозагрузку."""
        if is_autostart_enabled():
            # Удаляем из автозагрузки
            if remove_from_autostart():
                self.autostart_action.setChecked(False)
                QMessageBox.information(
                    self, APP_NAME,
                    "Программа удалена из автозагрузки."
                )
            else:
                QMessageBox.warning(
                    self, APP_NAME,
                    "Не удалось удалить программу из автозагрузки."
                )
                self.autostart_action.setChecked(True)
        else:
            # Добавляем в автозагрузку
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
    # Слоты
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
    # Клавиатура: хук NumLock
    # ------------------------------------------------------------------
    def _on_key(self, event):
        if not self.running:
            return

        if event.name != "num lock":
            return

        if is_programmatic_numlock():
            set_programmatic_flag(False)
            return

        now = time.time()
        if now - self._last_toggle < 0.1:
            return
        self._last_toggle = now

        self._sig_toggle.emit()
        QTimer.singleShot(20, set_numlock_on)

    # ------------------------------------------------------------------
    # Логика показа/скрытия калькулятора
    # ------------------------------------------------------------------
    def _do_toggle(self):
        window = self.calc_window

        if not window.isVisible():
            window.show()
            window.raise_()
            window.activateWindow()
            window.input_field.setFocus()
            window.input_field.selectAll()
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


# ---------------------------------------------------------------------------
# Диалог «О программе»
# ---------------------------------------------------------------------------
class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"О программе — {APP_NAME}")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setFixedWidth(340)
        self.setFixedHeight(180)
        self.setStyleSheet("""
            QDialog     { background:#1e1e1e; color:#eee; }
            QLabel      { color:#eee; }
            QPushButton { background:#2a2a2a; color:#eee;
                          border:1px solid #555; padding:5px 18px; }
            QPushButton:hover { background:#383838; }
        """)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(22, 22, 22, 22)

        lbl = QLabel(f"<b>{APP_NAME}</b>&nbsp;&nbsp;v{APP_VERSION}")
        lbl.setStyleSheet("font-size:18px; color:#fff;")
        lay.addWidget(lbl, alignment=Qt.AlignCenter)

        desc = QLabel(
            "Создатель: d_e_m_e_k<br>"
            "На основе кода Андрей Кудлай<br>"
            'GitHub: <a href="https://github.com/Akudlay-ru/CalcNumLock" style="color:#4a90e2; text-decoration:none;">CalcNumLock</a>'
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
