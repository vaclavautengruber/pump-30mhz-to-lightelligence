FROM python:3.6-stretch

RUN pip install paho-mqtt==1.3.1 pylint==1.9.1 pycodestyle==2.3.1 flake8==3.5.0 bandit==1.4.0

ADD pump.py /pump/pump.py

WORKDIR /pump

RUN pylint pump.py && \
    pycodestyle . && \
    flake8 *.py && \
    bandit -r .


FROM python:3.6-alpine3.7

RUN pip3 install paho-mqtt==1.3.1 && apk add --no-cache openssl

ADD pump.py /pump/pump.py
ADD olt_ca.pem /pump/olt_ca.pem

WORKDIR /pump

CMD ["/usr/local/bin/python3", "/pump/pump.py"]