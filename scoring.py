import csv
import io
from datetime import datetime, timedelta

import requests


USER_AGENT = "Mozilla/5.0 (Android) StockAnalyzer/1.0"
TIMEOUT = 15


# ─────────────────────────────────────────────
# 共用工具
# ─────────────────────────────────────────────

def 取得候選日期(最多嘗試天數=10):
    """
    由今天往前推，回傳一串 YYYYMMDD 字串，
    用來嘗試抓「最近一個有資料的交易日」。
    （週末、假日會抓不到資料，所以要往前多試幾天）
    """
    日期清單 = []
    for i in range(最多嘗試天數):
        d = datetime.now() - timedelta(days=i)
        日期清單.append(d.strftime("%Y%m%d"))
    return 日期清單


def 安全轉數字(文字, 預設=None):
    if 文字 is None:
        return 預設
    文字 = str(文字).replace(",", "").strip()
    if 文字 in ("", "-", "--", "N/A"):
        return 預設
    try:
        return float(文字)
    except ValueError:
        return 預設


def 找欄位索引(欄位清單, 關鍵字們):
    """
    TWSE 開放資料的欄位順序偶爾會調整，
    所以用欄位名稱關鍵字去比對，而不是寫死索引值，
    比較不容易因為 API 改版而算錯。
    """
    for i, 名稱 in enumerate(欄位清單):
        for 關鍵字 in 關鍵字們:
            if 關鍵字 in 名稱:
                return i
    return None


# ─────────────────────────────────────────────
# 行情（技術面資料來源）
# ─────────────────────────────────────────────

def 取得行情(股票代號):

    網址 = (
        f"https://query1.finance.yahoo.com/"
        f"v8/finance/chart/{股票代號}.TW"
    )

    參數 = {
        "range": "6mo",
        "interval": "1d",
        "events": "history"
    }

    回應 = requests.get(
        網址,
        params=參數,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT
    )

    回應.raise_for_status()

    資料 = 回應.json()

    結果 = 資料["chart"]["result"][0]

    報價 = 結果["indicators"]["quote"][0]

    收盤價 = [x for x in 報價["close"] if x is not None]
    成交量 = [x for x in 報價["volume"] if x is not None]

    if len(收盤價) < 60:
        raise ValueError("歷史資料不足 60 個交易日")

    return 收盤價, 成交量


# ─────────────────────────────────────────────
# 技術面（不變）
# ─────────────────────────────────────────────

def SMA(資料, 天數):
    return sum(資料[-天數:]) / 天數


def EMA(資料, 天數):
    k = 2 / (天數 + 1)
    ema = 資料[0]
    for 價格 in 資料[1:]:
        ema = 價格 * k + ema * (1 - k)
    return ema


def RSI(資料, 天數=14):
    漲跌 = [資料[i] - 資料[i - 1] for i in range(1, len(資料))]
    最近 = 漲跌[-天數:]
    上漲 = [max(x, 0) for x in 最近]
    下跌 = [max(-x, 0) for x in 最近]
    平均上漲 = sum(上漲) / 天數
    平均下跌 = sum(下跌) / 天數
    if 平均下跌 == 0:
        return 100
    RS = 平均上漲 / 平均下跌
    return 100 - (100 / (1 + RS))


def MACD(資料):
    EMA12 = EMA(資料, 12)
    EMA26 = EMA(資料, 26)
    return EMA12 - EMA26


def 技術面評分(收盤價, 成交量):

    現價 = 收盤價[-1]
    MA5 = SMA(收盤價, 5)
    MA20 = SMA(收盤價, 20)
    MA60 = SMA(收盤價, 60)
    RSI14 = RSI(收盤價)
    MACD值 = MACD(收盤價)
    二十日平均量 = sum(成交量[-20:]) / 20

    分數 = 0

    if 現價 > MA20:
        分數 += 20
    else:
        分數 += 8

    if MA20 > MA60:
        分數 += 15
    else:
        分數 += 6

    if MA5 > MA20:
        分數 += 15
    else:
        分數 += 6

    if MACD值 > 0:
        分數 += 15
    else:
        分數 += 6

    if 50 <= RSI14 <= 70:
        分數 += 15
    elif 40 <= RSI14 < 50:
        分數 += 10
    else:
        分數 += 6

    if 成交量[-1] >= 二十日平均量:
        分數 += 10
    else:
        分數 += 5

    二十日最高價 = max(收盤價[-20:])

    if 現價 >= 二十日最高價 * 0.97:
        分數 += 10
    else:
        分數 += 5

    分數 = min(100, 分數)

    均線描述 = "MA5 高於 MA20" if MA5 > MA20 else "MA5 低於 MA20"
    趨勢描述 = "MA20 高於 MA60" if MA20 > MA60 else "MA20 低於 MA60"
    MACD描述 = "MACD 偏多" if MACD值 > 0 else "MACD 偏弱"

    說明 = f"{均線描述}；{趨勢描述}；{MACD描述}；RSI={RSI14:.1f}"

    技術資料 = {
        "MA5": f"{MA5:.2f}",
        "MA20": f"{MA20:.2f}",
        "MA60": f"{MA60:.2f}",
        "RSI(14)": f"{RSI14:.1f}",
        "MACD": f"{MACD值:.3f}",
        "20日平均成交量": f"{二十日平均量:,.0f}"
    }

    return 分數, 技術資料, 說明


# ─────────────────────────────────────────────
# 基本面：本益比／殖利率／股價淨值比
# 資料來源：TWSE 個股日本益比、殖利率及股價淨值比 (BWIBBU_d)
# ─────────────────────────────────────────────

def 基本面評分(股票代號):

    網址 = "https://www.twse.com.tw/exchangeReport/BWIBBU_d"

    for 日期 in 取得候選日期():

        try:
            回應 = requests.get(
                網址,
                params={
                    "response": "json",
                    "date": 日期,
                    "stockNo": 股票代號
                },
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT
            )
            回應.raise_for_status()
            資料 = 回應.json()
        except Exception:
            continue

        if 資料.get("stat") != "OK":
            continue

        欄位 = 資料.get("fields", [])
        rows = 資料.get("data", [])

        if not rows:
            continue

        row = rows[-1]  # 該股票最新一筆

        殖利率索引 = 找欄位索引(欄位, ["殖利率"])
        本益比索引 = 找欄位索引(欄位, ["本益比"])
        股價淨值比索引 = 找欄位索引(欄位, ["股價淨值比"])

        殖利率 = 安全轉數字(row[殖利率索引]) if 殖利率索引 is not None else None
        本益比 = 安全轉數字(row[本益比索引]) if 本益比索引 is not None else None
        股價淨值比 = 安全轉數字(row[股價淨值比索引]) if 股價淨值比索引 is not None else None

        分數 = 50
        說明片段 = []

        if 本益比 is not None and 本益比 > 0:
            if 本益比 < 15:
                分數 += 15
            elif 本益比 < 25:
                分數 += 8
            else:
                分數 -= 5
            說明片段.append(f"本益比 {本益比:.2f} 倍")
        else:
            說明片段.append("本益比：暫無法取得（可能為虧損股或資料缺漏）")

        if 股價淨值比 is not None and 股價淨值比 > 0:
            if 股價淨值比 < 1.5:
                分數 += 15
            elif 股價淨值比 < 3:
                分數 += 8
            else:
                分數 -= 5
            說明片段.append(f"股價淨值比 {股價淨值比:.2f} 倍")
        else:
            說明片段.append("股價淨值比：暫無法取得")

        if 殖利率 is not None:
            if 殖利率 >= 5:
                分數 += 20
            elif 殖利率 >= 3:
                分數 += 12
            elif 殖利率 > 0:
                分數 += 5
            說明片段.append(f"殖利率 {殖利率:.2f}%")
        else:
            說明片段.append("殖利率：暫無法取得")

        分數 = max(0, min(100, round(分數)))

        說明 = f"資料日期 {日期}；" + "、".join(說明片段)

        基本資料 = {
            "本益比": f"{本益比:.2f}" if 本益比 is not None else "無資料",
            "股價淨值比": f"{股價淨值比:.2f}" if 股價淨值比 is not None else "無資料",
            "殖利率(%)": f"{殖利率:.2f}" if 殖利率 is not None else "無資料",
        }

        return 分數, 說明, 基本資料

    return (
        50,
        "近期無法取得本益比／殖利率／股價淨值比資料，暫以中性 50 分計算。",
        {}
    )


# ─────────────────────────────────────────────
# 籌碼面：三大法人買賣超 ＋ 融資融券餘額
# 資料來源：
#   TWSE 三大法人買賣金額統計表 (T86)
#   TWSE 融資融券餘額 (MI_MARGN)
# ─────────────────────────────────────────────

def 三大法人買賣超(股票代號):

    網址 = "https://www.twse.com.tw/fund/T86"

    for 日期 in 取得候選日期():

        try:
            回應 = requests.get(
                網址,
                params={
                    "response": "json",
                    "date": 日期,
                    "selectType": "ALL"
                },
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT
            )
            回應.raise_for_status()
            資料 = 回應.json()
        except Exception:
            continue

        if 資料.get("stat") != "OK":
            continue

        欄位 = 資料.get("fields", [])
        rows = 資料.get("data", [])

        目標 = None
        for row in rows:
            if row and row[0].strip() == 股票代號:
                目標 = row
                break

        if 目標 is None:
            continue

        外資索引 = 找欄位索引(欄位, ["外陸資買賣超", "外資買賣超"])
        投信索引 = 找欄位索引(欄位, ["投信買賣超"])
        自營商索引 = 找欄位索引(欄位, ["自營商買賣超股數"])
        三大法人索引 = 找欄位索引(欄位, ["三大法人買賣超"])

        外資 = 安全轉數字(目標[外資索引]) if 外資索引 is not None else None
        投信 = 安全轉數字(目標[投信索引]) if 投信索引 is not None else None
        自營商 = 安全轉數字(目標[自營商索引]) if 自營商索引 is not None else None
        三大法人 = 安全轉數字(目標[三大法人索引]) if 三大法人索引 is not None else None

        return {
            "日期": 日期,
            "外資買賣超股數": 外資,
            "投信買賣超股數": 投信,
            "自營商買賣超股數": 自營商,
            "三大法人合計買賣超股數": 三大法人,
        }

    return None


def 融資融券餘額(股票代號):

    網址 = "https://www.twse.com.tw/exchangeReport/MI_MARGN"

    for 日期 in 取得候選日期():

        try:
            回應 = requests.get(
                網址,
                params={
                    "response": "json",
                    "date": 日期,
                    "selectType": "ALL"
                },
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT
            )
            回應.raise_for_status()
            資料 = 回應.json()
        except Exception:
            continue

        if 資料.get("stat") != "OK":
            continue

        tables = 資料.get("tables") or [資料]

        for table in tables:
            欄位 = table.get("fields", [])
            rows = table.get("data", [])

            目標 = None
            for row in rows:
                if row and row[0].strip() == 股票代號:
                    目標 = row
                    break

            if 目標 is None:
                continue

            融資餘額索引 = 找欄位索引(欄位, ["融資今日餘額", "融資餘額"])
            融資增減索引 = 找欄位索引(欄位, ["融資買進", "融資"])
            融券餘額索引 = 找欄位索引(欄位, ["融券今日餘額", "融券餘額"])

            融資餘額 = (
                安全轉數字(目標[融資餘額索引])
                if 融資餘額索引 is not None else None
            )
            融券餘額 = (
                安全轉數字(目標[融券餘額索引])
                if 融券餘額索引 is not None else None
            )

            return {
                "日期": 日期,
                "融資餘額(張)": 融資餘額,
                "融券餘額(張)": 融券餘額,
            }

    return None


def 籌碼面評分(股票代號):

    法人資料 = 三大法人買賣超(股票代號)
    融資券資料 = 融資融券餘額(股票代號)

    分數 = 50
    說明片段 = []
    籌碼資料 = {}

    if 法人資料:

        三大法人 = 法人資料.get("三大法人合計買賣超股數")
        外資 = 法人資料.get("外資買賣超股數")
        投信 = 法人資料.get("投信買賣超股數")

        if 三大法人 is not None:
            if 三大法人 > 0:
                分數 += min(25, 三大法人 / 2_000_000 * 25)
                說明片段.append(
                    f"三大法人合計買超約 {三大法人:,.0f} 股"
                )
            elif 三大法人 < 0:
                分數 -= min(25, abs(三大法人) / 2_000_000 * 25)
                說明片段.append(
                    f"三大法人合計賣超約 {abs(三大法人):,.0f} 股"
                )
            else:
                說明片段.append("三大法人買賣超接近持平")

        if 外資 is not None:
            if 外資 > 0:
                分數 += 5
            elif 外資 < 0:
                分數 -= 5

        if 投信 is not None:
            if 投信 > 0:
                分數 += 5
            elif 投信 < 0:
                分數 -= 5

        籌碼資料["外資買賣超(股)"] = (
            f"{外資:,.0f}" if 外資 is not None else "無資料"
        )
        籌碼資料["投信買賣超(股)"] = (
            f"{投信:,.0f}" if 投信 is not None else "無資料"
        )
        籌碼資料["自營商買賣超(股)"] = (
            f"{法人資料.get('自營商買賣超股數'):,.0f}"
            if 法人資料.get("自營商買賣超股數") is not None
            else "無資料"
        )
        籌碼資料["三大法人合計買賣超(股)"] = (
            f"{三大法人:,.0f}" if 三大法人 is not None else "無資料"
        )
        籌碼資料["法人資料日期"] = 法人資料.get("日期", "無資料")

    else:
        說明片段.append("近期無法取得三大法人買賣超資料")

    if 融資券資料:

        融資餘額 = 融資券資料.get("融資餘額(張)")
        融券餘額 = 融資券資料.get("融券餘額(張)")

        if 融券餘額 is not None and 融券餘額 > 0:
            說明片段.append(f"融券餘額 {融券餘額:,.0f} 張")

        if 融資餘額 is not None:
            說明片段.append(f"融資餘額 {融資餘額:,.0f} 張")

        籌碼資料["融資餘額(張)"] = (
            f"{融資餘額:,.0f}" if 融資餘額 is not None else "無資料"
        )
        籌碼資料["融券餘額(張)"] = (
            f"{融券餘額:,.0f}" if 融券餘額 is not None else "無資料"
        )

    else:
        說明片段.append("近期無法取得融資融券資料")

    分數 = max(0, min(100, round(分數)))

    if not 說明片段:
        說明 = "近期無法取得籌碼面相關資料，暫以中性 50 分計算。"
    else:
        說明 = "、".join(說明片段)

    return 分數, 說明, 籌碼資料


# ─────────────────────────────────────────────
# 千張大戶：集保結算所股權分散表（TDCC 開放資料）
# 資料集：集保戶股權分散表（依股數分級）
# 「1,000,001股以上」＝ 持股 1,000 張以上的大戶
# 注意：TDCC 只提供「當週最新一次」的快照，
# 沒有官方 API 可直接查歷史比較，
# 所以這裡不會虛構「較上期」的變化量。
# ─────────────────────────────────────────────

def 千張大戶資訊(股票代號):

    網址 = "https://opendata.tdcc.com.tw/getOD.ashx"

    try:
        回應 = requests.get(
            網址,
            params={"id": "1-5"},
            headers={"User-Agent": USER_AGENT},
            timeout=30
        )
        回應.raise_for_status()
    except Exception as e:
        return {
            "可用": False,
            "說明": f"無法連線至集保結算所開放資料：{e}"
        }

    try:
        內容 = 回應.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(內容))
    except Exception as e:
        return {
            "可用": False,
            "說明": f"集保資料格式解析失敗：{e}"
        }

    符合股票的分級列表 = []
    資料日期 = None

    for row in reader:

        代號欄位 = None
        for key in row.keys():
            if key and ("證券代號" in key or "股票代號" in key):
                代號欄位 = key
                break

        if 代號欄位 is None:
            continue

        if row.get(代號欄位, "").strip() != 股票代號:
            continue

        符合股票的分級列表.append(row)

        for key in row.keys():
            if key and "資料日期" in key:
                資料日期 = row.get(key)

    if not 符合股票的分級列表:
        return {
            "可用": False,
            "說明": "在最新一期集保股權分散表中查無此股票代號，"
                   "可能是興櫃、剛掛牌或資料尚未更新。"
        }

    大戶人數 = 0
    大戶股數 = 0
    全體人數 = 0
    全體股數 = 0

    for row in 符合股票的分級列表:

        分級欄位 = next(
            (k for k in row if k and "級距" in k or (k and "分級" in k)),
            None
        )
        人數欄位 = next((k for k in row if k and "人數" in k), None)
        股數欄位 = next(
            (k for k in row if k and ("股數" in k and "占" not in k)),
            None
        )

        if not (人數欄位 and 股數欄位):
            continue

        人數 = 安全轉數字(row.get(人數欄位), 0) or 0
        股數 = 安全轉數字(row.get(股數欄位), 0) or 0

        全體人數 += 人數
        全體股數 += 股數

        分級文字 = row.get(分級欄位, "") if 分級欄位 else ""

        # 判斷是否為「1,000,001股以上」＝千張以上大戶
        if "1,000,001" in 分級文字 or "1000001" in 分級文字.replace(",", ""):
            大戶人數 += 人數
            大戶股數 += 股數

    if 全體股數 == 0:
        return {
            "可用": False,
            "說明": "取得資料但股數為 0，暫無法計算大戶比例。"
        }

    大戶比例 = 大戶股數 / 全體股數 * 100

    if 大戶比例 >= 60:
        大戶評分 = 90
    elif 大戶比例 >= 45:
        大戶評分 = 78
    elif 大戶比例 >= 30:
        大戶評分 = 65
    elif 大戶比例 >= 15:
        大戶評分 = 50
    else:
        大戶評分 = 35

    return {
        "可用": True,
        "資料日期": 資料日期 or "無資料",
        "千張以上大戶戶數": int(大戶人數),
        "千張以上大戶持股數(股)": int(大戶股數),
        "千張以上大戶持股比例(%)": round(大戶比例, 2),
        "大戶評分": 大戶評分,
        "說明": (
            f"千張以上大戶共 {int(大戶人數):,} 戶，"
            f"合計持股比例 {大戶比例:.2f}%"
            "（TDCC 未提供官方歷史比對，"
            "故不顯示「較上期」增減，避免虛構數字）"
        )
    }


# ─────────────────────────────────────────────
# 綜合評級
# ─────────────────────────────────────────────

def 綜合評級(分數):

    if 分數 >= 85:
        return "🟢 強勢"
    elif 分數 >= 70:
        return "🟢 偏多"
    elif 分數 >= 55:
        return "🟡 中性偏多"
    elif 分數 >= 40:
        return "🟠 中性偏弱"
    else:
        return "🔴 偏弱"


# ─────────────────────────────────────────────
# 主分析函式
# ─────────────────────────────────────────────

def analyze_stock(股票代號):

    收盤價, 成交量 = 取得行情(股票代號)

    技術分數, 技術資料, 技術說明 = 技術面評分(收盤價, 成交量)

    基本分數, 基本說明, 基本資料 = 基本面評分(股票代號)

    籌碼分數, 籌碼說明, 籌碼資料 = 籌碼面評分(股票代號)

    大戶資訊 = 千張大戶資訊(股票代號)

    # 若大戶資料可用，讓大戶評分小幅影響籌碼面總分（權重 20%）
    if 大戶資訊.get("可用"):
        籌碼分數 = round(
            籌碼分數 * 0.8 + 大戶資訊["大戶評分"] * 0.2
        )
        籌碼分數 = max(0, min(100, 籌碼分數))

    # 權重：基本面 35%、籌碼面 30%、技術面 35%
    綜合分數 = round(
        基本分數 * 0.35
        + 籌碼分數 * 0.30
        + 技術分數 * 0.35
    )

    return {
        "code": 股票代號,
        "name": f"{股票代號} 台股",
        "price": 收盤價[-1],

        "fundamental": 基本分數,
        "chip": 籌碼分數,
        "technical": 技術分數,
        "overall": 綜合分數,
        "rating": 綜合評級(綜合分數),

        "fundamental_reason": 基本說明,
        "chip_reason": 籌碼說明,
        "technical_reason": 技術說明,

        "fundamental_data": 基本資料,
        "chip_data": 籌碼資料,
        "technical_data": 技術資料,

        "big_holder": 大戶資訊,

        "source": (
            "Yahoo Finance 行情、TWSE 本益比／殖利率／股價淨值比、"
            "TWSE 三大法人買賣超、TWSE 融資融券、"
            "TDCC 集保股權分散表 ＋ 本機評分引擎"
        )
    }
