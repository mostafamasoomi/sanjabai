FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
# npm install with --maxsockets 1 avoids the "Exit handler never called!"
# crash that happens intermittently inside Docker builds on this host.
RUN npm install --no-audit --no-fund --legacy-peer-deps --maxsockets 1
ARG NEXT_PUBLIC_API_URL=http://127.0.0.1:8081
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
ENV NODE_ENV=production
USER node
CMD ["node", "server.js"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["node", "-e", "fetch('http://localhost:3000').then(r=>{process.exit(r.ok?0:1)}).catch(()=>process.exit(1))"]
