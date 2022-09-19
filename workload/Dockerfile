FROM python:3

WORKDIR /web
COPY ./ui /web

EXPOSE 80

ENTRYPOINT [ "python3", "-m", "http.server", "80"]
