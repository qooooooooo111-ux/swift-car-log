import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- 設定頁面資訊 ---
st.set_page_config(page_title="Suzuki Swift 雲端車庫", page_icon="☁️", layout="centered")

# --- 連線設定 (這是最關鍵的地方) ---
SCOPE = ['https://www.googleapis.com/auth/spreadsheets', "https://www.googleapis.com/auth/drive"]
CREDS_FILE = 'service_account.json'  # 剛剛下載的鑰匙檔名
SHEET_NAME = 'Swift_Log'             # Google 試算表的檔名

import json # 記得最上面要加上這行

# --- 連接 Google Sheets 函式 ---
def get_google_sheet_data(worksheet_name):
    try:
        # 智慧判斷：如果是在雲端，就讀取隱藏的 Secrets；如果在電腦，就讀取資料夾的 json 檔
        if "gcp_json" in st.secrets:
            creds_dict = json.loads(st.secrets["gcp_json"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
            
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        worksheet = sheet.worksheet(worksheet_name)
        data = worksheet.get_all_records()
        return pd.DataFrame(data), worksheet
    except Exception as e:
        st.error(f"連線失敗，請檢查金鑰或網路。\n錯誤訊息: {e}")
        st.stop()

# --- 讀取資料 ---
st.sidebar.write("🔄 連線雲端中...")
df_maint, sheet_maint = get_google_sheet_data("維修紀錄")
df_fuel, sheet_fuel = get_google_sheet_data("加油紀錄")
st.sidebar.success("雲端同步完成！")

# 取得目前里程 (邏輯：找兩張表中最大的里程數)
max_km_maint = df_maint["里程"].max() if not df_maint.empty else 0
max_km_fuel = df_fuel["里程"].max() if not df_fuel.empty else 0
# 如果都是 0，預設 150000
current_km = max(max_km_maint, max_km_fuel)
if current_km == 0: current_km = 150000

# --- 側邊欄：輸入區 ---
st.sidebar.header("📝 新增雲端紀錄")
input_type = st.sidebar.radio("選擇操作", ["記錄加油", "記錄維修/改裝"])

if input_type == "記錄加油":
    f_date = st.sidebar.date_input("日期", datetime.now()).strftime("%Y-%m-%d")
    f_km = st.sidebar.number_input("加油時里程", value=int(current_km))
    
    # 改成輸入公升數與「總價」
    f_liters = st.sidebar.number_input("加了幾公升 (L)", value=30.00, step=1.0)
    f_total = st.sidebar.number_input("總花費 (元)", value=1000, step=10)
    
    # 讓電腦自動反推單價 (四捨五入到小數點第二位)
    f_price = round(f_total / f_liters, 2) if f_liters > 0 else 0
    
    # 貼心提示：顯示反推出來的單價給車主看
    st.sidebar.info(f"💡 系統換算單價： {f_price} 元/公升")
    
    if st.sidebar.button("上傳加油紀錄"):
        # 存入資料庫時，把算好的單價(f_price)跟總價(f_total)寫進去
        new_row = [f_date, f_km, f_liters, f_price, int(f_total)]
        sheet_fuel.append_row(new_row)
        st.sidebar.success("✅ 上傳成功！")
        st.rerun()

elif input_type == "記錄維修/改裝":
    m_date = st.sidebar.date_input("日期", datetime.now()).strftime("%Y-%m-%d")
    m_km = st.sidebar.number_input("當下里程", value=int(current_km))
    m_item = st.sidebar.text_input("項目名稱", "例如：更換機油")
    m_cat = st.sidebar.selectbox("類別", ["定期保養 (有壽命)", "消耗品", "改裝升級", "維修"])
    m_cost = st.sidebar.number_input("費用", value=0)
    m_note = st.sidebar.text_area("備註")
    
    if st.sidebar.button("上傳保養紀錄"):
        new_row = [m_date, m_km, m_item, m_cat, m_cost, m_note]
        sheet_maint.append_row(new_row)
        st.sidebar.success("✅ 上傳成功！")
        st.rerun()

# --- 主畫面 ---
st.title("☁️ Swift 雲端車庫")
st.caption("資料來源：Google Sheets")
st.markdown(f"### 最新里程： `{current_km:,} km`")
st.markdown("---")

# --- 核心功能：零件壽命健康度監控 (雙重條件：里程 + 時間) ---
st.subheader("⚠️ 零件健康度監控 (里程與時間雙重把關)")

# 定義零件建議壽命：同時包含「公里數(km)」與「幾個月(months)」
# 你可以隨時在這裡新增或修改項目！
parts_lifespan = {
    "機油": {"km": 5000, "months": 6},
    "變速箱油": {"km": 20000, "months": 24},
    "輪胎": {"km": 40000, "months": 36},
    "火星塞": {"km": 30000, "months": 24},
    "電瓶": {"km": 40000, "months": 24},   # 電瓶非常受時間影響
    "雨刷": {"km": 10000, "months": 12},   # 雨刷膠條會隨時間硬化
    "冷氣濾網": {"km": 10000, "months": 12},
    "空氣濾網": {"km": 20000, "months": 24},
    "後引擎腳": {"km": 80000, "months": 60}
}

latest_changes = {}
if not df_maint.empty:
    # 確保里程是數字，並把「日期」轉換成系統能看懂的時間格式
    df_maint["里程"] = pd.to_numeric(df_maint["里程"], errors='coerce').fillna(0)
    df_maint["日期"] = pd.to_datetime(df_maint["日期"], errors='coerce')
    
    for part in parts_lifespan.keys():
        # 搜尋包含該零件名稱的紀錄
        part_records = df_maint[df_maint["項目"].astype(str).str.contains(part, na=False)]
        if not part_records.empty:
            # 找出最新（里程最大）的那一筆紀錄
            latest_record = part_records.sort_values(by="里程", ascending=False).iloc[0]
            latest_changes[part] = {
                "last_km": latest_record["里程"],
                "last_date": latest_record["日期"]
            }
        else:
            latest_changes[part] = None

cols = st.columns(2)
today = pd.to_datetime('today')

for i, (part, limits) in enumerate(parts_lifespan.items()):
    record = latest_changes.get(part)
    
    # 如果完全沒紀錄
    if record is None or pd.isna(record["last_date"]):
        with cols[i % 2]:
            st.warning(f"**{part}** - 尚無紀錄")
        continue

    last_km = record["last_km"]
    last_date = record["last_date"]
    
    # 1. 計算【里程】消耗比例
    used_km = current_km - last_km
    if used_km < 0: used_km = 0
    usage_percent_km = used_km / limits["km"]
    
    # 2. 計算【時間】消耗比例 (以 30.4 天為一個月計算)
    days_passed = (today - last_date).days
    used_months = days_passed / 30.4
    if used_months < 0: used_months = 0
    usage_percent_time = used_months / limits["months"]
    
    # 3. 殘酷二選一：取消耗比例較高的那個當作標準
    is_time_critical = usage_percent_time > usage_percent_km
    usage_percent = max(usage_percent_km, usage_percent_time)
    
    # 決定顏色與狀態
    status_emoji = "✅"
    if usage_percent > 0.8: status_emoji = "⚠️"
    if usage_percent >= 1.0: status_emoji = "❌"
    
    display_percent = min(usage_percent, 1.0)
    
    # 顯示原因：告訴車主是因為里程到了，還是時間到了
    if is_time_critical:
        reason_text = f"已過 {int(used_months)} 個月 (建議 {limits['months']} 個月換)"
    else:
        reason_text = f"已跑 {int(used_km)} km (建議 {limits['km']} km 換)"

    with cols[i % 2]:
        st.write(f"**{part}** ({status_emoji})")
        st.progress(display_percent, text=reason_text)
        if usage_percent >= 1.0:
            st.error(f"該換了！ ({reason_text})")

st.markdown("---")
# --- 歷史紀錄顯示 ---
tab1, tab2 = st.tabs(["🔧 保養紀錄", "⛽ 加油紀錄"])

with tab1:
    if not df_maint.empty:
        st.dataframe(df_maint.sort_values(by="里程", ascending=False), use_container_width=True)
    else:
        st.info("目前還沒有保養紀錄，請從左側新增。")

with tab2:
    if not df_fuel.empty:
        # 計算油耗
        df_fuel["里程"] = pd.to_numeric(df_fuel["里程"], errors='coerce')
        df_fuel["公升數"] = pd.to_numeric(df_fuel["公升數"], errors='coerce')
        total_dist = df_fuel["里程"].max() - df_fuel["里程"].min()
        total_liters = df_fuel["公升數"].sum()
        avg_km_l = total_dist / total_liters if total_liters > 0 and total_dist > 0 else 0
        
        col_fuel_1, col_fuel_2 = st.columns(2)
        col_fuel_1.metric("估計平均油耗", f"{avg_km_l:.2f} km/L")
        col_fuel_2.metric("總加油花費", f"${df_fuel['總價'].sum():,}")
        
        st.dataframe(df_fuel.sort_values(by="里程", ascending=False), use_container_width=True)
    else:
        st.info("目前還沒有加油紀錄，請從左側新增。")





