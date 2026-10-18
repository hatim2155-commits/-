
from kivy.app import App
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.clock import Clock
import threading
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

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
        font_size: "28sp"
        color: (0.1, 0.48, 1, 1)
        size_hint_y: None
        height: dp(50)

    Label:
        text: "قراءة إشارات راوتر هواوي"
        font_size: "18sp"
        color: (1, 1, 1, 1)
        size_hint_y: None
        height: dp(36)

    TextInput:
        id: router_ip
        text: "192.168.9.1"
        hint_text: "عنوان الراوتر"
        multiline: False
        size_hint_y: None
        height: dp(48)

    TextInput:
        id: router_password
        password: True
        multiline: False
        hint_text: "كلمة مرور صفحة الراوتر"
        size_hint_y: None
        height: dp(48)

    Button:
        text: "قراءة الإشارة"
        size_hint_y: None
        height: dp(48)
        on_release: app.read_signal()

    Label:
        id: status
        text: "اتصل بشبكة الراوتر ثم اضغط قراءة الإشارة"
        color: (0.8, 0.85, 0.95, 1)
        size_hint_y: None
        height: dp(65)
        text_size: self.width, None

    ScrollView:
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
        self.values = {}
        for name in (
            "LTE RSRP", "LTE RSRQ", "LTE SINR", "LTE PCI",
            "NR RSRP", "NR RSRQ", "NR SINR", "NR PCI",
            "LTE Band", "NR Band"
        ):
            self.add_reading(name)
        return self.root_widget

    def add_reading(self, name):
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.label import Label

        row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(40)
        )
        key = Label(
            text=name, color=(0.35, 0.65, 1, 1)
        )
        value = Label(text="—", color=(1, 1, 1, 1))
        row.add_widget(key)
        row.add_widget(value)
        self.root_widget.ids.readings.add_widget(row)
        self.values[name] = value

    def read_signal(self):
        ip = self.root_widget.ids.router_ip.text.strip()
        if not ip:
            self.root_widget.ids.status.text = "أدخل عنوان الراوتر"
            return

        self.root_widget.ids.status.text = "جارٍ الاتصال وطلب بيانات الإشارة..."
        threading.Thread(
            target=self._fetch_signal,
            args=(ip,),
            daemon=True
        ).start()

    def _get(self, url, headers=None, timeout=8):
        req = urllib.request.Request(
            url,
            headers=headers or {
                "User-Agent": "HATIM5G/1.0",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/xml"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")

    def _fetch_signal(self, ip):
        base = "http://" + ip.rstrip("/")
        try:
            # يطلب رمز التحقق كما يفعل سكربت المتصفح الأصلي.
            token_xml = self._get(base + "/api/webserver/token")
            token_root = ET.fromstring(token_xml)
            token_node = token_root.find(".//token")

            if token_node is None or not token_node.text:
                raise RuntimeError(
                    "الراوتر لم يُرجع رمز التحقق. قد يتطلب تسجيل الدخول أولًا."
                )

            token = token_node.text.strip()
            headers = {
                "User-Agent": "HATIM5G/1.0",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/xml",
                "__RequestVerificationToken": token
            }

            signal_xml = self._get(
                base + "/api/device/signal",
                headers=headers
            )
            root = ET.fromstring(signal_xml)

            aliases = {
                "LTE RSRP": ("lte_rsrp", "rsrp"),
                "LTE RSRQ": ("lte_rsrq", "rsrq"),
                "LTE SINR": ("lte_sinr", "lte_snr", "sinr"),
                "LTE PCI": ("lte_pci", "pci"),
                "NR RSRP": ("nr_rsrp", "nrrsrp"),
                "NR RSRQ": ("nr_rsrq", "nrrsrq"),
                "NR SINR": ("nr_sinr", "nrsinr"),
                "NR PCI": ("nr_pci",),
                "LTE Band": ("lte_band", "band"),
                "NR Band": ("nr_band", "nrbands")
            }

            found = {}
            for label, names in aliases.items():
                for name in names:
                    node = root.find(".//" + name)
                    if node is not None and node.text:
                        found[label] = node.text.strip()
                        break

            if not found:
                raise RuntimeError(
                    "وصل رد من الراوتر، لكن أسماء حقول الإشارة لم تطابق المتوقع."
                )

            Clock.schedule_once(
                lambda dt: self._show_results(found), 0
            )

        except urllib.error.HTTPError as exc:
            message = f"رفض الراوتر الطلب: HTTP {exc.code}"
            Clock.schedule_once(
                lambda dt, m=message: self._show_error(m), 0
            )
        except Exception as exc:
            message = f"تعذر قراءة الإشارة: {exc}"
            Clock.schedule_once(
                lambda dt, m=message: self._show_error(m), 0
            )

    def _show_results(self, found):
        for label, widget in self.values.items():
            widget.text = found.get(label, "غير متوفر في الرد")
        self.root_widget.ids.status.text = (
            "وصل رد الإشارة. راجع القيم المعروضة؛ "
            "الحقول غير المتوفرة قد تحتاج أسماء مختلفة في إصدار الراوتر."
        )

    def _show_error(self, message):
        self.root_widget.ids.status.text = message

if __name__ == "__main__":
    Hatim5GApp().run()
