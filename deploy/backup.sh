#!/bin/sh
# SQLite -> S3 backup. Installed by the deploy job as /usr/local/bin/disha-backup, run nightly from
# /etc/cron.d/disha-backup and once before every deploy. Usage: disha-backup <bucket>
# Uploads with the EC2 instance role (no keys on the box); the bucket's lifecycle rule expires old copies.
set -eu
BUCKET=$1
c=$(docker ps -qf label=com.docker.compose.service=backend)
[ -n "$c" ] || { echo "backend container not running, nothing to back up"; exit 0; }
docker exec "$c" test -f /data/disha.db || { echo "no /data/disha.db (DATABASE_URL points elsewhere?), skipping"; exit 0; }

# SQLite's online backup API: a consistent copy even while the app is writing (a plain cp can tear)
docker exec "$c" python -c "import sqlite3; d = sqlite3.connect('/data/backup.db'); sqlite3.connect('/data/disha.db').backup(d); d.close()"
tmp=$(mktemp -d)
docker cp "$c":/data/backup.db "$tmp/disha.db"
docker exec "$c" rm -f /data/backup.db
gzip "$tmp/disha.db"
key="disha-$(date -u +%Y-%m-%dT%H%M%SZ).db.gz"
docker run --rm -e AWS_DEFAULT_REGION=ap-south-1 -v "$tmp":/b:ro amazon/aws-cli \
  s3 cp "/b/disha.db.gz" "s3://$BUCKET/$key" --only-show-errors
rm -rf "$tmp"
echo "backed up to s3://$BUCKET/$key"
