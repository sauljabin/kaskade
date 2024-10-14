FROM python:3.10
ENV COLORTERM="truecolor"
ENV TERM="xterm-256color"
WORKDIR /kaskade
COPY dist/ /kaskade/
RUN pip install --no-cache-dir kaskade*.whl && rm ./*
ENTRYPOINT ["kaskade"]
