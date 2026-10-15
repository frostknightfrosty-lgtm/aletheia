#!/usr/bin/env bash
set -euo pipefail

docker build -t aletheia/sherlock:0.16.2 docker/sherlock
docker build -t aletheia/theharvester:4.11.1 docker/theharvester
docker build -t aletheia/exiftool:13.59 docker/exiftool
docker build -t aletheia/amass:5.1.1 docker/amass
docker build -t aletheia/subfinder:2.17.0 docker/subfinder
docker build -t aletheia/assetfinder:0.1.1 docker/assetfinder
docker build -t aletheia/dnsx:1.3.1 docker/dnsx
docker build -t aletheia/massdns:1.1.0 docker/massdns
docker build -t aletheia/dnsrecon:1.6.3 docker/dnsrecon
docker build -t aletheia/fierce:1.6.0 docker/fierce
docker build -t aletheia/shodan:1.31.0 docker/shodan
docker build -t aletheia/crtsh:public-json docker/crtsh

docker build -t aletheia/maigret:0.6.6 docker/maigret
docker build -t aletheia/holehe:1.61 docker/holehe
docker build -t aletheia/h8mail:2.5.6 docker/h8mail
docker build -t aletheia/hibp:api-v3 docker/hibp
docker build -t aletheia/xposedornot:api-v1 docker/xposedornot
docker build -t aletheia/phoneinfoga:2.11.0 docker/phoneinfoga
docker build -t aletheia/libphonenumber:9.0.40 docker/libphonenumber
docker build -t aletheia/instaloader:4.15.3 docker/instaloader
docker build -t aletheia/reddit-api:v1 docker/reddit-api
docker build -t aletheia/youtube-api:v3 docker/youtube-api
docker build -t aletheia/overpass:public docker/overpass
docker build -t aletheia/suncalc:2.0.2 docker/suncalc
docker build -t aletheia/deepface:0.0.101 docker/deepface
docker build -t aletheia/insightface:2.1 docker/insightface
docker build -f docker/core.Dockerfile -t aletheia/core:0.7.0 .
docker build -f docker/sec-edgar/Dockerfile -t aletheia/sec-edgar:public-api docker/sec-edgar
docker build -f docker/gleif/Dockerfile -t aletheia/gleif:api-v1 docker/gleif
docker build -f docker/opencorporates/Dockerfile -t aletheia/opencorporates:api-v0.4.8 docker/opencorporates
docker build -f docker/opensanctions/Dockerfile -t aletheia/opensanctions:api docker/opensanctions
docker build -f docker/courtlistener/Dockerfile -t aletheia/courtlistener:api-v3 docker/courtlistener
docker build -f docker/gravatar/Dockerfile -t aletheia/gravatar:api-v3 docker/gravatar
docker build -f docker/rdap/Dockerfile -t aletheia/rdap:rfc9082 docker/rdap
docker build -f docker/ip_intelligence/Dockerfile -t aletheia/ip-intelligence:v1 docker/ip_intelligence
docker build -f docker/government_records_us/Dockerfile -t aletheia/gov-records-us:v1 docker/government_records_us
docker build -f docker/corporate_registry/Dockerfile -t aletheia/corp-registry:v1 docker/corporate_registry
docker build -f docker/sanctions_enforcement_watchlists/Dockerfile -t aletheia/sanctions-watchlists:v1 docker/sanctions_enforcement_watchlists
docker build -f docker/academic_search/Dockerfile -t aletheia/academic-search:v1 docker/academic_search
docker build -f docker/ssl_tls/Dockerfile -t aletheia/ssl-tls:v1 docker/ssl_tls
docker build -f docker/crypto_blockchain/Dockerfile -t aletheia/crypto-blockchain:v1 docker/crypto_blockchain
docker build -f docker/patents_trademarks/Dockerfile -t aletheia/patents-trademarks:v1 docker/patents_trademarks
docker build -f docker/email_auth/Dockerfile -t aletheia/email-auth:v1 docker/email_auth
