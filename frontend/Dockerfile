FROM node:22-slim

WORKDIR /app
COPY package.json package-lock.json* .
RUN npm install
COPY . .
RUN npm run build

CMD exec npm start -- -p ${PORT:-8080}
