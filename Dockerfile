# Dockerfile
FROM python:3.7-stretch

ENV PORT=5000

RUN apt-get update -y
RUN apt-get install -y python-pip python-dev build-essential

WORKDIR /app
COPY requirements.txt  ./
RUN pip install -r requirements.txt

HEALTHCHECK --interval=5m --timeout=3s \
  CMD curl -f http://localhost:$PORT/ping || exit 1

COPY . /app


ENTRYPOINT ["python"]
CMD ["app.py"]
