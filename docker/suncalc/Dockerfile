FROM node:22-alpine
WORKDIR /opt
RUN npm install --no-audit --no-fund suncalc@2.0.2
COPY runner.js /opt/runner.js
ENTRYPOINT ["node", "/opt/runner.js"]
