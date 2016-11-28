FROM cfssl/cfssl
MAINTAINER John Morris <john@zultron.com>

# Docker image with cfssl and scripts for initializing coreos cluster
# communicating over SSL

RUN apt-get update
RUN apt-get install -y \
        python-yaml \
	python-pip \
	python-dev \
        libffi-dev \
	libssl-dev \
	build-essential \
        python-setuptools \
        python-pkg-resources
RUN pip install python-digitalocean
RUN pip install --upgrade \
        cffi
RUN pip install paramiko
RUN pip install Jinja2
# https://pypi.python.org/pypi/ipcalc/
RUN pip install ipcalc

RUN useradd -s /bin/bash user

ENV PYTHONPATH=/data/python

VOLUME /data
WORKDIR /data

USER user

ENTRYPOINT ["./provision-helper.py"]
