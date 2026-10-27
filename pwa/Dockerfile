# Pinned to the image the portal is built on. Unpinned, every new upstream
# build of the tag invalidated the cache and re-ran apt, and deb.debian.org
# is barely reachable from the portal's host (2026-10-27: a deploy hung on
# apt-get update for minutes). Move the pin on purpose, at a quiet time.
FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

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
