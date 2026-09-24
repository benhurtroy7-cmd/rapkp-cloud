FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY engine.py domains.py server.py ./
# pre-fetch the JPL DE421 ephemeris so the first request is not slow
RUN python -c "from skyfield.api import load; load('de421.bsp')" || true
ENV PORT=8000
EXPOSE 8000
CMD ["python", "server.py"]
