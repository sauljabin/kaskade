FROM python:3.14-slim

ENV COLORTERM="truecolor" \
    TERM="xterm-256color" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 10001 kaskade

RUN --mount=type=bind,source=dist,target=/tmp/dist \
    pip install /tmp/dist/kaskade-*.whl

WORKDIR /kaskade
RUN chown kaskade:kaskade /kaskade
USER kaskade

ENTRYPOINT ["kaskade"]
