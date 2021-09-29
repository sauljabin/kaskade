FROM python:3.7
WORKDIR /kaskade
COPY dist/ /kaskade/
RUN pip install kaskade*.whl
ENTRYPOINT ["kaskade"]