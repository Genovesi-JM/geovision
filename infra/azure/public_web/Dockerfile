# Existing reviewed runtime; static handler imports no backend application code.
FROM geovisionpilothcwka3w.azurecr.io/geovision-backend@sha256:b3b74c015f0b1a64bb4e1269f029e2c5d019cb08bf5d09f6687a22c0c3e83383
WORKDIR /web
ENV PORT=8080 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --chown=10001:10001 site.py /web/site.py
COPY --chown=10001:10001 public/ /web/public/
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/_site/health', timeout=4).read()"]
ENTRYPOINT ["python", "/web/site.py"]
CMD []
