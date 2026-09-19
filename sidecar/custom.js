// LanSentry UI Enhancement
// Injeta dinamicamente a coluna e o toggle de bloqueio na tabela do WatchYourLAN

(function() {
  console.log("🛡️ LanSentry UI Enhancement carregado!");

  // Injeta estilos CSS para o toggle de perigo (vermelho)
  const style = document.createElement('style');
  style.innerHTML = `
    .lansentry-block-toggle:checked {
      background-color: #dc3545 !important;
      border-color: #dc3545 !important;
    }
    .lansentry-blocked-row {
      background-color: rgba(220, 53, 69, 0.15) !important;
    }
    .lansentry-badge {
      font-size: 0.75rem;
      padding: 0.2rem 0.4rem;
      border-radius: 4px;
      font-weight: bold;
    }
  `;
  document.head.appendChild(style);

  function getHostIdFromRow(tr) {
    // Procura links como /host/12
    const links = tr.querySelectorAll('a[href*="/host/"]');
    for (const a of links) {
      const match = a.getAttribute('href').match(/\/host\/(\d+)/);
      if (match) return match[1];
    }
    return null;
  }

  async function toggleBlock(id, willBlock, checkbox, tr) {
    checkbox.disabled = true;
    try {
      const resp = await fetch(`/api/block_toggle/${id}/${willBlock ? '1' : '0'}`, {
        method: 'POST'
      });
      const data = await resp.json();
      if (data.success) {
        if (willBlock) {
          tr.classList.add('lansentry-blocked-row');
        } else {
          tr.classList.remove('lansentry-blocked-row');
        }
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

  function enhanceTable() {
    const thead = document.querySelector('table thead tr');
    if (!thead) return;

    // 1. Injeta cabeçalho "Bloquear" se ainda não existir
    if (!thead.querySelector('.lansentry-th-block')) {
      const th = document.createElement('th');
      th.className = 'lansentry-th-block';
      th.style.width = '6em';
      th.innerHTML = '<i class="bi bi-shield-slash-fill text-danger" title="Bloquear no Pi-hole"></i> Bloquear';
      thead.appendChild(th);
    }

    // 2. Injeta a coluna nas linhas do corpo da tabela
    const rows = document.querySelectorAll('table tbody tr');
    rows.forEach(tr => {
      if (tr.querySelector('.lansentry-td-block')) return;

      const hostId = getHostIdFromRow(tr);
      if (!hostId) return;

      const nameCell = tr.children[1];
      const isBlocked = nameCell && nameCell.textContent.includes('[BLOCK]');

      if (isBlocked) {
        tr.classList.add('lansentry-blocked-row');
      }

      const td = document.createElement('td');
      td.className = 'lansentry-td-block';
      td.innerHTML = `
        <div class="form-check form-switch" title="${isBlocked ? 'Dispositivo Bloqueado no Pi-hole' : 'Clique para Bloquear no Pi-hole'}">
          <input class="form-check-input lansentry-block-toggle" type="checkbox" ${isBlocked ? 'checked' : ''} style="cursor: pointer;">
        </div>
      `;

      const switchInput = td.querySelector('input');
      switchInput.addEventListener('change', (e) => {
        toggleBlock(hostId, e.target.checked, switchInput, tr);
      });

      tr.appendChild(td);
    });
  }

  // Monitora alterações no DOM para renderizar mesmo com navegação SPA
  const observer = new MutationObserver(() => {
    enhanceTable();
  });

  observer.observe(document.body, { childList: true, subtree: true });
  setInterval(enhanceTable, 1000);
})();
