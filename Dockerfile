FROM debian:jessie
MAINTAINER John Morris <john@zultron.com>

# Docker image with ansible and scripts for initializing coreos cluster
# communicating over SSL

RUN apt-get update
RUN apt-get install -y \
        python-yaml \
        libyaml-dev \
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
RUN pip install ansible
# dopy > 0.3.5 broken, according to DO Ansible tutorial
RUN pip install 'dopy>=0.3.5,<=0.3.5'
RUN apt-get install -y \
    openssh-client

RUN apt-get install -y \
    redis-server
RUN pip install redis

# Install and configure sudo, passwordless for everyone
RUN apt-get -y install sudo
RUN echo "ALL	ALL=(ALL:ALL) NOPASSWD: ALL" >> /etc/sudoers

RUN apt-get -y install ed

RUN apt-get -y install libldap2-dev libsasl2-dev
RUN pip install python-ldap

RUN apt-get -y install dnsutils

# For manual IPA ds query
RUN apt-get -y install ldap-utils

RUN useradd -s /bin/bash user

RUN apt-get -y install git

# Install author's fave editor
RUN apt-get -y install emacs-common


COPY lib/requirements.yaml /tmp
RUN ansible-galaxy install -r /tmp/requirements.yaml

ENV PYTHONPATH=/data/lib/python

# Work around annoying python location on CoreOS
RUN mkdir -p /home/core/bin && ln -s /usr/bin/python /home/core/bin/python

VOLUME /data
WORKDIR /data

USER user
