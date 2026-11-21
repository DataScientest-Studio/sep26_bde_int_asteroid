FROM python:3.12-slim
WORKDIR /app
COPY requirements/api.txt .
RUN pip install --no-cache-dir -r api.txt
COPY . .
CMD ["python3", "src/ml/dataset.py"]
