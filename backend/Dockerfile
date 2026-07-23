FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# sentence-transformers depends on torch. Installing torch from the CPU-only
# index first keeps the image ~1 GB instead of pulling the ~2.5 GB CUDA build.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run DB migrations, then serve. Railway (and most PaaS) inject $PORT;
# fall back to 8000 for local runs.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
