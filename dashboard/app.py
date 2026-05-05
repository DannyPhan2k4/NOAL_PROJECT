import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="NOAH Retail Command Center", layout="wide")
st.title("🚀 Hệ thống Đối soát Unified Commerce")

# Cấu hình kết nối qua Kong Gateway
GATEWAY_URL = "http://kong_gateway:8000/report" [cite: 114, 1028]
HEADERS = {"apikey": "noah-secret-key"} [cite: 110, 1090]

# Phân trang (Pagination Challenge)
page = st.sidebar.number_input("Trang dữ liệu", min_value=1, value=1) [cite: 208]

def fetch_data(p):
    try:
        response = requests.get(f"{GATEWAY_URL}?page={p}&limit=10", headers=HEADERS) [cite: 110]
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        st.error(f"Lỗi kết nối Gateway: {e}")
        return None

data = fetch_data(page)

if data and data['data']:
    df = pd.DataFrame(data['data'])
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Bảng doanh thu theo khách hàng")
        st.table(df) [cite: 217]
        
    with col2:
        st.subheader("Biểu đồ doanh thu")
        st.bar_chart(df.set_index('user_id')) [cite: 217]
else:
    st.info("Không có dữ liệu đơn hàng đã thanh toán ở trang này.")