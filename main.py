from __future__ import annotations

import os
import logging
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.storage.jsonstore import JsonStore
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.switch import Switch
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.textinput import TextInput
from kivy.utils import get_color_from_hex

import arabic_reshaper
from bidi.algorithm import get_display
from core.router import (
    DEFAULT_ROUTER_URL,
    HuaweiRouter,
    RouterError,
    RouterLoginError,
    RouterSignalError,
    RouterUnreachableError,
)

APP_NAME = "HATIM 5G"
BACKGROUND = get_color_from_hex("#0B1220")
SURFACE = get_color_from_hex("#121E31")
ACCENT = get_color_from_hex("#29B6F6")
FOREGROUND = get_color_from_hex("#F3F6FC")
MUTED = get_color_from_hex("#AAB8CC")
NOT_AVAILABLE = "غير متاح: لم يرد الحقل من الراوتر"


def rtl(text: str) -> str:
    return get_display(arabic_reshaper.reshape(text))


class Hatim5GApp(App):
    def build(self):
        self.title = APP_NAME
        self._busy = False
        self._refresh_event = None
        self._store = JsonStore(os.path.join(self.user_data_dir, "settings.json"))
        self._signal_values: dict[str, dict[str, Label]] = {}
        self._cell_values: dict[str, Label] = {}
        self._font_name = self._register_arabic_font()

        saved_url = self._store.get("router").get("url", DEFAULT_ROUTER_URL) if self._store.exists("router") else DEFAULT_ROUTER_URL
        saved_auto = self._store.get("refresh").get("enabled", False) if self._store.exists("refresh") else False
        saved_interval = self._store.get("refresh").get("seconds", 30) if self._store.exists("refresh") else 30

        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        with root.canvas.before:
            from kivy.graphics import Color, Rectangle

            Color(*BACKGROUND)
            self._background_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._update_background, size=self._update_background)

        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(8))
        title = self._label("HATIM 5G", 24, ACCENT, bold=True, halign="right")
        header.add_widget(title)
        self._refresh_button = self._button("تحديث الآن", self.refresh_signal, width=dp(122))
        header.add_widget(self._refresh_button)
        root.add_widget(header)

        self.status_label = self._label("لم يتم الاتصال بعد. اتصل بشبكة الراوتر ثم اختبر الاتصال.", 14, MUTED)
        self.status_label.size_hint_y = None
        self.status_label.height = dp(48)
        root.add_widget(self.status_label)

        self.tabs = TabbedPanel(do_default_tab=False, tab_width=dp(112), tab_height=dp(46), background_color=BACKGROUND)
        self.tabs.tab_pos = "top_right"
        self._add_home_tab()
        self._add_signal_tab("4G LTE", "4G LTE")
        self._add_signal_tab("5G NR", "5G NR")
        self._add_cells_tab()
        self._add_settings_tab(saved_url, saved_auto, saved_interval)
        root.add_widget(self.tabs)
        self.tabs.default_tab = self.home_tab
        self._set_auto_refresh(bool(saved_auto), saved_interval, persist=False)
        return root

    def _register_arabic_font(self) -> str:
        from kivy.core.text import LabelBase
        from kivy.resources import resource_find

        font_path = resource_find("assets/fonts/NotoNaskhArabic.ttf")
        if not font_path or not os.path.isfile(font_path):
            raise FileNotFoundError("Arabic font is missing from the application package.")
        LabelBase.register(name="HatimArabic", fn_regular=font_path)
        return "HatimArabic"

    def _update_background(self, widget, *_args):
        self._background_rect.pos = widget.pos
        self._background_rect.size = widget.size

    def _label(self, text: str, size: int = 16, color=FOREGROUND, bold=False, halign="right"):
        label = Label(
            text=rtl(text),
            font_name=self._font_name,
            font_size=dp(size),
            color=color,
            bold=bold,
            halign=halign,
            valign="middle",
            size_hint_y=None,
            height=dp(max(34, size * 2)),
            text_size=(None, None),
        )
        label.bind(size=lambda instance, _value: setattr(instance, "text_size", (instance.width - dp(8), None)))
        return label

    def _button(self, text: str, callback, width=None):
        button = Button(
            text=rtl(text),
            font_name=self._font_name,
            font_size=dp(15),
            color=FOREGROUND,
            background_normal="",
            background_color=ACCENT,
            size_hint_y=None,
            height=dp(46),
            size_hint_x=None if width else 1,
            width=width or 0,
        )
        button.bind(on_release=lambda *_args: callback())
        return button

    def _new_tab(self, title: str):
        tab = TabbedPanelItem(text=rtl(title), font_name=self._font_name, font_size=dp(14))
        scroll = ScrollView(do_scroll_x=False)
        content = GridLayout(cols=1, spacing=dp(10), padding=(dp(4), dp(8)), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        tab.add_widget(scroll)
        self.tabs.add_widget(tab)
        return tab, content

    def _card(self, title: str, content: GridLayout, rows: list[BoxLayout]):
        card = BoxLayout(
            orientation="vertical",
            padding=dp(12),
            spacing=dp(8),
            size_hint_y=None,
            height=dp(54 + len(rows) * 48),
        )
        with card.canvas.before:
            from kivy.graphics import Color, RoundedRectangle

            Color(*SURFACE)
            card._surface = RoundedRectangle(pos=card.pos, size=card.size, radius=[dp(14)])
        card.bind(pos=lambda widget, _v: setattr(widget._surface, "pos", widget.pos))
        card.bind(size=lambda widget, _v: setattr(widget._surface, "size", widget.size))
        heading = self._label(title, 17, ACCENT, bold=True)
        card.add_widget(heading)
        for row in rows:
            card.add_widget(row)
        content.add_widget(card)

    def _row(self, title: str, value: str, mapping: dict[str, Label] | None = None):
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(8))
        value_label = self._label(value, 15, FOREGROUND)
        title_label = self._label(title, 14, MUTED)
        row.add_widget(value_label)
        row.add_widget(title_label)
        if mapping is not None:
            mapping[title] = value_label
        return row

    def _add_home_tab(self):
        self.home_tab, content = self._new_tab("الرئيسية")
        intro = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(8), size_hint_y=None, height=dp(142))
        intro.add_widget(self._label("مراقبة اتصال وإشارة راوتر HATIM 5G", 19, ACCENT, bold=True))
        intro.add_widget(self._label(
            "يعرض التطبيق القراءات التي يرسلها الراوتر فقط. عدم ظهور قراءة لا يعني وجود إشارة وهمية.",
            14, MUTED,
        ))
        content.add_widget(intro)
        content.add_widget(self._label("افتح تبويب الإعدادات لإدخال عنوان الراوتر وكلمة المرور، ثم اختبر الاتصال.", 14, FOREGROUND))

    def _add_signal_tab(self, title: str, key: str):
        _, content = self._new_tab(title)
        values: dict[str, Label] = {}
        rows = []
        for metric in ("RSRP", "RSRQ", "SINR", "PCI", "النطاق", "EARFCN" if key == "4G LTE" else "NR-ARFCN", "معرّف الخلية"):
            rows.append(self._row(metric, NOT_AVAILABLE, values))
        self._signal_values[key] = values
        self._card("قراءات " + title, content, rows)
        content.add_widget(self._label(
            "تظهر القيم بعد نجاح طلب بيانات حقيقي من الراوتر. قد لا يرسل الراوتر جميع الحقول.",
            13, MUTED,
        ))

    def _add_cells_tab(self):
        _, content = self._new_tab("الأبراج القريبة")
        rows = []
        for metric in ("معرّف الخلية", "PCI", "النطاق", "القناة", "نوع الشبكة"):
            rows.append(self._row(metric, NOT_AVAILABLE, self._cell_values))
        self._card("معلومات الخلية التي يرسلها الراوتر", content, rows)
        content.add_widget(self._label(
            "واجهة Huawei القياسية قد تعرض الخلية الحالية فقط. لا تُعرض أبراج مجاورة إلا إذا أعادها الراوتر فعليًا.",
            13, MUTED,
        ))

    def _add_settings_tab(self, saved_url: str, saved_auto: bool, saved_interval: int):
        _, content = self._new_tab("الإعدادات")
        content.add_widget(self._label("عنوان الراوتر", 15, ACCENT, bold=True))
        self.address_input = TextInput(
            text=saved_url,
            hint_text="http://192.168.9.1",
            multiline=False,
            font_name=self._font_name,
            size_hint_y=None,
            height=dp(48),
            foreground_color=FOREGROUND,
            background_color=SURFACE,
            cursor_color=ACCENT,
            halign="left",
        )
        content.add_widget(self.address_input)
        content.add_widget(self._label("كلمة مرور حساب الراوتر (لا تُحفظ على الجهاز)", 14, ACCENT, bold=True))
        self.password_input = TextInput(
            password=True,
            multiline=False,
            hint_text=rtl("كلمة المرور"),
            font_name=self._font_name,
            size_hint_y=None,
            height=dp(48),
            foreground_color=FOREGROUND,
            background_color=SURFACE,
            cursor_color=ACCENT,
            halign="left",
        )
        content.add_widget(self.password_input)
        content.add_widget(self._button("اختبار الاتصال وقراءة الإشارة", self.test_connection))

        auto_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(46), spacing=dp(8))
        self.auto_switch = Switch(active=bool(saved_auto))
        self.auto_switch.bind(active=lambda _switch, active: self._set_auto_refresh(active, self._interval_value(), persist=True))
        auto_row.add_widget(self.auto_switch)
        auto_row.add_widget(self._label("تحديث تلقائي", 15))
        content.add_widget(auto_row)

        interval_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(46), spacing=dp(8))
        self.interval_input = TextInput(
            text=str(saved_interval),
            hint_text="30",
            multiline=False,
            input_filter="int",
            font_name=self._font_name,
            size_hint_x=None,
            width=dp(88),
            foreground_color=FOREGROUND,
            background_color=SURFACE,
            halign="center",
        )
        interval_row.add_widget(self.interval_input)
        interval_row.add_widget(self._label("الفاصل بالثواني (10–3600)", 14, MUTED))
        content.add_widget(interval_row)
        content.add_widget(self._button("حفظ الإعدادات", self.save_settings))

    def _interval_value(self) -> int:
        try:
            return max(10, min(3600, int(self.interval_input.text)))
        except (AttributeError, TypeError, ValueError):
            return 30

    def save_settings(self):
        address = self.address_input.text.strip() or DEFAULT_ROUTER_URL
        seconds = self._interval_value()
        self.interval_input.text = str(seconds)
        self._store.put("router", url=address)
        self._store.put("refresh", enabled=self.auto_switch.active, seconds=seconds)
        self._set_status("تم حفظ الإعدادات. كلمة المرور لا تُحفظ.", MUTED)
        self._set_auto_refresh(self.auto_switch.active, seconds, persist=False)

    def _set_auto_refresh(self, active: bool, seconds: int, persist: bool):
        if not hasattr(self, "interval_input"):
            return
        if self._refresh_event is not None:
            self._refresh_event.cancel()
            self._refresh_event = None
        if active:
            self._refresh_event = Clock.schedule_interval(
                lambda _dt: self.refresh_signal(), max(10, min(3600, int(seconds)))
            )
        if persist and hasattr(self, "_store"):
            self._store.put("refresh", enabled=bool(active), seconds=max(10, min(3600, int(seconds))))

    def test_connection(self):
        self._start_read(test=True)

    def refresh_signal(self):
        self._start_read(test=False)

    def _start_read(self, test: bool):
        if self._busy:
            return
        address = self.address_input.text.strip() or DEFAULT_ROUTER_URL
        password = self.password_input.text
        self._store.put("router", url=address)
        self._busy = True
        self._refresh_button.disabled = True
        self._clear_values()
        self._set_status("جارٍ اختبار جلسة الراوتر وطلب بيانات الإشارة...", ACCENT)
        threading.Thread(target=self._read_worker, args=(address, password, test), daemon=True).start()

    def _read_worker(self, address: str, password: str, test: bool):
        try:
            reading = HuaweiRouter.test_connection(address, password)
            Clock.schedule_once(lambda _dt: self._show_reading(reading, test), 0)
        except RouterUnreachableError as exc:
            Clock.schedule_once(lambda _dt, message=str(exc): self._show_error(message), 0)
        except RouterLoginError as exc:
            Clock.schedule_once(lambda _dt, message=str(exc): self._show_error(message), 0)
        except RouterSignalError as exc:
            Clock.schedule_once(lambda _dt, message=str(exc): self._show_error(message), 0)
        except RouterError as exc:
            Clock.schedule_once(lambda _dt, message=str(exc): self._show_error(message), 0)
        except Exception:
            logging.getLogger(__name__).exception("Unexpected router read failure")
            Clock.schedule_once(
                lambda _dt: self._show_error("حدث خطأ غير متوقع أثناء الاتصال. أعد المحاولة وتحقق من سجل التطبيق."),
                0,
            )

    def _show_reading(self, reading, test: bool):
        for technology in ("4G LTE", "5G NR"):
            available = reading.signal.get(technology, {})
            for metric, label in self._signal_values[technology].items():
                label.text = rtl(available.get(metric, NOT_AVAILABLE))

        for label, value in self._cell_values.items():
            label.text = rtl(reading.cell_info.get(label, "غير متاح: لم يرسل الراوتر بيانات الخلية"))

        self._busy = False
        self._refresh_button.disabled = False
        if reading.login_verified:
            message = "تم تسجيل الدخول واستلام بيانات إشارة حقيقية من الراوتر."
        else:
            message = "تم استلام بيانات إشارة حقيقية؛ تسجيل الدخول لم يُتحقق (لم تُدخل كلمة مرور)."
        self._set_status(message, get_color_from_hex("#75E0A7"))

    def _show_error(self, message: str):
        self._busy = False
        self._refresh_button.disabled = False
        self._set_status(message, get_color_from_hex("#FF8A80"))

    def _clear_values(self):
        for values in self._signal_values.values():
            for label in values.values():
                label.text = rtl(NOT_AVAILABLE)
        for label in self._cell_values.values():
            label.text = rtl("غير متاح: لم يرسل الراوتر بيانات الخلية")

    def _set_status(self, message: str, color):
        self.status_label.text = rtl(message)
        self.status_label.color = color


if __name__ == "__main__":
    Hatim5GApp().run()
