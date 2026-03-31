FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    fonts-liberation \
    build-essential \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

ENV PORT=8000

CMD ["sh", "-c", "python manage.py migrate && gunicorn market.wsgi:application --bind 0.0.0.0:$PORT"]