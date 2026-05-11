FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    iproute2 \
    wireguard-tools \
    sudo \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN echo "ALL ALL=(ALL) NOPASSWD: /usr/sbin/ip, /usr/bin/awg-quick, /usr/bin/awg, /usr/bin/systemctl, /usr/bin/journalctl" >> /etc/sudoers

CMD ["python", "main.py"]