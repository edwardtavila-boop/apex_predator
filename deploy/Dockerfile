FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e .
CMD ["uvicorn", "deploy.scripts.dashboard_api:app", "--host", "0.0.0.0", "--port", "8421"]
