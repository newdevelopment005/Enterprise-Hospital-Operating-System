# EHOS backup/restore tool image (postgres client + mc + curl).
#   docker build -t ehos/backup -f infrastructure/backup/Dockerfile .
FROM alpine:3.20
RUN apk add --no-cache postgresql16-client mc curl coreutils
WORKDIR /ops
COPY backup.sh restore.sh ./
RUN chmod +x backup.sh restore.sh
CMD ["/bin/sh"]