FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY examples ./examples
RUN pip install --no-cache-dir .

ENV LANTERN_HOME=/data
EXPOSE 8787
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=2)"
CMD ["lantern", "serve", "--host", "0.0.0.0", "--port", "8787"]
