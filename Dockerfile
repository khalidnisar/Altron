FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN addgroup --system altron && adduser --system --ingroup altron altron
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --upgrade pip && pip install '.[all]'
RUN mkdir -p /app/data && chown -R altron:altron /app
USER altron
EXPOSE 8000
CMD ["uvicorn", "altron.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
