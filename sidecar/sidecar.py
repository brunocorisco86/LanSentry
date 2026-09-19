#!/usr/bin/env python3
"""
LanSentry Sidecar
Sincroniza dispositivos marcados para bloqueio no PostgreSQL com o Pi-hole (gravity.db).
"""

import os
import sys
import time
import logging
import sqlite3
import psycopg2
from psycopg2.extras import DictCursor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("lansentry-sidecar")

PG_CONNECT = os.getenv("PG_CONNECT", "postgres://lansentry:lansentry_pass_mude_aqui@127.0.0.1:5432/lansentry?sslmode=disable")
PIHOLE_DB_PATH = os.getenv("PIHOLE_GRAVITY_DB", "/etc/pihole/gravity.db")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
BLOCK_GROUP_NAME = "LANSENTRY_BLOCKED"


def get_pg_connection():
    while True:
        try:
            conn = psycopg2.connect(PG_CONNECT)
            return conn
        except Exception as e:
            logger.warning(f"Aguardando PostgreSQL ficar pronto... ({e})")
            time.sleep(5)


def init_pihole_group():
    """Garante que o grupo de bloqueio e a regra wildcard existam no gravity.db do Pi-hole."""
    if not os.path.exists(PIHOLE_DB_PATH):
        logger.info(f"[DEV MODE] Arquivo {PIHOLE_DB_PATH} não encontrado. Operando em modo de simulação.")
        return False

    try:
        conn = sqlite3.connect(PIHOLE_DB_PATH)
        cursor = conn.cursor()

        # Verifica se o banco sqlite possui a estrutura do Pi-hole (tabela 'group')
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='group';")
        if not cursor.fetchone():
            logger.info(f"[DEV MODE] Tabela 'group' não encontrada em {PIHOLE_DB_PATH}. Operando em modo de simulação.")
            conn.close()
            return False

        # 1. Garante o grupo no Pi-hole
        cursor.execute("SELECT id FROM 'group' WHERE name = ?", (BLOCK_GROUP_NAME,))
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                "INSERT INTO 'group' (name, description, enabled) VALUES (?, ?, 1)",
                (BLOCK_GROUP_NAME, "Grupo de Dispositivos Bloqueados pelo LanSentry"),
            )
            group_id = cursor.lastrowid
            logger.info(f"Criado grupo no Pi-hole: '{BLOCK_GROUP_NAME}' (ID {group_id})")
        else:
            group_id = row[0]

        # 2. Garante a regra regex coringa '.*' associada ao grupo para barrar qualquer resolução DNS
        cursor.execute("SELECT id FROM domainlist WHERE type = 3 AND domain = '.*'")
        domain_row = cursor.fetchone()
        if not domain_row:
            cursor.execute(
                "INSERT INTO domainlist (type, domain, enabled, comment) VALUES (3, '.*', 1, 'LanSentry Total Block Regex')"
            )
            domain_id = cursor.lastrowid
            cursor.execute(
                "INSERT OR IGNORE INTO domainlist_by_group (domainlist_id, group_id) VALUES (?, ?)",
                (domain_id, group_id),
            )
            logger.info("Criada regra de bloqueio total (Regex '.*') no Pi-hole.")
        else:
            domain_id = domain_row[0]
            cursor.execute(
                "INSERT OR IGNORE INTO domainlist_by_group (domainlist_id, group_id) VALUES (?, ?)",
                (domain_id, group_id),
            )

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Erro ao inicializar grupo no Pi-hole: {e}")
        return False


def sync_blocks():
    """Lê os dispositivos do Postgres e sincroniza com o Pi-hole."""
    pg_conn = None
    try:
        pg_conn = get_pg_connection()
        with pg_conn.cursor(cursor_factory=DictCursor) as cur:
            # Localiza tabela do WatchYourLAN (nows ou now ou hosts)
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name IN ('nows', 'now', 'hosts');
            """)
            tables = [r[0] for r in cur.fetchall()]
            if not tables:
                logger.info("Nenhuma tabela do WatchYourLAN encontrada ainda no Postgres. Aguardando primeiro scan...")
                return

            table_name = tables[0]
            # Seleciona dispositivos com [BLOCK] no nome (colunas GORM em maiúsculo)
            cur.execute(f"""
                SELECT "MAC" AS mac, "IP" AS ip, "NAME" AS name 
                FROM "{table_name}"
                WHERE UPPER("NAME") LIKE '%BLOCK%' OR UPPER("NAME") LIKE '%[BLOCK]%';
            """)
            blocked_devices = cur.fetchall()

            if not os.path.exists(PIHOLE_DB_PATH):
                if blocked_devices:
                    logger.info(f"[DEV MODE] {len(blocked_devices)} dispositivo(s) marcados para bloqueio:")
                    for dev in blocked_devices:
                        logger.info(f" - MAC: {dev['mac']} | IP: {dev['ip']} | Nome: {dev['name']}")
                return

            # Sincronização real com gravity.db do Pi-hole
            pi_conn = sqlite3.connect(PIHOLE_DB_PATH)
            pi_cur = pi_conn.cursor()

            # Checa se a tabela group existe
            pi_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='group';")
            if not pi_cur.fetchone():
                if blocked_devices:
                    logger.info(f"[DEV MODE] {len(blocked_devices)} dispositivo(s) marcados para bloqueio (simulação):")
                    for dev in blocked_devices:
                        logger.info(f" - MAC: {dev['mac']} | IP: {dev['ip']} | Nome: {dev['name']}")
                pi_conn.close()
                return

            # Pega ID do grupo de bloqueio
            pi_cur.execute("SELECT id FROM 'group' WHERE name = ?", (BLOCK_GROUP_NAME,))
            g_row = pi_cur.fetchone()
            if not g_row:
                pi_conn.close()
                return
            group_id = g_row[0]

            blocked_macs = [dev['mac'].lower().strip() for dev in blocked_devices]

            # Aplica bloqueio para cada MAC encontrado
            for dev in blocked_devices:
                mac = dev['mac'].lower().strip()
                name = dev['name']

                # Verifica se cliente já existe no Pi-hole
                pi_cur.execute("SELECT id FROM client WHERE LOWER(ip) = ?", (mac,))
                c_row = pi_cur.fetchone()
                if not c_row:
                    pi_cur.execute(
                        "INSERT INTO client (ip, comment) VALUES (?, ?)",
                        (mac, f"LanSentry: {name}"),
                    )
                    client_id = pi_cur.lastrowid
                    logger.info(f"🚫 Adicionando cliente no Pi-hole: MAC {mac} ({name})")
                else:
                    client_id = c_row[0]

                # Vincula cliente ao grupo de bloqueio
                pi_cur.execute(
                    "INSERT OR IGNORE INTO client_by_group (client_id, group_id) VALUES (?, ?)",
                    (client_id, group_id),
                )

            pi_conn.commit()
            pi_conn.close()

    except Exception as e:
        logger.error(f"Erro durante sincronização: {e}")
    finally:
        if pg_conn:
            pg_conn.close()


def main():
    logger.info("Iniciando LanSentry Sidecar...")
    logger.info(f"Intervalo de checagem: {CHECK_INTERVAL}s")
    init_pihole_group()

    while True:
        try:
            sync_blocks()
        except Exception as e:
            logger.error(f"Exceção não tratada no loop: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
