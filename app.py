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
    f_liters = st.sidebar.number_input("加了幾公升", value=30.0)
    f_price = st.sidebar.number_input("單價 (元/公升)", value=30.0)
    
    if st.sidebar.button("上傳加油紀錄"):
        new_row = [f_date, f_km, f_liters, f_price, int(f_liters * f_price)]
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

# --- 核心功能：零件壽命健康度監控 (邏輯不變) ---
st.subheader("⚠️ 零件健康度監控")
parts_lifespan = {
    "機油": 5000,
    "變速箱油": 20000,
    "輪胎": 40000,
    "火星塞": 30000,
    "煞車油": 40000,
    "冷卻水": 20000
}

latest_changes = {}
if not df_maint.empty:
    # 確保里程是數字格式
    df_maint["里程"] = pd.to_numeric(df_maint["里程"], errors='coerce').fillna(0)
    
    for part in parts_lifespan.keys():
        part_records = df_maint[df_maint["項目"].astype(str).str.contains(part, na=False)]
        if not part_records.empty:
            last_km = part_records["里程"].max()
            latest_changes[part] = last_km
        else:
            latest_changes[part] = 0

cols = st.columns(2)
for i, (part, lifespan) in enumerate(parts_lifespan.items()):
    last_km = latest_changes.get(part, 0)
    
    if last_km == 0:
        with cols[i % 2]:
            st.warning(f"**{part}** - 尚無紀錄")
        continue

    used_km = current_km - last_km
    if used_km < 0: used_km = 0
    usage_percent = used_km / lifespan
    
    status_emoji = "✅"
    if usage_percent > 0.8: status_emoji = "⚠️"
    if usage_percent >= 1.0: status_emoji = "❌"
    
    # 限制進度條最大 100%
    display_percent = min(usage_percent, 1.0)

    with cols[i % 2]:
        st.write(f"**{part}** ({status_emoji})")
        st.progress(display_percent, text=f"已跑 {used_km} / {lifespan} km")
        if usage_percent >= 1.0:
            st.error(f"該換了！")

st.markdown("---")

# --- 歷史紀錄顯示 ---
tab1, tab2 = st.tabs(["🔧 保養紀錄", "⛽ 加油紀錄"])

with tab1:
    st.dataframe(df_maint, use_container_width=True)

with tab2:
    if not df_fuel.empty:
        df_fuel["里程"] = pd.to_numeric(df_fuel["里程"], errors='coerce')
        df_fuel["公升數"] = pd.to_numeric(df_fuel["公升數"], errors='coerce')
        
        total_dist = df_fuel["里程"].max() - df_fuel["里程"].min()
        total_liters = df_fuel["公升數"].sum()
        avg_km_l = total_dist / total_liters if total_liters > 0 and total_dist > 0 else 0
        
        st.metric("估計平均油耗", f"{avg_km_l:.2f} km/L")
    st.dataframe(df_fuel, use_container_width=True)