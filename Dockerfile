FROM python:3.13-slim

WORKDIR /app

# Dépendances système pour WeasyPrint + Django
RUN apt-get update && apt-get install -y \
    libgobject-2.0-0 \
    libglib2.0-0 \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    shared-mime-info \
    fonts-liberation \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copier le projet
COPY . .

# Installer Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Port Railway
ENV PORT=8000

# Django migrations + run
CMD ["sh", "-c", "python manage.py migrate && python manage.py runserver 0.0.0.0:$PORT"]