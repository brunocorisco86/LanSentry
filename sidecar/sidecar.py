#!/usr/bin/env python3
"""
LanSentry Sidecar & Auto-Enricher
- Sincroniza dispositivos marcados para bloqueio com o Pi-hole (gravity.db).
- Envia notificações ntfy (bruno-casa-dallas).
- Enriquece automaticamente fabricantes desconhecidos via api.macvendors.com.
- Gera nomes inteligentes para dispositivos sem identificação consultando DNS (Unbound/Pi-hole).
"""

import os
import sys
import time
import logging
import sqlite3
import requests
import psycopg2
from psycopg2.extras import DictCursor

try:
    import dns.resolver
    import dns.reversename
    DNS_MODULE_AVAILABLE = True
except ImportError:
    DNS_MODULE_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("lansentry-sidecar")

PG_CONNECT = os.getenv("PG_CONNECT", "postgres://lansentry:lansentry_pass_mude_aqui@127.0.0.1:5432/lansentry?sslmode=disable")
PIHOLE_DB_PATH = os.getenv("PIHOLE_GRAVITY_DB", "/etc/pihole/gravity.db")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "30"))
BLOCK_GROUP_NAME = "LANSENTRY_BLOCKED"
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "bruno-casa-dallas")
DNS_SERVER = os.getenv("DNS_SERVER", "192.168.1.7")

# Cache em memória para evitar requisições repetidas de MAC
MAC_VENDOR_CACHE = {}


def send_ntfy_message(text, title="LanSentry 🛡️", priority="3", tags="shield"):
    """Envia notificação via ntfy.sh seguindo padrão do homelab."""
    if not NTFY_TOPIC:
        return
    try:
        clean_text = text.replace("*", "").replace("`", "")
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=clean_text.encode("utf-8"),
            headers={"Title": title, "Priority": str(priority), "Tags": tags},
            timeout=3.0,
        )
    except Exception as e:
        logger.warning(f"Aviso ntfy: {e}")


def get_pg_connection():
    while True:
        try:
            conn = psycopg2.connect(PG_CONNECT)
            return conn
        except Exception as e:
            logger.warning(f"Aguardando PostgreSQL ficar pronto... ({e})")
            time.sleep(5)


def lookup_mac_vendor_api(mac):
    """Consulta api.macvendors.com para fabricantes desconhecidos com cache e rate-limit."""
    if not mac:
        return ""
    mac_clean = mac.strip().upper()
    prefix = ":".join(mac_clean.split(":")[:3])
    if prefix in MAC_VENDOR_CACHE:
        return MAC_VENDOR_CACHE[prefix]

    try:
        logger.info(f"🔍 Consultando API macvendors para MAC: {mac_clean}...")
        url = f"https://api.macvendors.com/{mac_clean}"
        resp = requests.get(url, timeout=4.0)
        # Respeita o rate-limit da API gratuita (1 req/s)
        time.sleep(1.2)
        if resp.status_code == 200:
            vendor = resp.text.strip()
            MAC_VENDOR_CACHE[prefix] = vendor
            logger.info(f"✅ Fabricante encontrado na API: {vendor}")
            return vendor
        elif resp.status_code == 404:
            MAC_VENDOR_CACHE[prefix] = "(Desconhecido)"
            return "(Desconhecido)"
    except Exception as e:
        logger.warning(f"Falha ao consultar API para MAC {mac_clean}: {e}")

    return ""


def lookup_reverse_dns(ip):
    """Consulta PTR no servidor DNS (Unbound/Pi-hole)."""
    if not DNS_MODULE_AVAILABLE or not ip or ip == "127.0.0.1":
        return ""
    try:
        resolver = dns.resolver.Resolver()
        resolver.nameservers = [DNS_SERVER]
        resolver.lifetime = 1.5
        rev_name = dns.reversename.from_address(ip)
        answers = resolver.resolve(rev_name, "PTR")
        for rdata in answers:
            hostname = str(rdata).rstrip(".")
            return hostname
    except Exception:
        pass
    return ""


def suggest_device_name(dns_name, vendor, ip):
    """Gera sugestão inteligente de nome baseada em DNS e Fabricante."""
    v_low = (vendor or "").lower()

    if dns_name:
        clean_dns = dns_name.split(".")[0].capitalize()
        if "raspberry" in v_low:
            return f"{clean_dns} (Raspberry Pi)"
        return clean_dns

    if "tuya" in v_low:
        return f"Tuya Smart Device ({ip.split('.')[-1]})"
    if "midea" in v_low:
        return "Midea Ar-Condicionado"
    if "motorola" in v_low:
        return "Motorola Mobile"
    if "apple" in v_low:
        return "Dispositivo Apple"
    if "samsung" in v_low:
        return "Dispositivo Samsung"
    if "espressif" in v_low:
        return f"Espressif IoT ({ip.split('.')[-1]})"
    if "amazon" in v_low:
        return "Amazon Echo / Alexa"
    if any(k in v_low for k in ["cisco", "tp-link", "tplink", "mikrotik", "intelbras", "ubiquiti"]):
        return f"Rede: {vendor.split()[0]}"
    if "realtek" in v_low:
        return f"PC LAN ({ip.split('.')[-1]})"
    if vendor and vendor != "(Unknown)" and vendor != "(Desconhecido)":
        return f"{vendor.split(',')[0]} ({ip.split('.')[-1]})"

    return f"Aparelho ({ip})"


def enrich_devices():
    """Percorre aparelhos no PostgreSQL e preenche HW e Name faltantes."""
    pg_conn = None
    try:
        pg_conn = get_pg_connection()
        with pg_conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
                SELECT "ID", "IP", "MAC", "HW", "NAME", "DNS"
                FROM "now"
                WHERE "NAME" IS NULL OR "NAME" = '' 
                   OR "HW" = '(Unknown)' OR "HW" IS NULL OR "HW" = '';
            """)
            devices_to_enrich = cur.fetchall()

            if not devices_to_enrich:
                return

            logger.info(f"✨ Encontrados {len(devices_to_enrich)} dispositivos para enriquecimento automático...")

            for dev in devices_to_enrich:
                dev_id = dev["ID"]
                ip = dev["IP"]
                mac = dev["MAC"]
                hw = dev["HW"]
                name = dev["NAME"]
                dns_name = dev["DNS"]

                updated = False

                # 1. Se HW for Unknown, tenta resolver via API
                if not hw or hw == "(Unknown)":
                    new_hw = lookup_mac_vendor_api(mac)
                    if new_hw and new_hw != "(Desconhecido)":
                        hw = new_hw
                        updated = True

                # 2. Se DNS for vazio, tenta consulta reversa no Unbound/Pi-hole
                if not dns_name:
                    rev_dns = lookup_reverse_dns(ip)
                    if rev_dns:
                        dns_name = rev_dns
                        updated = True

                # 3. Se NAME estiver vazio, gera nome inteligente
                if not name or name.strip() == "":
                    name = suggest_device_name(dns_name, hw, ip)
                    updated = True

                if updated:
                    cur.execute(
                        """
                        UPDATE "now"
                        SET "NAME" = %s, "HW" = %s, "DNS" = %s
                        WHERE "ID" = %s;
                        """,
                        (name, hw, dns_name, dev_id),
                    )
                    pg_conn.commit()
                    logger.info(f"🏷️  Auto-Enriquecido: IP {ip} -> Nome: '{name}' | Fabricante: '{hw}'")

    except Exception as e:
        logger.error(f"Erro durante enriquecimento: {e}")
    finally:
        if pg_conn:
            pg_conn.close()


def init_pihole_group():
    """Garante que o grupo de bloqueio e a regra wildcard existam no gravity.db do Pi-hole."""
    if not os.path.exists(PIHOLE_DB_PATH):
        logger.info(f"[DEV MODE] Arquivo {PIHOLE_DB_PATH} não encontrado. Operando em modo de simulação.")
        return False

    try:
        conn = sqlite3.connect(PIHOLE_DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='group';")
        if not cursor.fetchone():
            logger.info(f"[DEV MODE] Tabela 'group' não encontrada em {PIHOLE_DB_PATH}. Operando em modo de simulação.")
            conn.close()
            return False

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
    """Lê os dispositivos do Postgres e sincroniza bloqueios deliberados com o Pi-hole."""
    pg_conn = None
    try:
        pg_conn = get_pg_connection()
        with pg_conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name IN ('nows', 'now', 'hosts');
            """)
            tables = [r[0] for r in cur.fetchall()]
            if not tables:
                return

            table_name = tables[0]
            cur.execute(f"""
                SELECT "MAC" AS mac, "IP" AS ip, "NAME" AS name 
                FROM "{table_name}"
                WHERE UPPER("NAME") LIKE '%BLOCK%' OR UPPER("NAME") LIKE '%[BLOCK]%';
            """)
            blocked_devices = cur.fetchall()

            if not os.path.exists(PIHOLE_DB_PATH):
                if blocked_devices:
                    logger.info(f"[DEV MODE] {len(blocked_devices)} dispositivo(s) marcados com [BLOCK] (simulação):")
                    for dev in blocked_devices:
                        logger.info(f" - MAC: {dev['mac']} | IP: {dev['ip']} | Nome: {dev['name']}")
                return

            try:
                pi_conn = sqlite3.connect(PIHOLE_DB_PATH)
                pi_cur = pi_conn.cursor()

                pi_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='group';")
                if not pi_cur.fetchone():
                    if blocked_devices:
                        logger.info(f"[DEV MODE] {len(blocked_devices)} dispositivo(s) marcados com [BLOCK] (simulação):")
                        for dev in blocked_devices:
                            logger.info(f" - MAC: {dev['mac']} | IP: {dev['ip']} | Nome: {dev['name']}")
                    pi_conn.close()
                    return
            except sqlite3.Error as e:
                if blocked_devices:
                    logger.info(f"[DEV MODE] {len(blocked_devices)} dispositivo(s) marcados com [BLOCK] (simulação):")
                    for dev in blocked_devices:
                        logger.info(f" - MAC: {dev['mac']} | IP: {dev['ip']} | Nome: {dev['name']}")
                return

            pi_cur.execute("SELECT id FROM 'group' WHERE name = ?", (BLOCK_GROUP_NAME,))
            g_row = pi_cur.fetchone()
            if not g_row:
                pi_conn.close()
                return
            group_id = g_row[0]

            for dev in blocked_devices:
                mac = dev['mac'].lower().strip()
                name = dev['name']

                pi_cur.execute("SELECT id FROM client WHERE LOWER(ip) = ?", (mac,))
                c_row = pi_cur.fetchone()
                if not c_row:
                    pi_cur.execute(
                        "INSERT INTO client (ip, comment) VALUES (?, ?)",
                        (mac, f"LanSentry: {name}"),
                    )
                    client_id = pi_cur.lastrowid
                    logger.info(f"🚫 Adicionando cliente no Pi-hole: MAC {mac} ({name})")
                    send_ntfy_message(
                        f"Aparelho isolado da rede:\nNome: {name}\nIP: {dev['ip']}\nMAC: {mac}",
                        title="LanSentry: Acesso Revogado 🚫",
                        priority="4",
                        tags="no_entry,shield",
                    )
                else:
                    client_id = c_row[0]

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
    logger.info("Iniciando LanSentry Sidecar & Auto-Enricher...")
    logger.info(f"Filtro DNS Server: {DNS_SERVER}")
    logger.info(f"Tópico ntfy: {NTFY_TOPIC}")
    logger.info(f"Intervalo de checagem: {CHECK_INTERVAL}s")
    init_pihole_group()

    while True:
        try:
            enrich_devices()
            sync_blocks()
        except Exception as e:
            logger.error(f"Exceção não tratada no loop: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
