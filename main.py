import os
import threading
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.text import LabelBase
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView

from scoring import analyze_stock


# ─────────────────────────────────────────────
# 中文字型支援
# Kivy 內建字型不含中文字，在 Android 上會顯示成方框，
# 這裡改用手機系統內建的中文字型，不用額外包字型檔。
# 依常見 Android 版本／廠牌列出幾個常見路徑輪流嘗試。
# ─────────────────────────────────────────────
_CJK_FONT_CANDIDATES = [
    # 一般單一字型檔優先（.ttc 多字型合集檔容易讓 Kivy 算錯文字寬度、疊字）
    "/system/fonts/DroidSansFallbackFull.ttf",
    "/system/fonts/DroidSansFallback.ttf",
    "/system/fonts/NotoSansSC-Regular.otf",
    "/system/fonts/NotoSansCJK-Regular.ttf",
    "/system/fonts/MiSans-Regular.ttf",
    # 最後才嘗試 .ttc（合集檔，可能疊字，但總比方框好）
    "/system/fonts/NotoSansCJK-Regular.ttc",
]

for _font_path in _CJK_FONT_CANDIDATES:
    if os.path.exists(_font_path):
        LabelBase.register(name="Roboto", fn_regular=_font_path)
        break


# ─────────────────────────────────────────────
# 全域安全網：任何沒被 try/except 接住的例外，
# 一律導向這裡處理，不讓整個 App 直接關閉消失。
# ─────────────────────────────────────────────
from kivy.base import ExceptionManager, ExceptionHandler
import traceback


class _安全網(ExceptionHandler):
    def handle_exception(self, inst):
        try:
            錯誤內容 = "".join(
                traceback.format_exception(type(inst), inst, inst.__traceback__)
            )
        except Exception:
            錯誤內容 = str(inst)

        app = App.get_running_app()
        if app is not None and hasattr(app, "顯示錯誤"):
            try:
                Clock.schedule_once(lambda dt: app.顯示錯誤(錯誤內容))
            except Exception:
                pass

        return ExceptionManager.PASS


ExceptionManager.add_handler(_安全網())


class 股票分析APP(App):

    def build(self):
        self.title = "三面向股票分析器"

        主畫面 = BoxLayout(
            orientation="vertical",
            padding=dp(12),
            spacing=dp(8)
        )

        標題 = Label(
            text="📈 三面向股票分析器",
            font_size=dp(25),
            size_hint_y=None,
            height=dp(55)
        )
        主畫面.add_widget(標題)

        輸入列 = BoxLayout(
            size_hint_y=None,
            height=dp(50),
            spacing=dp(8)
        )

        self.股票代號 = TextInput(
            text="2330",
            hint_text="輸入股票代號，例如 2330",
            multiline=False,
            font_size=dp(18)
        )

        分析按鈕 = Button(
            text="開始分析",
            font_size=dp(17)
        )

        分析按鈕.bind(on_press=self.開始分析)

        輸入列.add_widget(self.股票代號)
        輸入列.add_widget(分析按鈕)

        主畫面.add_widget(輸入列)

        self.狀態 = Label(
            text="請輸入股票代號",
            size_hint_y=None,
            height=dp(38)
        )

        主畫面.add_widget(self.狀態)

        捲動區 = ScrollView()

        self.結果 = GridLayout(
            cols=1,
            spacing=dp(6),
            padding=dp(8),
            size_hint_y=None
        )

        self.結果.bind(
            minimum_height=self.結果.setter("height")
        )

        捲動區.add_widget(self.結果)

        主畫面.add_widget(捲動區)

        return 主畫面

    def 開始分析(self, instance):

        股票 = self.股票代號.text.strip()

        if not 股票.isdigit():
            self.狀態.text = "❌ 請輸入正確股票代號，例如 2330"
            return

        if len(股票) < 4:
            self.狀態.text = "❌ 股票代號至少需要 4 碼"
            return

        self.結果.clear_widgets()

        self.狀態.text = "⏳ 正在取得資料，請稍候（需查詢多個資料來源，可能需要 10-20 秒）……"

        threading.Thread(
            target=self.背景分析,
            args=(股票,),
            daemon=True
        ).start()

    def 背景分析(self, 股票):

        try:

            結果 = analyze_stock(股票)

            Clock.schedule_once(
                lambda dt: self.顯示結果(結果)
            )

        except Exception as e:

            Clock.schedule_once(
                lambda dt: self.顯示錯誤(str(e))
            )

    def 增加文字(self, 文字, 大小=17, 高度=40):

        標籤 = Label(
            text=文字,
            font_size=dp(大小),
            size_hint_y=None,
            height=dp(高度),
            halign="left",
            valign="middle"
        )

        標籤.bind(
            size=lambda obj, value:
            setattr(obj, "text_size", (obj.width, None))
        )

        self.結果.add_widget(標籤)

    def 增加分隔線(self):
        self.增加文字("━━━━━━━━━━━━━━━━━━━━")

    def 增加資料表(self, 標題, 資料字典):

        if not 資料字典:
            return

        self.增加文字(標題, 20, 42)

        for 名稱, 數值 in 資料字典.items():
            self.增加文字(f"• {名稱}：{數值}")

    def 顯示結果(self, d):

        self.狀態.text = (
            "分析完成　"
            + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        self.增加文字(f"📌 {d['code']}　{d['name']}", 24, 50)
        self.增加文字(f"💰 最新價格：{d['price']:.2f}", 18)

        self.增加分隔線()

        self.增加文字(f"📊 基本面　　{d['fundamental']} / 100", 19)
        self.增加文字(f"🏦 籌碼面　　{d['chip']} / 100", 19)
        self.增加文字(f"📈 技術面　　{d['technical']} / 100", 19)

        self.增加分隔線()

        self.增加文字(f"⭐ 綜合評分　{d['overall']} / 100", 23, 48)
        self.增加文字(f"📢 綜合判斷：{d['rating']}", 22, 48)

        self.增加分隔線()

        # 基本面
        self.增加文字("📊 基本面分析", 20, 42)
        self.增加文字(d["fundamental_reason"])
        self.增加資料表("　基本面數據", d.get("fundamental_data", {}))

        self.增加分隔線()

        # 籌碼面
        self.增加文字("🏦 籌碼面分析", 20, 42)
        self.增加文字(d["chip_reason"])
        self.增加資料表("　籌碼面數據", d.get("chip_data", {}))

        self.增加分隔線()

        # 千張大戶
        大戶 = d.get("big_holder", {})
        self.增加文字("👥 千張大戶", 20, 42)

        if 大戶.get("可用"):
            self.增加文字(
                f"資料日期：{大戶.get('資料日期', '無資料')}"
            )
            self.增加文字(
                f"千張以上大戶：{大戶['千張以上大戶戶數']:,} 戶"
            )
            self.增加文字(
                f"持股比例：{大戶['千張以上大戶持股比例(%)']:.2f}%"
            )
            self.增加文字(
                f"大戶評分：{大戶['大戶評分']} / 100"
            )
            self.增加文字(大戶.get("說明", ""), 15, 55)
        else:
            self.增加文字(
                "⚠️ " + 大戶.get("說明", "目前無法取得千張大戶資料"),
                15,
                55
            )

        self.增加分隔線()

        # 技術面
        self.增加文字("📈 技術面分析", 20, 42)
        self.增加文字(d["technical_reason"])
        self.增加資料表("　技術指標", d.get("technical_data", {}))

        self.增加分隔線()

        self.增加文字("ℹ️ 資料來源：" + d["source"], 14, 70)

        self.增加文字(
            "⚠️ 本程式僅供資訊分析與研究使用，"
            "不構成投資或買賣建議。",
            14,
            60
        )

    def 顯示錯誤(self, 錯誤):

        self.狀態.text = "❌ 分析失敗"

        self.增加文字("取得股票資料時發生錯誤：", 19)
        self.增加文字(錯誤, 16, 70)


if __name__ == "__main__":
    股票分析APP().run()
