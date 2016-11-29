#!/bin/bash -ex

# docker pull zultron/docker-freeipa:centos-7-client

. /media/state/system.env

# https://linux.die.net/man/1/ipa-client-install

IPA_CLIENT_INSTALL_OPTS="-N --force-join --force --server=${SERVER_IP_ipa} --fixed-primary --domain=zultron.com"

docker run -it --privileged \
    -e IPA_PORT_53_UDP_ADDR=${SERVER_IP_ipa} \
    -e PASSWORD=${ADMIN_PASSWORD} \
    -e IPA_PORT_80_TCP_ADDR=${SERVER_IP_ipa} \
    -e IPA_CLIENT_INSTALL_OPTS \
    -h ${HOST_NAME} \
    --net ${NETWORK_NAME} --ip ${IPA_CLIENT_IP} \
    zultron/docker-freeipa:centos-7-client
#    --entrypoint /bin/bash \
