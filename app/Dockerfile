FROM arm64v8/python:3.9-slim-bullseye as compile-image
ENV PATH=/root/.local/bin:$PATH
WORKDIR /root
COPY requirements.txt requirements.txt
RUN apt-get update && apt-get install -yy --no-install-recommends build-essential librtmidi-dev
RUN python3 -m pip install --upgrade pip &&\
    python3 -m pip install --user -r requirements.txt

FROM arm64v8/python:3.9-slim-bullseye as runtime-image
COPY --from=compile-image /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
RUN apt-get update && apt-get install -yy --no-install-recommends fluidsynth alsa-utils libasound2 librtmidi5 &&\
    rm -rf /var/lib/apt/lists/*

FROM runtime-image
COPY sf/. /sf/.
COPY app/. /app/ 
WORKDIR /app
ENV PATH=/root/.local/bin:/app/bin:$PATH
