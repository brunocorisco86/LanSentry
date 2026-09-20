#!/usr/bin/env python3
"""
LanSentry Sidecar, Proxy & Auto-Enricher
- Proxy transparente com injeção do Toggle de Bloqueio e Seletor de Grupos do Pi-hole.
- Sincroniza dispositivos marcados para bloqueio com o Pi-hole (gravity.db).
- Sincronização e controle bidirecional de grupos do Pi-hole (Default, IoT, Streaming, Mobile, PCs, Infra).
- Auto-Classificação de novos dispositivos no grupo correto do Pi-hole.
- Injeção de nomes amigáveis no Query Log do Pi-hole (network_addresses em pihole-FTL.db).
- Envia notificações ntfy com link direto para o ID do aparelho (bruno-casa-dallas).
- Enriquece automaticamente fabricantes desconhecidos via api.macvendors.com.
- Gera nomes inteligentes para dispositivos sem identificação consultando DNS (Unbound/Pi-hole).
"""

import os
import sys
import time
import json
import logging
import sqlite3
import threading
import urllib.parse
import subprocess
import requests
import psycopg2
from psycopg2.extras import DictCursor
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

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

PG_CONNECT = os.getenv("PG_CONNECT", "postgres://lansentry:lansentry_pass_mude_aqui@127.0.0.1:5434/lansentry?sslmode=disable")
PIHOLE_DB_PATH = os.getenv("PIHOLE_GRAVITY_DB", "/etc/pihole/gravity.db")
PIHOLE_FTL_PATH = os.getenv("PIHOLE_FTL_DB", "/etc/pihole/pihole-FTL.db")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "30"))
BLOCK_GROUP_NAME = "LANSENTRY_BLOCKED"
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "bruno-casa-dallas")
DNS_SERVER = os.getenv("DNS_SERVER", "192.168.1.7")
SERVER_HOST = os.getenv("SERVER_HOST", "192.168.1.7")

PROXY_PORT = int(os.getenv("PROXY_PORT", "8840"))
WYL_TARGET = os.getenv("WYL_TARGET", "http://127.0.0.1:8841")

MAC_VENDOR_CACHE = {}


def reload_pihole_lists():
    """Envia sinal RTMIN para o pihole-FTL recarregar as listas e grupos instantaneamente."""
    try:
        subprocess.run(
            ["sh", "-c", "kill -RTMIN $(cat /run/pihole-FTL_openrc.pid 2>/dev/null || pgrep -x pihole-FTL) 2>/dev/null || true"],
            timeout=2.0,
            check=False,
        )
    except Exception as e:
        logger.debug(f"Aviso reload pihole: {e}")


def send_ntfy_message(text, title="LanSentry 🛡️", priority="3", tags="shield", device_id=None):
    """Envia notificação via ntfy.sh com link direto por ID."""
    if not NTFY_TOPIC:
        return
    try:
        clean_text = text.replace("*", "").replace("`", "")
        clean_title = title.encode("ascii", "ignore").decode("ascii").strip()
        headers = {"Title": clean_title, "Priority": str(priority), "Tags": tags}

        if device_id:
            host_url = f"http://{SERVER_HOST}:8840/#/host/{device_id}"
            headers["Click"] = host_url
            headers["Actions"] = f"view, Editar no LanSentry, {host_url}"

        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=clean_text.encode("utf-8"),
            headers=headers,
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


def init_pihole_group():
    """Garante que o grupo de bloqueio e a regra wildcard existam no gravity.db do Pi-hole."""
    if not os.path.exists(PIHOLE_DB_PATH):
        return False

    try:
        conn = sqlite3.connect(PIHOLE_DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='group';")
        if not cursor.fetchone():
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

        # Remove do grupo 0 (Default) caso tenha sido associado pela trigger automática do Pi-hole
        cursor.execute(
            "DELETE FROM domainlist_by_group WHERE domainlist_id = ? AND group_id = 0",
            (domain_id,),
        )

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Erro ao inicializar grupo no Pi-hole: {e}")
        return False


def get_pihole_groups():
    """Retorna todos os grupos configurados no Pi-hole."""
    if not os.path.exists(PIHOLE_DB_PATH):
        return [
            {"id": 0, "name": "Default", "description": "Grupo Padrão", "enabled": 1},
            {"id": 1, "name": "Infraestrutura", "description": "Roteadores e Servidores", "enabled": 1},
            {"id": 2, "name": "IoT & Smart Home", "description": "Sensores e Automação", "enabled": 1},
            {"id": 3, "name": "Assistentes & Streaming", "description": "Alexa e Smart TVs", "enabled": 1},
            {"id": 4, "name": "Dispositivos Móveis", "description": "Smartphones e Tablets", "enabled": 1},
            {"id": 5, "name": "Workstations & PCs", "description": "Computadores e Notebooks", "enabled": 1},
            {"id": 6, "name": "Kids & Família", "description": "Controle Parental", "enabled": 1},
        ]
    try:
        conn = sqlite3.connect(PIHOLE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, description, enabled FROM 'group' WHERE name != ? ORDER BY id;", (BLOCK_GROUP_NAME,))
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r[0], "name": r[1], "description": r[2] or "", "enabled": r[3]} for r in rows]
    except Exception as e:
        logger.error(f"Erro ao consultar grupos do Pi-hole: {e}")
        return []


def get_pihole_client_groups():
    """Retorna dicionário mapeando identificador (MAC ou IP em maiúsculas) para seus grupos no Pi-hole."""
    if not os.path.exists(PIHOLE_DB_PATH):
        return {}
    try:
        conn = sqlite3.connect(PIHOLE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT UPPER(c.ip) AS client_id, c.comment, g.id AS group_id, g.name AS group_name
            FROM client c
            JOIN client_by_group cbg ON c.id = cbg.client_id
            JOIN 'group' g ON cbg.group_id = g.id;
        """)
        rows = cursor.fetchall()
        conn.close()

        client_map = {}
        for row in rows:
            ident = row[0].strip().upper()
            comment = row[1] or ""
            g_id = row[2]
            g_name = row[3]

            if ident not in client_map:
                client_map[ident] = {
                    "primary_group_id": 0,
                    "primary_group_name": "Default",
                    "comment": comment,
                    "groups": [],
                    "is_blocked": False,
                }

            if g_name == BLOCK_GROUP_NAME:
                client_map[ident]["is_blocked"] = True
            else:
                client_map[ident]["groups"].append({"id": g_id, "name": g_name})
                client_map[ident]["primary_group_id"] = g_id
                client_map[ident]["primary_group_name"] = g_name

        return client_map
    except Exception as e:
        logger.error(f"Erro ao ler grupos de clientes do Pi-hole: {e}")
        return {}


def set_pihole_device_group(mac, group_id, ip=None, dev_name=None):
    """Define ou altera o grupo de um dispositivo no Pi-hole por MAC ou IP."""
    if not os.path.exists(PIHOLE_DB_PATH):
        logger.info(f"[DEV MODE] Atribuído grupo {group_id} para MAC {mac}")
        return True, None

    try:
        conn = sqlite3.connect(PIHOLE_DB_PATH)
        cursor = conn.cursor()

        mac_upper = mac.strip().upper() if mac else None
        ip_clean = ip.strip() if ip else None

        # Procura cliente pelo MAC ou pelo IP
        client_id = None
        if mac_upper:
            cursor.execute("SELECT id FROM client WHERE UPPER(ip) = ?", (mac_upper,))
            row = cursor.fetchone()
            if row:
                client_id = row[0]

        if not client_id and ip_clean:
            cursor.execute("SELECT id FROM client WHERE ip = ?", (ip_clean,))
            row = cursor.fetchone()
            if row:
                client_id = row[0]

        comment_text = f"{dev_name} [{ip_clean or mac_upper}]" if dev_name else f"LanSentry [{ip_clean or mac_upper}]"

        if not client_id:
            target_ident = mac_upper if mac_upper else ip_clean
            cursor.execute(
                "INSERT INTO client (ip, comment) VALUES (?, ?)",
                (target_ident, comment_text),
            )
            client_id = cursor.lastrowid
        else:
            if dev_name:
                cursor.execute("UPDATE client SET comment = ? WHERE id = ?", (comment_text, client_id))

        # Recupera o ID do grupo de bloqueio para não removê-lo se estiver bloqueado
        cursor.execute("SELECT id FROM 'group' WHERE name = ?", (BLOCK_GROUP_NAME,))
        b_row = cursor.fetchone()
        block_id = b_row[0] if b_row else -1

        # Remove grupos não-bloqueio atuais
        cursor.execute("DELETE FROM client_by_group WHERE client_id = ? AND group_id != ?", (client_id, block_id))

        # Adiciona o novo grupo selecionado
        cursor.execute(
            "INSERT OR IGNORE INTO client_by_group (client_id, group_id) VALUES (?, ?)",
            (client_id, int(group_id)),
        )

        conn.commit()
        conn.close()

        reload_pihole_lists()
        logger.info(f"🎯 Grupo Pi-hole atualizado: Cliente {mac_upper or ip_clean} -> Grupo ID {group_id}")
        return True, None
    except Exception as e:
        logger.error(f"Erro ao atualizar grupo no Pi-hole: {e}")
        return False, str(e)


def sync_names_to_pihole_ftl():
    """Sincroniza os nomes humanos enriquecidos do LanSentry para a tabela network_addresses do Pi-hole FTL."""
    if not os.path.exists(PIHOLE_FTL_PATH):
        return

    pg_conn = None
    try:
        pg_conn = get_pg_connection()
        with pg_conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('SELECT "IP", "NAME" FROM "now" WHERE "NAME" IS NOT NULL AND "NAME" != \'\';')
            devices = cur.fetchall()

        if not devices:
            return

        ftl_conn = sqlite3.connect(PIHOLE_FTL_PATH)
        ftl_cur = ftl_conn.cursor()

        updated_count = 0
        now_ts = int(time.time())

        for dev in devices:
            ip = dev["IP"]
            name = dev["NAME"].replace("[BLOCK]", "").strip()
            if not name:
                continue

            ftl_cur.execute(
                """
                UPDATE network_addresses 
                SET name = ?, nameUpdated = ?
                WHERE ip = ? AND (name IS NULL OR name = '' OR name LIKE '%.lan' OR name != ?);
                """,
                (name, now_ts, ip, name),
            )
            if ftl_cur.rowcount > 0:
                updated_count += 1

        ftl_conn.commit()
        ftl_conn.close()

        if updated_count > 0:
            logger.info(f"🕳️  {updated_count} nome(s) de dispositivos sincronizados para o Query Log do Pi-hole FTL!")

    except Exception as e:
        logger.debug(f"Aviso sync FTL: {e}")
    finally:
        if pg_conn:
            pg_conn.close()


def auto_classify_devices(pihole_client_map):
    """Classifica automaticamente dispositivos novos no grupo correto do Pi-hole com base no perfil."""
    pg_conn = None
    try:
        pg_conn = get_pg_connection()
        with pg_conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('SELECT "ID", "IP", "MAC", "HW", "NAME" FROM "now";')
            devices = cur.fetchall()

        if not devices:
            return

        for dev in devices:
            mac = (dev["MAC"] or "").strip().upper()
            ip = (dev["IP"] or "").strip()
            hw = (dev["HW"] or "").lower()
            name = (dev["NAME"] or "").lower()

            client_info = pihole_client_map.get(mac) or pihole_client_map.get(ip.upper())
            # Se já tem um grupo configurado (diferente de Default 0), respeita a escolha existente
            if client_info and client_info.get("primary_group_id", 0) != 0:
                continue

            target_group = None
            target_group_name = ""

            # Regras de Auto-Classificação
            if any(k in hw or k in name for k in ["tuya", "espressif", "midea", "sonoff", "bilian", "trolink", "altobeam", "esp32", "esp8266"]):
                target_group = 2
                target_group_name = "IoT & Smart Home"
            elif any(k in hw or k in name for k in ["amazon", "echo", "alexa", "roku", "chromecast", "smart tv", "apple tv", "fire tv"]):
                target_group = 3
                target_group_name = "Assistentes & Streaming"
            elif any(k in hw or k in name for k in ["motorola", "iphone", "ipad", "xiaomi", "samsung mobile", "galaxy"]):
                target_group = 4
                target_group_name = "Dispositivos Móveis"
            elif any(k in hw or k in name for k in ["realtek", "intel", "dell", "lenovo", "asus", "pc_", "workstation", "notebook", "desktop"]):
                target_group = 5
                target_group_name = "Workstations & PCs"
            elif any(k in hw or k in name for k in ["cisco", "tp-link", "tplink", "ubiquiti", "mikrotik", "intelbras", "router"]):
                target_group = 1
                target_group_name = "Infraestrutura"

            if target_group:
                dev_clean_name = dev["NAME"] or f"Aparelho ({ip})"
                success, _ = set_pihole_device_group(mac, target_group, ip, dev_clean_name)
                if success:
                    logger.info(f"✨ Auto-Classificado no Pi-hole: {dev_clean_name} -> Grupo '{target_group_name}'")
                    send_ntfy_message(
                        f"Novo dispositivo classificado automaticamente!\nAparelho: {dev_clean_name}\nIP: {ip}\nGrupo Pi-hole: {target_group_name}",
                        title="LanSentry: Perfil Pi-hole Definido 🏷️",
                        priority="3",
                        tags="sparkles,gear",
                        device_id=dev["ID"],
                    )

    except Exception as e:
        logger.error(f"Erro na auto-classificação de dispositivos: {e}")
    finally:
        if pg_conn:
            pg_conn.close()


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

                if not hw or hw == "(Unknown)":
                    new_hw = lookup_mac_vendor_api(mac)
                    if new_hw and new_hw != "(Desconhecido)":
                        hw = new_hw
                        updated = True

                if not dns_name:
                    rev_dns = lookup_reverse_dns(ip)
                    if rev_dns:
                        dns_name = rev_dns
                        updated = True

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
                SELECT "ID" AS id, "MAC" AS mac, "IP" AS ip, "NAME" AS name 
                FROM "{table_name}"
                WHERE UPPER("NAME") LIKE '%BLOCK%' OR UPPER("NAME") LIKE '%[BLOCK]%';
            """)
            blocked_devices = cur.fetchall()

            if not os.path.exists(PIHOLE_DB_PATH):
                return

            pi_conn = sqlite3.connect(PIHOLE_DB_PATH)
            pi_cur = pi_conn.cursor()

            pi_cur.execute("SELECT id FROM 'group' WHERE name = ?", (BLOCK_GROUP_NAME,))
            g_row = pi_cur.fetchone()
            if not g_row:
                pi_conn.close()
                return
            group_id = g_row[0]

            for dev in blocked_devices:
                mac = dev['mac'].upper().strip()
                name = dev['name']

                pi_cur.execute("SELECT id FROM client WHERE UPPER(ip) = ?", (mac,))
                c_row = pi_cur.fetchone()
                if not c_row:
                    pi_cur.execute(
                        "INSERT INTO client (ip, comment) VALUES (?, ?)",
                        (mac, f"LanSentry: {name}"),
                    )
                    client_id = pi_cur.lastrowid
                else:
                    client_id = c_row[0]

                pi_cur.execute(
                    "INSERT OR IGNORE INTO client_by_group (client_id, group_id) VALUES (?, ?)",
                    (client_id, group_id),
                )

            pi_conn.commit()
            pi_conn.close()
            reload_pihole_lists()

    except Exception as e:
        logger.error(f"Erro durante sincronização de bloqueios: {e}")
    finally:
        if pg_conn:
            pg_conn.close()


def handle_block_toggle(dev_id, will_block):
    """Atualiza o nome no banco com ou sem a tag [BLOCK], roda sync_blocks imediatamente e notifica."""
    pg_conn = None
    try:
        pg_conn = get_pg_connection()
        with pg_conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('SELECT "ID", "IP", "MAC", "NAME" FROM "now" WHERE "ID" = %s;', (dev_id,))
            dev = cur.fetchone()
            if not dev:
                return False, "Dispositivo não encontrado"

            current_name = dev["NAME"] or ""
            mac = dev["MAC"]
            ip = dev["IP"]

            if will_block:
                if "[BLOCK]" not in current_name:
                    new_name = f"[BLOCK] {current_name}".strip()
                else:
                    new_name = current_name
            else:
                new_name = current_name.replace("[BLOCK]", "").strip()

            cur.execute('UPDATE "now" SET "NAME" = %s WHERE "ID" = %s;', (new_name, dev_id))
            pg_conn.commit()

        # Remove do grupo de bloqueio do Pi-hole se foi liberado
        if not will_block and os.path.exists(PIHOLE_DB_PATH):
            try:
                p_conn = sqlite3.connect(PIHOLE_DB_PATH)
                p_cur = p_conn.cursor()
                p_cur.execute("SELECT id FROM 'group' WHERE name = ?", (BLOCK_GROUP_NAME,))
                bg_row = p_cur.fetchone()
                if bg_row:
                    block_gid = bg_row[0]
                    mac_upper = mac.strip().upper()
                    p_cur.execute("SELECT id FROM client WHERE UPPER(ip) = ?", (mac_upper,))
                    c_row = p_cur.fetchone()
                    if c_row:
                        p_cur.execute(
                            "DELETE FROM client_by_group WHERE client_id = ? AND group_id = ?",
                            (c_row[0], block_gid),
                        )
                        p_conn.commit()
                p_conn.close()
                reload_pihole_lists()
            except Exception as e:
                logger.error(f"Erro ao desvincular do grupo de bloqueio no Pi-hole: {e}")

        sync_blocks()

        if will_block:
            send_ntfy_message(
                f"Dispositivo bloqueado na rede!\nNome: {new_name}\nIP: {ip}\nMAC: {mac}",
                title="LanSentry: Acesso Revogado 🚫",
                priority="4",
                tags="no_entry,shield",
                device_id=dev_id,
            )
        else:
            send_ntfy_message(
                f"Dispositivo liberado para navegar:\nNome: {new_name}\nIP: {ip}\nMAC: {mac}",
                title="LanSentry: Acesso Restaurado ✅",
                priority="3",
                tags="white_check_mark,shield",
                device_id=dev_id,
            )

        return True, None
    except Exception as e:
        logger.error(f"Erro em handle_block_toggle: {e}")
        return False, str(e)
    finally:
        if pg_conn:
            pg_conn.close()


class LanSentryProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Silencia logs comuns de requisições web

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/custom.js":
            try:
                with open("/app/custom.js", "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                self.send_error(500, str(e))
                return

        # Endpoint que retorna os grupos disponíveis e o mapa de grupos de clientes
        if path == "/api/pihole/info":
            groups = get_pihole_groups()
            clients = get_pihole_client_groups()
            payload = json.dumps({"groups": groups, "clients": clients}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        target_url = f"{WYL_TARGET}{self.path}"
        try:
            resp = requests.get(target_url, timeout=10.0, headers={k: v for k, v in self.headers.items() if k.lower() != "host"})
            content_type = resp.headers.get("Content-Type", "")

            # Injeta custom.js em qualquer página HTML servida (seja /, /host/:id, /config, etc.)
            if "text/html" in content_type:
                html = resp.text
                if "/custom.js" not in html:
                    if "</body>" in html:
                        html = html.replace("</body>", '<script src="/custom.js" defer></script></body>')
                    elif "</head>" in html:
                        html = html.replace("</head>", '<script src="/custom.js" defer></script></head>')
                body_bytes = html.encode("utf-8")
                self.send_response(resp.status_code)
                for k, v in resp.headers.items():
                    if k.lower() not in ["content-encoding", "transfer-encoding", "content-length"]:
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(body_bytes)))
                self.end_headers()
                self.wfile.write(body_bytes)
                return

            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() not in ["content-encoding", "transfer-encoding", "content-length"]:
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(resp.content)))
            self.end_headers()
            self.wfile.write(resp.content)
        except Exception as e:
            self.send_error(502, f"Proxy error: {e}")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/block_toggle/"):
            parts = path.strip("/").split("/")
            if len(parts) >= 4:
                dev_id = parts[2]
                status = parts[3]
                success, err = handle_block_toggle(dev_id, status == "1")
                res_body = json.dumps({"success": success, "error": err}).encode("utf-8")
                self.send_response(200 if success else 400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(res_body)))
                self.end_headers()
                self.wfile.write(res_body)
                return

        if path.startswith("/api/pihole/set_group/"):
            parts = path.strip("/").split("/")
            if len(parts) >= 5:
                dev_id = parts[3]
                group_id = parts[4]

                # Busca detalhes do dispositivo no Postgres
                pg_conn = None
                try:
                    pg_conn = get_pg_connection()
                    with pg_conn.cursor(cursor_factory=DictCursor) as cur:
                        cur.execute('SELECT "MAC", "IP", "NAME" FROM "now" WHERE "ID" = %s;', (dev_id,))
                        dev = cur.fetchone()
                        if dev:
                            success, err = set_pihole_device_group(dev["MAC"], group_id, dev["IP"], dev["NAME"])
                        else:
                            success, err = False, "Dispositivo não encontrado"
                except Exception as e:
                    success, err = False, str(e)
                finally:
                    if pg_conn:
                        pg_conn.close()

                res_body = json.dumps({"success": success, "error": err}).encode("utf-8")
                self.send_response(200 if success else 400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(res_body)))
                self.end_headers()
                self.wfile.write(res_body)
                return

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else None
        target_url = f"{WYL_TARGET}{self.path}"
        try:
            resp = requests.post(target_url, data=post_data, timeout=10.0, headers={k: v for k, v in self.headers.items() if k.lower() != "host"})
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() not in ["content-encoding", "transfer-encoding", "content-length"]:
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(resp.content)))
            self.end_headers()
            self.wfile.write(resp.content)
        except Exception as e:
            self.send_error(502, f"Proxy error: {e}")


def run_proxy():
    server_address = ("0.0.0.0", PROXY_PORT)
    httpd = ThreadingHTTPServer(server_address, LanSentryProxyHandler)
    logger.info(f"🌐 LanSentry Web Proxy ativo em http://0.0.0.0:{PROXY_PORT} (repassando para {WYL_TARGET})")
    httpd.serve_forever()


def main():
    logger.info("Iniciando LanSentry Sidecar, Proxy & Auto-Enricher...")
    logger.info(f"Filtro DNS Server: {DNS_SERVER}")
    logger.info(f"Tópico ntfy: {NTFY_TOPIC}")
    logger.info(f"Host base ntfy links: {SERVER_HOST}")
    init_pihole_group()

    # Inicia proxy HTTP em thread separada
    proxy_t = threading.Thread(target=run_proxy, daemon=True)
    proxy_t.start()

    while True:
        try:
            enrich_devices()
            sync_blocks()
            sync_names_to_pihole_ftl()

            # Executa auto-classificação de novos dispositivos
            client_groups = get_pihole_client_groups()
            auto_classify_devices(client_groups)

        except Exception as e:
            logger.error(f"Exceção não tratada no loop: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
