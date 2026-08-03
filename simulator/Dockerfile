FROM python:3.12-slim
WORKDIR /simulator
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY geovision_simulator.py .
CMD ["python", "geovision_simulator.py", "run", "--scenario", "demo"]
