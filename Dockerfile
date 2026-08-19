# Imagen oficial de Playwright Python con navegadores y dependencias del sistema operativo
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Directorio de trabajo en el contenedor
WORKDIR /app

# Copiar archivo de requerimientos e instalarlos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente del proyecto
COPY . .

# Puerto por defecto en Render (Render inyectará la variable PORT automáticamente)
ENV PORT=10000
EXPOSE 10000

# Comando para iniciar Uvicorn con 1 worker (optimizado para plan de 512MB RAM)
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port $PORT --workers 1"]
