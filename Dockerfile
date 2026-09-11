FROM python:3.11-slim

WORKDIR /app

# شبکه‌هایی که به pypi.org دسترسی ندارند (از جمله برخی شبکه‌های ایران)
# هنگام build آینه تزریق می‌کنند:
#   docker compose build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# اسکیما قبل از شروع سرویس اعمال می‌شود (web و worker هر دو)
ENTRYPOINT ["sh", "scripts/entrypoint.sh"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]