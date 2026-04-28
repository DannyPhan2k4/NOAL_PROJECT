import os
import time
import shutil
import pandas as pd
import mysql.connector
import redis
from mysql.connector import Error

# Cấu hình đường dẫn thư mục gắn với Volumes
INPUT_DIR = '/app/input'
PROCESSED_DIR = '/app/processed'
ERROR_DIR = '/app/error'

# Cấu hình Redis (Option 2)
# Tên host 'redis_cache' phải khớp với tên service trong docker-compose.yml
redis_client = redis.Redis(host='redis_cache', port=6379, db=0, decode_responses=True)

def get_db_connection():
    """Thử thách Khởi động lạnh: Tự động retry kết nối database"""
    retries = 5
    while retries > 0:
        try:
            connection = mysql.connector.connect(
                host='mysql_db', # Tên container MySQL trong docker-compose
                database='noah_sales',
                user='noah_user',
                password='noah_password'
            )
            if connection.is_connected():
                return connection
        except Error as e:
            print(f"[WAITING] Database chưa sẵn sàng, thử lại sau 5s... ({e})")
            retries -= 1
            time.sleep(5)
    raise Exception("Không thể kết nối đến MySQL sau nhiều lần thử.")

def process_file(filepath):
    print(f"\n[INFO] Đã phát hiện file mới: {filepath}")
    filename = os.path.basename(filepath)
    
    try:
        # 1. PHASE EXTRACT: Đọc file CSV bằng Pandas
        df = pd.read_csv(filepath)
        
        # 2. PHASE TRANSFORM: Làm sạch và xử lý dữ liệu bẩn
        # Bỏ qua các dòng có quantity < 0 (Log cảnh báo ẩn bên trong)
        df_valid = df[df['quantity'] >= 0]
        invalid_count = len(df) - len(df_valid)
        if invalid_count > 0:
            print(f"[WARNING] Bỏ qua {invalid_count} dòng có số lượng âm.")

        # Xử lý lỗi DUPLICATES (Của Nhóm 7): Gộp các dòng trùng product_id lại và cộng dồn quantity
        df_clean = df_valid.groupby('product_id', as_index=False)['quantity'].sum()

        # 3. PHASE LOAD: Đổ dữ liệu vào MySQL và Redis
        db = get_db_connection()
        cursor = db.cursor()
        
        processed_records = 0
        for index, row in df_clean.iterrows():
            try:
                pid = int(row['product_id'])
                qty = int(row['quantity'])
                
                # Update vào MySQL
                sql_update = "UPDATE products SET quantity = %s WHERE id = %s"
                cursor.execute(sql_update, (qty, pid))
                
                # Nạp đồng thời lên Redis (Chuẩn bị cho Option 2)
                redis_key = f"product:{pid}:stock"
                redis_client.set(redis_key, qty)
                
                processed_records += 1
            except Exception as e:
                print(f"[ERROR] Lỗi dòng dữ liệu product_id {row['product_id']}: {e}")
                continue # Bỏ qua dòng lỗi, chạy tiếp dòng sau (Khả năng chịu lỗi - Resilience)
        
        db.commit()
        cursor.close()
        db.close()
        
        # 4. CLEANUP: Di chuyển file sang mục Processed để đánh dấu hoàn tất [cite: 581-582]
        shutil.move(filepath, os.path.join(PROCESSED_DIR, filename))
        print(f"[SUCCESS] Đã xử lý {processed_records} mã sản phẩm. Đã dọn dẹp file CSV.")

    except Exception as e:
        print(f"[FATAL] File hỏng hoặc sai cấu trúc: {e}")
        # Di chuyển sang thư mục Error nếu file không thể đọc được
        shutil.move(filepath, os.path.join(ERROR_DIR, filename))

def start_watching():
    print("🚀 Watchdog Service Started... Chờ file CSV từ hệ thống Legacy.")
    while True:
        # Quét thư mục Input
        files = os.listdir(INPUT_DIR)
        for file in files:
            if file.endswith('.csv'):
                full_path = os.path.join(INPUT_DIR, file)
                process_file(full_path)
        
        # Nhịp tim của hệ thống: Ngủ 5s để tránh vắt kiệt CPU 
        time.sleep(5)

if __name__ == '__main__':
    # Tạo các thư mục nếu chưa tồn tại (để tránh lỗi khi start)
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(ERROR_DIR, exist_ok=True)
    start_watching()