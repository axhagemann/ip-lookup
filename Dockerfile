FROM python:3.12-slim

RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY upcheck.py .
COPY static/ static/

USER app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
