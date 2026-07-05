FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ENV DB_PATH=/app/data/database.sqlite
EXPOSE 3000
CMD ["node", "server.js"]
