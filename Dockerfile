FROM python:3.11-slim

WORKDIR /app

# Dépendances système MINIMALES pour WeasyPrint
RUN apt-get update && apt-get install -y \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copier le projet
COPY . .

# Installer Python
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Port Railway
ENV PORT=8000

# Lancement Django propre
CMD ["gunicorn", "market.wsgi:application", "--bind", "0.0.0.0:8000"]