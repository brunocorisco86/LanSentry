# 🛡️ 14_LanSentry

Catálogo inteligente de dispositivos conectados na LAN, monitoramento de presença/uptime, resolução de fabricantes por MAC Address e bloqueio automatizado no **Pi-hole + Unbound**, com persistência em **PostgreSQL** e execução em containers minimalistas **Alpine Linux**.

---

## 🏗️ Arquitetura

```text
               +-------------------------------------------+
               |           Sua Rede Local (LAN)            |
               +-------------------------------------------+
                                     |
                               (ARP Broadcast)
                                     v
+--------------------------------------------------------------------------+
| Servidor Alpine (ex: Raspberry Pi 192.168.1.7 ou Dev Local)              |
|                                                                          |
|  [ aceberg/watchyourlan:v2 ] (Porta 8840)                                |
|    • Varredura ARP em camada 2 (network_mode: host)                      |
|    • Tradução de MAC para Fabricante (Base OUI embutida)                 |
|    • Interface Web minimalista em Go (~20MB RAM)                         |
|             |                                                            |
|             v (Grava hosts, IP, MAC, status)                             |
|  [ postgres:16-alpine ]                                                  |
|    • Banco de dados relacional persistente                               |
|             ^                                                            |
|             | (Lê dispositivos marcados como [BLOCK])                    |
|  [ lansentry-sidecar ] (Alpine Python Worker)                            |
|             |                                                            |
|             v (Insere MAC no grupo LANSENTRY_BLOCKED)                    |
|  [ Pi-hole + Unbound ] (/etc/pihole/gravity.db)                          |
|    • Regra coringa '.*' bloqueia qualquer resolução DNS para o MAC       |
|    • Tráfego é descartado antes de alcançar o Unbound recursivo          |
+--------------------------------------------------------------------------+
```

---

## 📁 Estrutura de Arquivos

```text
14_LanSentry/
├── .env.example          # Modelo de variáveis de ambiente
├── docker-compose.yml    # Orquestração dos 3 containers (WYL + Postgres + Sidecar)
├── README.md             # Esta documentação
├── data/                 # Volumes de dados locais (ignorados pelo Git)
│   ├── postgres/         # Dados do PostgreSQL
│   └── wyl/              # Configurações do WatchYourLAN
└── sidecar/              # Worker de bloqueio Pi-hole
    ├── Dockerfile        # Container Alpine leve (~15MB)
    ├── requirements.txt  # Dependências Python (psycopg2)
    └── sidecar.py        # Lógica de sincronização
```

---

## 🚀 Como Executar em Ambiente Local (Dev & Testes)

1. **Copie o arquivo de variáveis de ambiente:**
   ```bash
   cp .env.example .env
   ```

2. **Ajuste sua interface de rede no `.env`:**
   Descubra o nome da sua placa de rede com `ip link` ou `ip route show default` (ex: `wlo1` ou `enp3s0`).

3. **Inicie a stack:**
   ```bash
   docker compose up -d --build
   ```

4. **Acesse a interface Web:**
   - URL: `http://localhost:8840`
   - O WatchYourLAN iniciará a varredura da sua rede e listará todos os aparelhos com MAC e Fabricante.

---

## 🚫 Como Bloquear um Aparelho no Pi-hole

1. Acesse a interface web do WatchYourLAN (`http://localhost:8840` ou IP do servidor).
2. Localize o aparelho que não deve mais ter acesso à internet.
3. Clique em **Editar** e inclua a tag `[BLOCK]` no nome do aparelho (exemplo: `[BLOCK] Smart TV Quarto` ou `Tablet [BLOCK]`).
4. O `lansentry-sidecar` identificará a alteração no PostgreSQL e:
   - Adicionará o MAC no grupo `LANSENTRY_BLOCKED` do Pi-hole.
   - O Pi-hole recusará qualquer resolução de nomes para aquele dispositivo.
   - Como o Unbound só atende consultas repassadas pelo Pi-hole, o aparelho fica completamente sem resolução de DNS.

---

## 🚢 Roteiro de Deploy no Raspberry Pi (`ssh alpine`)

Quando os testes locais estiverem concluídos:

1. **Sincronize a pasta para o servidor:**
   ```bash
   rsync -avz --exclude 'data' ~/Documentos/4_HOMELAB/14_LanSentry/ alpine:~/14_LanSentry/
   ```
2. **Conecte via SSH:**
   ```bash
   ssh alpine
   cd 14_LanSentry
   cp .env.example .env
   ```
3. **Configure no `.env` do Alpine:**
   - `IFACES=eth0` (ou a interface local do Raspberry Pi).
   - `PIHOLE_GRAVITY_DB=/etc/pihole/gravity.db` (onde o Pi-hole armazena o banco).
4. **Suba o serviço:**
   ```bash
   docker compose up -d --build
   ```
