FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
COPY bootstrap_admin.py .
COPY lead_hunter_worker.py .
COPY migrate_sqlite_to_postgres.py .
EXPOSE 8080
CMD ["sh","-c","uvicorn main:app --host 0.0.0.0 --port 8080 --workers ${WEB_CONCURRENCY:-4}"]
