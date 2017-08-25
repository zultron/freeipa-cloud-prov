FROM debian:jessie

RUN apt-get update && \
    apt-get install dnsmasq dnsmasq-utils --no-install-recommends -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

EXPOSE 53/tcp 53/udp

VOLUME ["/etc/dnsmasq"]

CMD ["dnsmasq"]
