---
name: lansentry
description: Guia completo de operação, arquitetura, automação e integração do LanSentry com Pi-hole v6, Unbound, PostgreSQL e ntfy. Use esta skill para consultar o catálogo de ativos de rede, gerenciar bloqueios deliberados, sincronizar grupos no Pi-hole, inspecionar o grafo de conhecimento (graphify) ou executar tarefas de manutenção no Raspberry Pi.
---

# LanSentry Skill & Operational Manual

O **LanSentry** é um catálogo inteligente de ativos de rede local (LAN Layer 2), sistema de alerta push e orquestrador de segurança com integração nativa ao **Pi-hole v6** e **Unbound**.

---

## 🏗️ 1. Arquitetura do Sistema

```
[ Rede Física LAN / ARP (eth0) ]
              │
              ▼
   [ aceberg/watchyourlan:v2 ] (Porta Interna 8841)
              │
              ▼
    [ PostgreSQL 15 ] (postgres_db em 127.0.0.1:5432/lansentry)
              │
              ▼
    [ LanSentry Sidecar & Proxy ] (Porta 8840)
       ├── Injeta custom.js no Frontend (Toggles & Seletor de Grupos)
       ├── Auto-Enricher: OUI + api.macvendors.com + DNS PTR Unbound
       ├── Sincronizador Bidirecional Pi-hole (gravity.db & pihole-FTL.db)
       └── Notificador Push: ntfy (bruno-casa-dallas) com link direto
```

---

## 🌐 2. Acesso e Endpoints

- **Dashboard Web:** `http://192.168.1.7:8840`
- **Página de Detalhes do Dispositivo:** `http://192.168.1.7:8840/#/host/<ID>`
- **API Grupos e Clientes Pi-hole:** `GET http://192.168.1.7:8840/api/pihole/info`
- **API Alteração de Grupo:** `POST http://192.168.1.7:8840/api/pihole/set_group/<ID>/<GROUP_ID>`
- **API Toggle de Bloqueio:** `POST http://192.168.1.7:8840/api/block_toggle/<ID>/<1|0>`

---

## 🔒 3. Integração com Pi-hole v6

1. **Grupos Suportados no Pi-hole:**
   - `0`: Default (Regras padrão)
   - `1`: Infraestrutura (Roteadores, switches, APs)
   - `2`: IoT & Smart Home (Sensores, ESP32, Tuya, Ar-Condicionado)
   - `3`: Assistentes & Streaming (Alexa, Roku, Chromecast, Apple TV)
   - `4`: Dispositivos Móveis (Smartphones, Tablets)
   - `5`: Workstations & PCs (Computadores, notebooks)
   - `6`: Kids & Família (Controle parental / SafeSearch)
   - `7`: LANSENTRY_BLOCKED (Corte total de DNS via regex `.*`)

2. **Auto-Classificação de Novos Aparelhos:**
   - O Sidecar detecta aparelhos sem grupo customizado e classifica automaticamente baseado nas palavras-chave de fabricante (`HW`) e nome (`NAME`).

3. **Sincronização de Nomes Amigáveis no Pi-hole Query Log:**
   - O Sidecar sincroniza periodicamente os nomes enriquecidos do LanSentry para `network_addresses.name` no `/etc/pihole/pihole-FTL.db`.

---

## 💾 4. Backups e Manutenção no Raspberry Pi

- **Diretório do Projeto no Alpine:** `/mnt/pendrive_cinza/14_LanSentry/` (atalho em `~/14_LanSentry`)
- **Script de Backup:** `/mnt/pendrive_cinza/14_LanSentry/scripts/backup_lansentry.sh`
- **Agendamento Cron:** Diariamente às `03:45 AM`
- **Destino dos Dumps:** `/mnt/pendrive_cinza/backup/lansentry/` (retenção de 14 dias)

Comandos rápidos via SSH:
```bash
# Verificar status dos containers
ssh alpine "docker ps --filter 'name=lansentry'"

# Ver logs do scanner
ssh alpine "docker compose -f ~/14_LanSentry/docker-compose.prod.yml logs --tail=50 lansentry-wyl"

# Ver logs do sidecar e auto-enricher
ssh alpine "docker compose -f ~/14_LanSentry/docker-compose.prod.yml logs --tail=50 lansentry-sidecar"

# Executar backup manual
ssh alpine "/mnt/pendrive_cinza/14_LanSentry/scripts/backup_lansentry.sh"
```

---

## 🧠 5. Grafo de Conhecimento (Graphify)

O projeto possui um grafo de conhecimento indexado pelo `graphifyy`:
- Visualização interativa: `graphify-out/graph.html`
- Relatório de arquitetura: `graphify-out/GRAPH_REPORT.md`
- Atualização do grafo após mudanças de código:
  ```bash
  python3 -m graphify /home/bruno/Documentos/4_HOMELAB/14_LanSentry --code-only
  python3 -m graphify cluster-only /home/bruno/Documentos/4_HOMELAB/14_LanSentry
  ```
