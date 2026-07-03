FROM postgres:15

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt
COPY main.py .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 9002
ENTRYPOINT ["/entrypoint.sh"]
