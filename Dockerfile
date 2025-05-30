FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p data output

COPY data/BESS_Data.xlsx data/

COPY app/ app/

CMD ["python", "-m", "app.main"]