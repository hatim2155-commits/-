import flet as ft
import requests
import xml.etree.ElementTree as ET

ROUTER_IP = "192.168.8.1"
BASE_URL = f"http://{ROUTER_IP}"

# الترددات الأساسية المدعومة للدمج والتثبيت
ALL_BANDS = {
    "تلقائي (الكل 4G/5G)": "7FFFFFFFFFFFFFFF",
    "5G - N78 (3500 MHz الرئيسي)": "8000000000",
    "5G - N28 (700 MHz تغطية)": "8000000",
    "4G - B3 (1800 MHz)": "4",
    "4G - B1 (2100 MHz)": "1",
    "دمج 4G (B3+B1) + 5G (N78)": "8000000005"
}

def main(page: ft.Page):
    page.title = "Hatim5G Control"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    password_input = ft.TextField(
        label="كلمة مرور الراوتر", 
        password=True, 
        can_reveal_password=True,
        value="admin"
    )
    
    status_text = ft.Text("الحالة: جاهز", color=ft.Colors.GREY)
    
    rsrp_card = ft.Text("RSRP: --", size=16, weight=ft.FontWeight.BOLD)
    sinr_card = ft.Text("SINR: --", size=16, weight=ft.FontWeight.BOLD)
    rsrq_card = ft.Text("RSRQ: --", size=16, weight=ft.FontWeight.BOLD)
    band_card = ft.Text("الشبكة: --", size=14, color=ft.Colors.AMBER_200)
    cell_card = ft.Text("Cell ID: --", size=14, color=ft.Colors.BLUE_200)

    band_dropdown = ft.Dropdown(
        label="اختر التردد أو الدمج المطلوب",
        options=[ft.dropdown.Option(key) for key in ALL_BANDS.keys()],
        value="تلقائي (الكل 4G/5G)"
    )

    session = requests.Session()

    def get_token():
        try:
            res = session.get(f"{BASE_URL}/api/webserver/SesTokInfo", timeout=3)
            if res.status_code == 200:
                root = ET.fromstring(res.text)
                return root.find('SesInfo').text, root.find('TokInfo').text
        except Exception as e:
            status_text.value = f"خطأ بالاتصال: {e}"
            status_text.color = ft.Colors.RED
            page.update()
        return None, None

    def fetch_signal(e):
        status_text.value = "جاري سحب القراءات..."
        status_text.color = ft.Colors.BLUE
        page.update()

        cookie, token = get_token()
        if not token:
            status_text.value = "تعذر الاتصال (تأكد من الواي فاي)"
            status_text.color = ft.Colors.RED
            page.update()
            return

        headers = {"__RequestVerificationToken": token, "Cookie": cookie}

        try:
            res = session.get(f"{BASE_URL}/api/device/signal", headers=headers, timeout=4)
            if res.status_code == 200:
                root = ET.fromstring(res.text)
                
                rsrp = root.findtext('rsrp', default='N/A')
                sinr = root.findtext('sinr', default='N/A')
                rsrq = root.findtext('rsrq', default='N/A')
                cell_id = root.findtext('CellId', default='N/A')
                
                rsrp_card.value = f"RSRP: {rsrp} dBm"
                sinr_card.value = f"SINR: {sinr} dB"
                rsrq_card.value = f"RSRQ: {rsrq} dB"
                cell_card.value = f"Cell ID: {cell_id}"
                
                status_text.value = "تم التحديث بنجاح ✅"
                status_text.color = ft.Colors.GREEN
            else:
                status_text.value = "فشل في جلب البيانات"
                status_text.color = ft.Colors.RED
        except Exception as ex:
            status_text.value = f"خطأ: {ex}"
            status_text.color = ft.Colors.RED
        
        page.update()

    def apply_band_lock(e):
        selected_option = band_dropdown.value
        mask_hex = ALL_BANDS.get(selected_option, "7FFFFFFFFFFFFFFF")

        status_text.value = "جاري تطبيق التردد..."
        status_text.color = ft.Colors.ORANGE
        page.update()

        cookie, token = get_token()
        if not token:
            return

        headers = {
            "__RequestVerificationToken": token,
            "Cookie": cookie,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
        }

        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
        <request>
            <NetworkMode>03</NetworkMode>
            <NetworkBand>{mask_hex}</NetworkBand>
            <LTEBand>{mask_hex}</LTEBand>
        </request>"""

        try:
            res = session.post(f"{BASE_URL}/api/net/net-mode", data=payload, headers=headers, timeout=5)
            if "OK" in res.text:
                status_text.value = "تم تثبيت التردد بنجاح 🎯"
                status_text.color = ft.Colors.GREEN
            else:
                status_text.value = f"رد الراوتر: {res.text}"
                status_text.color = ft.Colors.RED
        except Exception as ex:
            status_text.value = f"خطأ: {ex}"
            status_text.color = ft.Colors.RED

        page.update()

    page.add(
        ft.Text("Hatim5G Control 📶", size=22, weight=ft.FontWeight.BOLD),
        password_input,
        ft.ElevatedButton("تحديث الإشارة 🔄", on_click=fetch_signal, color=ft.Colors.WHITE, bgcolor=ft.Colors.BLUE_700),
        status_text,
        ft.Divider(),
        ft.Card(content=ft.Container(content=ft.Column([band_card, rsrp_card, sinr_card, rsrq_card, cell_card]), padding=15)),
        ft.Divider(),
        band_dropdown,
        ft.ElevatedButton("تطبيق وتثبيت التردد 🔒", on_click=apply_band_lock, color=ft.Colors.WHITE, bgcolor=ft.Colors.GREEN_700)
    )

ft.app(target=main)
