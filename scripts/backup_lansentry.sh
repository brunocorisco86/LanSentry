#!/bin/bash
# ==========================================================
# LanSentry - Script de Backup Automatizado no Pendrive
# Executa pg_dump comprimido e snapshot do Pi-hole gravity.db
# ==========================================================

set -euo pipefail

DEST_DIR="/mnt/pendrive_cinza/backup/lansentry"
DATE_STAMP=$(date +'%Y-%m-%d_%H%M')
PG_CONTAINER="postgres_db"
PG_USER="lansentry"
PG_DB="lansentry"
GRAVITY_PATH="/etc/pihole/gravity.db"

# 1. Verifica se o pendrive está montado
if ! mountpoint -q /mnt/pendrive_cinza; then
    echo "[ERRO] Pendrive cinza não está montado em /mnt/pendrive_cinza!" >&2
    exit 1
fi

mkdir -p "$DEST_DIR"
echo "[$(date +'%Y-%m-%d %H:%M:%S')] Iniciando backup do LanSentry..."

# 2. Dump do PostgreSQL comprimido
DUMP_FILE="$DEST_DIR/lansentry_pgdump_${DATE_STAMP}.sql.gz"
if docker ps --format '{{.Names}}' | grep -q "^${PG_CONTAINER}$"; then
    docker exec "$PG_CONTAINER" pg_dump -U "$PG_USER" "$PG_DB" | gzip > "$DUMP_FILE"
    echo "  [✓] PostgreSQL dump salvo: $DUMP_FILE ($(du -h "$DUMP_FILE" | cut -f1))"
else
    echo "  [AVISO] Container $PG_CONTAINER não encontrado em execução!" >&2
fi

# 3. Snapshot do Pi-hole gravity.db
if [ -f "$GRAVITY_PATH" ]; then
    GRAVITY_BACKUP="$DEST_DIR/pihole_gravity_${DATE_STAMP}.db"
    cp "$GRAVITY_PATH" "$GRAVITY_BACKUP"
    echo "  [✓] Pi-hole gravity snapshot salvo: $GRAVITY_BACKUP ($(du -h "$GRAVITY_BACKUP" | cut -f1))"
fi

# 4. Rotação de backups antigos (mantém os últimos 14 dias)
echo "  [i] Removendo backups com mais de 14 dias..."
find "$DEST_DIR" -type f \( -name "lansentry_pgdump_*.sql.gz" -o -name "pihole_gravity_*.db" \) -mtime +14 -delete

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Backup concluído com sucesso!"
