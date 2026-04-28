import json
import redis
import pika
import mysql.connector
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

app = FastAPI()

# Kết nối Redis (Naming Service: redis_cache)
redis_client = redis.Redis(host='redis_cache', port=6379, db=0, decode_responses=True)

# Kết nối RabbitMQ (Naming Service: rabbit_broker)
credentials = pika.PlainCredentials('admin', 'admin123')
rabbit_params = pika.ConnectionParameters('rabbit_broker', 5672, '/', credentials)

# Định dạng JSON đầu vào cho Endpoint
class OrderRequest(BaseModel):
    user_id: int
    product_id: int
    quantity: int

def get_mysql_connection():
    return mysql.connector.connect(
        host='mysql_db',
        database='noah_sales',
        user='noah_user',
        password='noah_password'
    )

@app.post("/api/orders", status_code=status.HTTP_202_ACCEPTED)
def create_order(order: OrderRequest):
    # 1. Validate dữ liệu
    if order.quantity <= 0:
        raise HTTPException(status_code=400, detail="Số lượng phải lớn hơn 0")

    redis_key = f"product:{order.product_id}:stock"

    # 2. KIỂM TRA TỒN KHO TRÊN REDIS (Overselling Protection)
    # Lệnh DECRBY trừ nguyên tử số lượng đặt mua khỏi tồn kho hiện tại
    stock_after_decr = redis_client.decrby(redis_key, order.quantity)

    # Nếu tồn kho âm -> Hết hàng -> Trả lại số lượng vừa trừ và báo lỗi
    if stock_after_decr < 0:
        redis_client.incrby(redis_key, order.quantity) # Rollback
        raise HTTPException(status_code=400, detail="Out of Stock")

    # 3. GHI NHẬN SƠ BỘ VÀO MYSQL (Status: PENDING)
    db = get_mysql_connection()
    cursor = db.cursor()
    
    insert_query = """
        INSERT INTO orders (user_id, product_id, quantity, status) 
        VALUES (%s, %s, %s, 'PENDING')
    """
    cursor.execute(insert_query, (order.user_id, order.product_id, order.quantity))
    db.commit()
    
    # Lấy ID của đơn hàng vừa tạo để gửi sang hệ thống Tài chính
    order_id = cursor.lastrowid
    
    cursor.close()
    db.close()

    # 4. PUBLISH JSON VÀO RABBITMQ (Mô hình Fire-and-Forget)
    message_payload = {
        "order_id": order_id,
        "user_id": order.user_id,
        "product_id": order.product_id,
        "quantity": order.quantity
    }
    
    try:
        connection = pika.BlockingConnection(rabbit_params)
        channel = connection.channel()
        channel.queue_declare(queue='order_queue', durable=True)
        
        channel.basic_publish(
            exchange='',
            routing_key='order_queue',
            body=json.dumps(message_payload),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Đảm bảo message không bị mất nếu RabbitMQ sập
            )
        )
        connection.close()
    except Exception as e:
        # Nếu đẩy vào Queue thất bại, cần rollback Redis và MySQL ở các hệ thống thực tế
        print(f"[ERROR] Không thể gửi message vào Queue: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error: Message Queue Failed")

    # 5. PHẢN HỒI NHANH CHO CLIENT
    return {
        "message": "Order received", 
        "order_id": order_id,
        "status": "PENDING"
    }