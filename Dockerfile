FROM python:3.13-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY pyproject.toml ./
COPY tina ./tina
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 tina \
    && mkdir -p /app/reports /home/tina/.tradingagents \
    && chown tina:tina /app/reports /home/tina/.tradingagents
USER 10001:10001
CMD ["uvicorn", "tina.api:factory", "--factory", "--host", "0.0.0.0", "--port", "8081", "--workers", "1"]

FROM app AS research
USER root
RUN pip install --no-cache-dir '.[research]'
USER 10001:10001
CMD ["python", "-m", "tina.research"]

FROM app AS reports
USER root
RUN pip install --no-cache-dir '.[reports]'
USER 10001:10001
CMD ["python", "-m", "tina.report"]
