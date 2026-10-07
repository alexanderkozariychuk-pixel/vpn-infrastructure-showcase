FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh

# The app runs unprivileged. Its SSH key is mounted from the host at
# /home/app/.ssh (owned by uid 10001 there); nothing else is written to disk.
RUN useradd --uid 10001 --create-home --home-dir /home/app --shell /usr/sbin/nologin app
USER app

EXPOSE 8000

CMD ["./entrypoint.sh"]
