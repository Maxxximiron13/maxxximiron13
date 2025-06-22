# Используем базовый образ Python
FROM python:3.11.2-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл требований в контейнер
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы приложения в контейнер
COPY . .

# Команда для запуска бота
CMD ["python", "./bot.py"]
