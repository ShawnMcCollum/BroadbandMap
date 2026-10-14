# Development image for the React web app.
FROM node:22-bookworm-slim

RUN corepack enable

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN CI=true pnpm install --frozen-lockfile

COPY . .

EXPOSE 5173
CMD ["pnpm", "dev"]
