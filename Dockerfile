# Menggunakan image Python
FROM python:3.9

# Set working directory
WORKDIR /app

# Salin semua file ke dalam container
COPY . .

# Instal dependensi dari requirements.txt
RUN pip install -r requirements.txt

# Jalankan bot
CMD ["python", "bot.py"]
