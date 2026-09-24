FROM node:22-slim

WORKDIR /app
COPY package.json package-lock.json* .
RUN npm install
COPY . .
# rewrites() is resolved at build time, so the proxy target has to be known here
ARG API_URL
ENV API_URL=$API_URL
RUN npm run build

CMD exec npm start -- -p ${PORT:-8080}
