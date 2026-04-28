# Sử dụng Python Slim để nhẹ máy
FROM python:3.9-slim

# Thiết lập thư mục làm việc
WORKDIR /app

# Copy và cài đặt thư viện trước để tối ưu Cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn vào
COPY watcher.py .

# Chạy watchdog khi container khởi động
CMD ["python", "watcher.py"]