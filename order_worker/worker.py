import time
import json
import pika
import mysql.connector
import psycopg2
from psycopg2 import OperationalError as PGError
from mysql.connector import Error as MySQLError

# --- CƠ CHẾ KHỞI ĐỘNG LẠNH (RETRY CONNECTIONS) ---
def get_mysql_connection():
    while True:
        try:
            conn = mysql.connector.connect(
                host='mysql_db',
                database='noah_sales',
                user='noah_user',
                password='noah_password'
            )
            return conn
        except MySQLError:
            print("[WAIT] MySQL chưa sẵn sàng, thử lại sau 5s...")
            time.sleep(5)

def get_postgres_connection():
    while True:
        try:
            conn = psycopg2.connect(
                host='postgres_db',
                dbname='noah_finance',
                user='noah_user',
                password='noah_password'
            )
            return conn
        except PGError:
            print("[WAIT] PostgreSQL chưa sẵn sàng, thử lại sau 5s...")
            time.sleep(5)

# --- LOGIC XỬ LÝ ĐƠN HÀNG (CONSUMER CALLBACK) ---
def process_order_callback(ch, method, properties, body):
    order_data = json.loads(body)
    order_id = order_data['order_id']
    user_id = order_data['user_id']
    amount = order_data['quantity'] * 100 # Giả lập tính thành tiền
    
    print(f"\n[RECEIVED] Đang xử lý đơn hàng #{order_id} từ RabbitMQ...")
    
    # 1. Giả lập độ trễ: Kế toán đang duyệt hồ sơ
    time.sleep(1.5)
    
    pg_conn = None
    my_conn = None
    
    try:
        # 2. Ghi hệ thống đích: Insert vào PostgreSQL (Finance)
        pg_conn = get_postgres_connection()
        pg_cursor = pg_conn.cursor()
        
        # Tạo bảng nếu chưa có (Tránh lỗi khởi tạo)
        pg_cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                order_id INT NOT NULL,
                user_id INT NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                status VARCHAR(50) DEFAULT 'PAID'
            )
        """)
        pg_cursor.execute(
            "INSERT INTO transactions (order_id, user_id, amount) VALUES (%s, %s, %s)",
            (order_id, user_id, amount)
        )
        pg_conn.commit()
        print(f"[FINANCE] Đã ghi nhận giao dịch vào PostgreSQL cho đơn #{order_id}")
        
        # 3. Cập nhật trạng thái: Quay lại MySQL đổi PENDING thành COMPLETED
        my_conn = get_mysql_connection()
        my_cursor = my_conn.cursor()
        my_cursor.execute(
            "UPDATE orders SET status = 'COMPLETED' WHERE id = %s",
            (order_id,)
        )
        my_conn.commit()
        print(f"[SALES] Đã chốt trạng thái COMPLETED trong MySQL cho đơn #{order_id}")
        
        # 4. Acknowledge (ACK): Báo RabbitMQ xóa tin nhắn an toàn
        ch.basic_ack(delivery_tag=method.delivery_tag)
        print(f"[DONE] Hoàn tất luồng đơn hàng #{order_id}")

    except Exception as e:
        print(f"[ERROR] Lỗi xử lý đơn hàng #{order_id}: {e}")
        # Nếu lỗi, KHÔNG gửi ACK. RabbitMQ sẽ giữ lại tin nhắn để xử lý sau.
        if pg_conn: pg_conn.rollback()
        if my_conn: my_conn.rollback()
        
    finally:
        if pg_conn: pg_conn.close()
        if my_conn: my_conn.close()

# --- KHỞI ĐỘNG CONSUMER ---
def start_worker():
    credentials = pika.PlainCredentials('admin', 'admin123')
    parameters = pika.ConnectionParameters('rabbit_broker', 5672, '/', credentials)
    
    # Retry kết nối RabbitMQ
    while True:
        try:
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            break
        except Exception:
            print("[WAIT] RabbitMQ chưa sẵn sàng, thử lại sau 5s...")
            time.sleep(5)
            
    channel.queue_declare(queue='order_queue', durable=True)
    
    # Chỉ nhận 1 tin nhắn tại một thời điểm (Fair Dispatch)
    channel.basic_qos(prefetch_count=1)
    
    channel.basic_consume(
        queue='order_queue',
        on_message_callback=process_order_callback
    )
    
    print("👷 Order Worker Started... Đang lắng nghe Queue 'order_queue'. To exit press CTRL+C")
    channel.start_consuming()

if __name__ == '__main__':
    start_worker()