"""Показ уведомлений в Windows."""

import ctypes
import sys

from config.settings import LOGS_DIR, SEND_WIN_ALERT, WIN_USE_NATIVE_MSGBOX
from core.logger import logger
from core.models import AlertKind

_DEFAULT_DIALOG_TITLE = "Проверка сертификата"
_MSGBOX_BODY_MAX = 900
_TAIL = "\n\n… Текст сокращён. Полное сообщение — в журнале приложения (папка {})."


def _trim_for_native_messagebox(message: str) -> str:
    if len(message) <= _MSGBOX_BODY_MAX:
        return message
    logs_hint = str(LOGS_DIR)
    budget = _MSGBOX_BODY_MAX - len(_TAIL.format(logs_hint))
    return message[: max(0, budget)] + _TAIL.format(logs_hint)


def _show_tk(title: str, message: str, *, kind: AlertKind) -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        if kind is AlertKind.ERROR:
            messagebox.showerror(title, message, parent=root)
        elif kind is AlertKind.INFO:
            messagebox.showinfo(title, message, parent=root)
        else:
            messagebox.showwarning(title, message, parent=root)
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


def show_window_alert(title: str, message: str, *, kind: AlertKind = AlertKind.WARNING) -> None:
    if not SEND_WIN_ALERT:
        return

    title = title.strip() or _DEFAULT_DIALOG_TITLE
    display_message = _trim_for_native_messagebox(message) if WIN_USE_NATIVE_MSGBOX else message

    if WIN_USE_NATIVE_MSGBOX and sys.platform == "win32":
        try:
            fl = {
                AlertKind.WARNING: 0x30,
                AlertKind.ERROR: 0x10,
                AlertKind.INFO: 0x40,
            }.get(kind, 0x30)
            ctypes.windll.user32.MessageBoxW(0, display_message, title, 0x40000 | fl)
            logger.info("Показано окно Windows (MessageBox) с результатом проверки.")
            return
        except Exception as e:
            logger.warning("Не удалось показать MessageBox: {}", e)
    try:
        _show_tk(title, message, kind=kind)
    except ImportError as e:
        logger.warning("Окно с результатом недоступно (нет tkinter): {}", e)
