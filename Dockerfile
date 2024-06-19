FROM python:3.10
WORKDIR /kaskade
COPY dist/ /kaskade/
RUN pip install --no-cache-dir kaskade*.whl && rm ./*
ENTRYPOINT ["kaskade"]
