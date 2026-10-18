
from kivy.app import App
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
import threading
import urllib.request
import urllib.error
import json

APP_NAME = "HATIM 5G"

KV = r"""
BoxLayout:
    orientation: "vertical"
    padding: dp(16)
    spacing: dp(10)

    canvas.before:
        Color:
            rgba: (0.035, 0.055, 0.09, 1)
        Rectangle:
            pos: self.pos
            size: self.size

    Label:
        text: "[b]HATIM 5G[/b]"
        markup: True
        font_size: "30sp"
        color: (0.1, 0.48, 1, 1)
        size_hint_y: None
        height: dp(54)

    Label:
        text: "إدارة راوتر هواوي"
        font_size: "20sp"
        color: (1, 1, 1, 1)
        size_hint_y: None
        height: dp(38)

    BoxLayout:
        size_hint_y: None
        height: dp(48)
        spacing: dp(8)

        Label:
            text: "عنوان الراوتر"
            size_hint_x: .42
            color: (1, 1, 1, 1)

        TextInput:
            id: router_ip
            text: "192.168.8.1"
            multiline: False
            input_type: "url"
            size_hint_x: .58

    BoxLayout:
        size_hint_y: None
        height: dp(48)
        spacing: dp(8)

        Label:
            text: "كلمة المرور"
            size_hint_x: .42
            color: (1, 1, 1, 1)

        TextInput:
            id: router_password
            password: True
            multiline: False
            hint_text: "كلمة مرور الراوتر"
            size_hint_x: .58

    Button:
        text: "اختبار الاتصال"
        size_hint_y: None
        height: dp(50)
        background_normal: ""
        background_color: (0.05, 0.32, 0.85, 1)
        on_release: app.test_connection()

    Label:
        id: status
        text: "أدخل عنوان الراوتر ثم اختبر الاتصال"
        color: (0.8, 0.85, 0.95, 1)
        size_hint_y: None
        height: dp(52)
        halign: "center"
        valign: "middle"
        text_size: self.width, None

    Label:
        text: "[b]معلومات الإشارة[/b]"
        markup: True
        font_size: "20sp"
        color: (1, 1, 1, 1)
        size_hint_y: None
        height: dp(40)

    ScrollView:
        do_scroll_x: False

        GridLayout:
            id: readings
            cols: 1
            spacing: dp(8)
            size_hint_y: None
            height: self.minimum_height
"""

class Hatim5GApp(App):
    def build(self):
        self.title = APP_NAME
        self.root_widget = Builder.load_string(KV)
        self.add_reading("حالة الاتصال", "لم يتم الاختبار بعد")
        self.add_reading("RSRP", "—")
        self.add_reading("RSRQ", "—")
        self.add_reading("SINR", "—")
        self.add_reading("PCI", "—")
        self.add_reading("التردد / النطاق", "—")
        return self.root_widget

    def add_reading(self, name, value):
        row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(8)
        )
        key = Label(
            text=name,
            color=(0.35, 0.65, 1, 1),
            halign="right"
        )
        val = Label(
            text=value,
            color=(1, 1, 1, 1),
            halign="left"
        )
        row.add_widget(key)
        row.add_widget(val)
        self.root_widget.ids.readings.add_widget(row)
        return val

    def test_connection(self):
        ip = self.root_widget.ids.router_ip.text.strip()
        if not ip:
            self.root_widget.ids.status.text = "أدخل عنوان الراوتر أولًا"
            return

        self.root_widget.ids.status.text = "جارٍ اختبار صفحة الراوتر..."
        threading.Thread(
            target=self._check_router,
            args=(ip,),
            daemon=True
        ).start()

    def _check_router(self, ip):
        url = "http://" + ip + "/"
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "HATIM5G/1.0"}
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                code = response.status
                result = f"تم الوصول إلى صفحة الراوتر (HTTP {code})"
        except urllib.error.HTTPError as exc:
            result = f"وصلنا للراوتر؛ استجاب برمز HTTP {exc.code}"
        except Exception as exc:
            result = "تعذر الاتصال: تأكد من الشبكة وعنوان الراوتر"

        Clock.schedule_once(
            lambda dt: self._show_status(result),
            0
        )

    def _show_status(self, message):
        self.root_widget.ids.status.text = message

if __name__ == "__main__":
    Hatim5GApp().run()
