// LanSentry UI Enhancement
// Injeta dinamicamente a coluna de Grupo do Pi-hole e Toggle de Bloqueio,
// com filtros na barra superior (input-group) e ordenação interativa (sorting) adotando o padrão nativo do WatchYourLAN.

(function() {
  console.log("🛡️ LanSentry UI Enhancement ativo (com Classificação e Filtros)!");

  // Injeta estilos CSS uma única vez
  if (!document.getElementById('lansentry-styles')) {
    const style = document.createElement('style');
    style.id = 'lansentry-styles';
    style.innerHTML = `
      .lansentry-block-toggle:checked {
        background-color: #dc3545 !important;
        border-color: #dc3545 !important;
      }
      .lansentry-blocked-row {
        background-color: rgba(220, 53, 69, 0.15) !important;
      }
      .lansentry-block-badge {
        font-size: 0.8rem;
        padding: 0.25rem 0.5rem;
      }
      .lansentry-pihole-badge {
        font-size: 0.78rem;
        font-weight: 500;
        letter-spacing: 0.02em;
        white-space: nowrap;
      }
      .lansentry-sort-th {
        cursor: pointer;
        user-select: none;
        white-space: nowrap;
      }
      .lansentry-sort-th:hover {
        color: var(--bs-primary);
      }
      .lansentry-sort-icon {
        font-size: 0.85rem;
        vertical-align: middle;
      }
      .lansentry-filter-select {
        max-width: 170px;
      }
    `;
    document.head.appendChild(style);
  }

  let piholeData = { groups: [], clients: {} };
  let deviceMap = {};
  let isFetching = false;
  let isEnhancing = false;

  // Estado dos filtros e ordenação
  let currentSort = { field: null, direction: 'asc' };
  let currentFilter = { group: 'ALL', block: 'ALL' };

  async function loadData() {
    if (isFetching) return;
    isFetching = true;
    try {
      const [piholeResp, allResp] = await Promise.all([
        fetch('/api/pihole/info').then(r => r.json()).catch(() => null),
        fetch('/api/all').then(r => r.json()).catch(() => null)
      ]);

      if (piholeResp) {
        piholeData = piholeResp;
      }

      if (allResp && Array.isArray(allResp)) {
        deviceMap = {};
        for (const dev of allResp) {
          deviceMap[String(dev.ID)] = dev;
        }
      }
    } catch (e) {
      console.warn("Aviso ao carregar dados LanSentry/Pi-hole:", e);
    } finally {
      isFetching = false;
    }
  }

  loadData();
  setInterval(loadData, 10000);

  function getGroupBadge(groupName) {
    const name = groupName || 'Default';
    switch (name) {
      case 'Infraestrutura':
        return '<span class="badge bg-info text-dark lansentry-pihole-badge">🌐 Infraestrutura</span>';
      case 'IoT & Smart Home':
        return '<span class="badge bg-success lansentry-pihole-badge">💡 IoT & Automação</span>';
      case 'Assistentes & Streaming':
        return '<span class="badge bg-primary lansentry-pihole-badge">📺 Streaming & Alexa</span>';
      case 'Dispositivos Móveis':
        return '<span class="badge bg-warning text-dark lansentry-pihole-badge">📱 Dispositivo Móvel</span>';
      case 'Workstations & PCs':
        return '<span class="badge bg-secondary lansentry-pihole-badge">💻 Workstation / PC</span>';
      case 'Kids & Família':
        return '<span class="badge bg-danger lansentry-pihole-badge">👶 Kids & Família</span>';
      case 'LANSENTRY_BLOCKED':
        return '<span class="badge bg-dark text-danger lansentry-pihole-badge">🚫 Bloqueado</span>';
      default:
        return '<span class="badge bg-light text-secondary border lansentry-pihole-badge">⚪ Padrão</span>';
    }
  }

  function getHostIdFromRow(tr) {
    const links = tr.querySelectorAll('a[href*="/host/"]');
    for (const a of links) {
      const match = a.getAttribute('href').match(/\/host\/(\d+)/);
      if (match) return match[1];
    }
    return null;
  }

  async function toggleBlock(id, willBlock, checkbox, tr, nameInput) {
    checkbox.disabled = true;
    try {
      const resp = await fetch(`/api/block_toggle/${id}/${willBlock ? '1' : '0'}`, {
        method: 'POST'
      });
      const data = await resp.json();
      if (data.success) {
        if (tr) {
          if (willBlock) {
            tr.classList.add('lansentry-blocked-row');
            tr.dataset.lansentryBlocked = '1';
          } else {
            tr.classList.remove('lansentry-blocked-row');
            tr.dataset.lansentryBlocked = '0';
          }
        }
        if (nameInput) {
          const currentVal = nameInput.value || '';
          if (willBlock) {
            if (!currentVal.includes('[BLOCK]')) {
              nameInput.value = `[BLOCK] ${currentVal}`.trim();
            }
          } else {
            nameInput.value = currentVal.replace('[BLOCK]', '').trim();
          }
        }
        await loadData();
        applyFilters();
      } else {
        alert("Falha ao atualizar bloqueio: " + (data.error || "erro desconhecido"));
        checkbox.checked = !willBlock;
      }
    } catch (e) {
      console.error("Erro na chamada de bloqueio:", e);
      checkbox.checked = !willBlock;
    } finally {
      checkbox.disabled = false;
    }
  }

  // Aplica os filtros ativos (Grupo e Bloqueio) nas linhas da tabela
  function applyFilters() {
    const rows = document.querySelectorAll('table tbody tr');
    rows.forEach(tr => {
      // Ignora se for a tabela da tela de detalhes (/host/:id)
      if (tr.children[0] && tr.children[0].textContent.trim() === 'ID') return;

      const groupName = tr.dataset.lansentryGroup || 'Default';
      const isBlocked = tr.dataset.lansentryBlocked === '1';

      let matchGroup = true;
      if (currentFilter.group && currentFilter.group !== 'ALL') {
        matchGroup = (groupName === currentFilter.group);
      }

      let matchBlock = true;
      if (currentFilter.block === '1') {
        matchBlock = isBlocked;
      } else if (currentFilter.block === '0') {
        matchBlock = !isBlocked;
      }

      if (matchGroup && matchBlock) {
        tr.style.display = '';
      } else {
        tr.style.display = 'none';
      }
    });
  }

  // Ordena a tabela por Grupo Pi-hole ou Bloqueio
  function sortTable(field) {
    const tbody = document.querySelector('table tbody');
    if (!tbody) return;

    if (currentSort.field === field) {
      currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
      currentSort.field = field;
      // Para bloqueio, o default mais intuitivo no primeiro clique é exibir os bloqueados no topo (desc)
      currentSort.direction = (field === 'block') ? 'desc' : 'asc';
    }

    const rows = Array.from(tbody.querySelectorAll('tr')).filter(tr => {
      return !(tr.children[0] && tr.children[0].textContent.trim() === 'ID');
    });

    rows.sort((a, b) => {
      if (field === 'group') {
        const gA = (a.dataset.lansentryGroup || 'Default').toLowerCase();
        const gB = (b.dataset.lansentryGroup || 'Default').toLowerCase();
        return currentSort.direction === 'asc' ? gA.localeCompare(gB) : gB.localeCompare(gA);
      } else if (field === 'block') {
        const bA = a.dataset.lansentryBlocked === '1' ? 1 : 0;
        const bB = b.dataset.lansentryBlocked === '1' ? 1 : 0;
        return currentSort.direction === 'desc' ? (bB - bA) : (bA - bB);
      }
      return 0;
    });

    rows.forEach(r => tbody.appendChild(r));
    updateSortIcons();
    applyFilters();
  }

  function updateSortIcons() {
    const thGroup = document.querySelector('.lansentry-th-group');
    const thBlock = document.querySelector('.lansentry-th-block');

    if (thGroup) {
      const icon = thGroup.querySelector('.lansentry-sort-icon');
      if (icon) {
        if (currentSort.field === 'group') {
          icon.className = `bi ${currentSort.direction === 'asc' ? 'bi-sort-alpha-down' : 'bi-sort-alpha-up-alt'} my-btn ms-1 lansentry-sort-icon text-primary`;
        } else {
          icon.className = 'bi bi-sort-down-alt my-btn ms-1 lansentry-sort-icon text-secondary opacity-50';
        }
      }
    }

    if (thBlock) {
      const icon = thBlock.querySelector('.lansentry-sort-icon');
      if (icon) {
        if (currentSort.field === 'block') {
          icon.className = `bi ${currentSort.direction === 'desc' ? 'bi-sort-down' : 'bi-sort-up'} my-btn ms-1 lansentry-sort-icon text-danger`;
        } else {
          icon.className = 'bi bi-sort-down-alt my-btn ms-1 lansentry-sort-icon text-secondary opacity-50';
        }
      }
    }
  }

  // 1. Injeta os selects de filtro no grupo de inputs nativo do WatchYourLAN
  function enhanceFilterBar() {
    const inputGroup = document.querySelector('.input-group');
    if (!inputGroup) return;

    const resetBtn = Array.from(inputGroup.querySelectorAll('button')).find(
      btn => btn.textContent.includes('Reset filter') || btn.getAttribute('title') === 'Reset filter'
    );
    if (!resetBtn) return;

    // Filtro Grupo Pi-hole
    if (!inputGroup.querySelector('.lansentry-filter-group')) {
      const selectGroup = document.createElement('select');
      selectGroup.className = 'form-select lansentry-filter-select lansentry-filter-group';
      selectGroup.title = 'Filter by Grupo Pi-hole';

      const defaultGroups = [
        "Infraestrutura",
        "IoT & Smart Home",
        "Assistentes & Streaming",
        "Dispositivos Móveis",
        "Workstations & PCs",
        "Kids & Família",
        "LANSENTRY_BLOCKED",
        "Default"
      ];

      const groups = (piholeData && piholeData.groups && piholeData.groups.length > 0)
        ? piholeData.groups.map(g => g.name)
        : defaultGroups;

      let options = `<option value="" disabled ${currentFilter.group === 'ALL' ? 'selected' : ''}>Grupo Pi-hole</option>`;
      options += `<option value="ALL" ${currentFilter.group === 'ALL' ? 'selected' : ''}>Todos os Grupos</option>`;

      groups.forEach(gName => {
        options += `<option value="${gName}" ${currentFilter.group === gName ? 'selected' : ''}>${gName}</option>`;
      });

      selectGroup.innerHTML = options;
      selectGroup.addEventListener('change', (e) => {
        currentFilter.group = e.target.value;
        applyFilters();
      });

      inputGroup.insertBefore(selectGroup, resetBtn);
    }

    // Filtro de Bloqueio
    if (!inputGroup.querySelector('.lansentry-filter-block')) {
      const selectBlock = document.createElement('select');
      selectBlock.className = 'form-select lansentry-filter-select lansentry-filter-block';
      selectBlock.title = 'Filter by Bloqueio';
      selectBlock.innerHTML = `
        <option value="" disabled ${currentFilter.block === 'ALL' ? 'selected' : ''}>Bloqueio</option>
        <option value="ALL" ${currentFilter.block === 'ALL' ? 'selected' : ''}>Todos</option>
        <option value="1" ${currentFilter.block === '1' ? 'selected' : ''}>🚫 Bloqueados</option>
        <option value="0" ${currentFilter.block === '0' ? 'selected' : ''}>✅ Liberados</option>
      `;

      selectBlock.addEventListener('change', (e) => {
        currentFilter.block = e.target.value;
        applyFilters();
      });

      inputGroup.insertBefore(selectBlock, resetBtn);
    }

    // Vincula o botão nativo Reset filter para restaurar também os filtros do LanSentry
    if (!resetBtn.dataset.lansentryHooked) {
      resetBtn.dataset.lansentryHooked = 'true';
      resetBtn.addEventListener('click', () => {
        currentFilter.group = 'ALL';
        currentFilter.block = 'ALL';
        const selG = inputGroup.querySelector('.lansentry-filter-group');
        if (selG) selG.value = 'ALL';
        const selB = inputGroup.querySelector('.lansentry-filter-block');
        if (selB) selB.value = 'ALL';
        setTimeout(applyFilters, 100);
      });
    }
  }

  // 2. Injeta colunas de Grupo Pi-hole e Bloqueio na tabela principal
  function enhanceTable() {
    const thead = document.querySelector('table thead tr');
    if (!thead) return;

    // Cabeçalho Grupo Pi-hole com ordenação
    let thGroup = thead.querySelector('.lansentry-th-group');
    if (!thGroup) {
      thGroup = document.createElement('th');
      thGroup.className = 'lansentry-th-group lansentry-sort-th';
      thGroup.style.width = '13em';
      thGroup.title = 'Clique para ordenar por Grupo Pi-hole';
      thGroup.innerHTML = '<span>Grupo Pi-hole</span> <i class="bi bi-sort-down-alt my-btn ms-1 lansentry-sort-icon text-secondary opacity-50" title="Ordenar"></i>';
      thGroup.addEventListener('click', () => sortTable('group'));
      thead.appendChild(thGroup);
    }

    // Cabeçalho Bloqueio com ordenação
    let thBlock = thead.querySelector('.lansentry-th-block');
    if (!thBlock) {
      thBlock = document.createElement('th');
      thBlock.className = 'lansentry-th-block lansentry-sort-th';
      thBlock.style.width = '7.5em';
      thBlock.title = 'Clique para ordenar por Status de Bloqueio';
      thBlock.innerHTML = '<span>Bloquear</span> <i class="bi bi-sort-down-alt my-btn ms-1 lansentry-sort-icon text-secondary opacity-50" title="Ordenar"></i>';
      thBlock.addEventListener('click', () => sortTable('block'));
      thead.appendChild(thBlock);
    }

    const rows = document.querySelectorAll('table tbody tr');
    rows.forEach(tr => {
      // Ignora se for a tabela da tela de detalhes (/host/:id)
      if (tr.children[0] && tr.children[0].textContent.trim() === 'ID') return;

      const hostId = getHostIdFromRow(tr);
      if (!hostId) return;

      const dev = deviceMap[hostId];
      const mac = dev && dev.Mac ? dev.Mac.toUpperCase().trim() : '';
      const ip = dev && dev.IP ? dev.IP.trim() : '';

      // Descobre se o nome contém [BLOCK]
      const nameInputOrText = tr.querySelector('input[type="text"]') || tr.children[2] || tr.children[1];
      const nameText = nameInputOrText ? (nameInputOrText.value || nameInputOrText.textContent || '') : '';
      const isBlocked = nameText.includes('[BLOCK]');

      if (isBlocked) {
        tr.classList.add('lansentry-blocked-row');
      } else {
        tr.classList.remove('lansentry-blocked-row');
      }

      // Descobre o grupo do Pi-hole
      let groupName = 'Default';
      if (piholeData && piholeData.clients) {
        const clientInfo = (mac ? piholeData.clients[mac] : null) || (ip ? piholeData.clients[ip.toUpperCase()] : null);
        if (clientInfo) {
          groupName = clientInfo.primary_group_name || 'Default';
        }
      }

      // Registra dados nas propriedades do elemento tr para ordenação e filtro instantâneos
      tr.dataset.lansentryGroup = groupName;
      tr.dataset.lansentryBlocked = isBlocked ? '1' : '0';

      // Atualiza ou insere td de Grupo Pi-hole
      let tdGroup = tr.querySelector('.lansentry-td-group');
      if (!tdGroup) {
        tdGroup = document.createElement('td');
        tdGroup.className = 'lansentry-td-group';
        tdGroup.dataset.group = groupName;
        tdGroup.innerHTML = getGroupBadge(groupName);
        tr.appendChild(tdGroup);
      } else if (tdGroup.dataset.group !== groupName) {
        tdGroup.dataset.group = groupName;
        tdGroup.innerHTML = getGroupBadge(groupName);
      }

      // Atualiza ou insere td de Toggle de Bloqueio
      let tdBlock = tr.querySelector('.lansentry-td-block');
      if (!tdBlock) {
        tdBlock = document.createElement('td');
        tdBlock.className = 'lansentry-td-block';
        tdBlock.innerHTML = `
          <div class="form-check form-switch" title="${isBlocked ? 'Dispositivo Bloqueado no Pi-hole' : 'Clique para Bloquear no Pi-hole'}">
            <input class="form-check-input lansentry-block-toggle" type="checkbox" ${isBlocked ? 'checked' : ''} style="cursor: pointer;">
          </div>
        `;

        const switchInput = tdBlock.querySelector('input');
        switchInput.addEventListener('change', (e) => {
          toggleBlock(hostId, e.target.checked, switchInput, tr, null);
        });

        tr.appendChild(tdBlock);
      } else {
        const switchInput = tdBlock.querySelector('input');
        if (switchInput && switchInput.checked !== isBlocked) {
          switchInput.checked = isBlocked;
        }
      }
    });

    applyFilters();
  }

  // 3. Injeta linha de grupo e bloqueio na tela de detalhes do host (/host/:id)
  function enhanceHostPage() {
    const rows = Array.from(document.querySelectorAll('table tbody tr'));
    const idRow = rows.find(r => r.children[0] && r.children[0].textContent.trim() === 'ID');
    if (!idRow) return;

    const hostId = idRow.children[1] ? idRow.children[1].textContent.trim() : null;
    if (!hostId) return;

    const dev = deviceMap[hostId];
    const mac = dev && dev.Mac ? dev.Mac.toUpperCase().trim() : '';
    const ip = dev && dev.IP ? dev.IP.trim() : '';

    const nameRow = rows.find(r => r.children[0] && r.children[0].textContent.trim() === 'Name');
    const nameInput = nameRow ? nameRow.querySelector('input') : null;
    const isBlocked = nameInput ? nameInput.value.includes('[BLOCK]') : false;

    const knownRow = rows.find(r => r.children[0] && r.children[0].textContent.trim() === 'Known');
    const targetRow = knownRow || idRow;

    // Seletor de Grupo do Pi-hole
    if (!document.querySelector('.lansentry-hostpage-group-row')) {
      let currentGroupId = 0;
      if (piholeData && piholeData.clients) {
        const clientInfo = (mac ? piholeData.clients[mac] : null) || (ip ? piholeData.clients[ip.toUpperCase()] : null);
        if (clientInfo) {
          currentGroupId = clientInfo.primary_group_id || 0;
        }
      }

      const groups = (piholeData && piholeData.groups && piholeData.groups.length > 0) 
        ? piholeData.groups 
        : [
            { id: 0, name: "Default" },
            { id: 1, name: "Infraestrutura" },
            { id: 2, name: "IoT & Smart Home" },
            { id: 3, name: "Assistentes & Streaming" },
            { id: 4, name: "Dispositivos Móveis" },
            { id: 5, name: "Workstations & PCs" },
            { id: 6, name: "Kids & Família" }
          ];

      const optionsHtml = groups.map(g => 
        `<option value="${g.id}" ${Number(g.id) === Number(currentGroupId) ? 'selected' : ''}>${g.name}</option>`
      ).join('');

      const groupTr = document.createElement('tr');
      groupTr.className = 'lansentry-hostpage-group-row';
      groupTr.innerHTML = `
        <td><strong>Grupo no Pi-hole</strong></td>
        <td>
          <div class="d-flex align-items-center">
            <select class="form-select form-select-sm w-auto me-2 lansentry-group-select" style="min-width: 220px; font-weight: 500;">
              ${optionsHtml}
            </select>
            <span class="badge bg-success d-none lansentry-group-feedback">✓ Atualizado</span>
          </div>
        </td>
      `;

      const selectElem = groupTr.querySelector('.lansentry-group-select');
      const feedbackElem = groupTr.querySelector('.lansentry-group-feedback');

      selectElem.addEventListener('change', async (e) => {
        const newGid = e.target.value;
        selectElem.disabled = true;
        try {
          const resp = await fetch(`/api/pihole/set_group/${hostId}/${newGid}`, { method: 'POST' });
          const res = await resp.json();
          if (res.success) {
            feedbackElem.classList.remove('d-none');
            setTimeout(() => feedbackElem.classList.add('d-none'), 3000);
            await loadData();
          } else {
            alert("Erro ao alterar grupo: " + (res.error || "desconhecido"));
          }
        } catch (err) {
          alert("Erro de rede ao alterar grupo: " + err);
        } finally {
          selectElem.disabled = false;
        }
      });

      targetRow.parentNode.insertBefore(groupTr, targetRow.nextSibling);
    }

    // Toggle de Bloqueio na Tela do Host
    if (!document.querySelector('.lansentry-hostpage-block-row')) {
      const blockTr = document.createElement('tr');
      blockTr.className = 'lansentry-hostpage-block-row';
      blockTr.innerHTML = `
        <td><strong>Bloquear no Pi-hole</strong></td>
        <td>
          <div class="form-check form-switch d-flex align-items-center">
            <input class="form-check-input lansentry-block-toggle" type="checkbox" ${isBlocked ? 'checked' : ''} style="cursor: pointer;">
            <span class="ms-2 badge bg-danger ${isBlocked ? '' : 'd-none'} lansentry-block-badge">🚫 Acesso Revogado</span>
          </div>
        </td>
      `;

      const switchInput = blockTr.querySelector('input');
      const badge = blockTr.querySelector('.lansentry-block-badge');

      switchInput.addEventListener('change', (e) => {
        const willBlock = e.target.checked;
        toggleBlock(hostId, willBlock, switchInput, null, nameInput);
        if (willBlock) {
          badge.classList.remove('d-none');
        } else {
          badge.classList.add('d-none');
        }
      });

      const groupRow = document.querySelector('.lansentry-hostpage-group-row');
      const insertAnchor = groupRow || targetRow;
      insertAnchor.parentNode.insertBefore(blockTr, insertAnchor.nextSibling);
    }
  }

  function runEnhancements() {
    if (isEnhancing) return;
    isEnhancing = true;
    try {
      enhanceFilterBar();
      enhanceTable();
      enhanceHostPage();
    } catch (err) {
      console.warn("Aviso render LanSentry:", err);
    } finally {
      isEnhancing = false;
    }
  }

  // Executa periodicamente a cada 1 segundo (leve, seguro e compatível com SPA)
  setInterval(runEnhancements, 1000);
})();
