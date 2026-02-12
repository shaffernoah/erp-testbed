/* ============================================================
   LaFrieda ERP Dashboard - KPIs, Sidebar, Alerts
   ============================================================ */

// ---- KPI Fetching ----
function fetchKPIs() {
  var xhr = new XMLHttpRequest();
  xhr.open('GET', '/api/kpis', true);
  xhr.onload = function() {
    if (xhr.status !== 200) return;
    try {
      var data = JSON.parse(xhr.responseText);
      updateKPICards(data);
      updateAlertFeed(data.recent_alerts || []);
    } catch(e) {
      console.error('KPI parse error:', e);
    }
  };
  xhr.onerror = function() {
    console.error('KPI fetch failed');
  };
  xhr.send();
}

function updateKPICards(data) {
  // Expiry Risk
  if (data.expiry_risk) {
    var er = data.expiry_risk;
    document.getElementById('kpi-expiry-value').textContent = er.count + ' lots';
    document.getElementById('kpi-expiry-sub').textContent = '$' + formatNumber(er.value) + ' at risk';
    updateKPIStatus('expiry_risk', er.status);
  }

  // Slow Movers
  if (data.slow_movers) {
    var sm = data.slow_movers;
    document.getElementById('kpi-slow-value').textContent = sm.count + ' SKUs';
    document.getElementById('kpi-slow-sub').textContent = '$' + formatNumber(sm.value) + ' sitting idle';
    updateKPIStatus('slow_movers', sm.status);
  }

  // Route Efficiency
  if (data.route_efficiency) {
    var re = data.route_efficiency;
    document.getElementById('kpi-route-value').textContent = re.avg_utilization + '%';
    document.getElementById('kpi-route-sub').textContent = re.active_routes + ' active routes';
    updateKPIStatus('route_efficiency', re.status);
  }

  // Margin Opps
  if (data.margin_opps) {
    var mo = data.margin_opps;
    document.getElementById('kpi-margin-value').textContent = mo.count + ' items';
    document.getElementById('kpi-margin-sub').textContent = 'Avg ' + mo.avg_margin + '% margin';
    updateKPIStatus('margin_opps', mo.status);
  }
}

function updateKPIStatus(kpi, status) {
  var card = document.querySelector('[data-kpi="' + kpi + '"]');
  if (!card) return;
  card.classList.remove('status-critical', 'status-warning', 'status-ok', 'status-info');
  if (status) card.classList.add('status-' + status);
}

function updateAlertFeed(alerts) {
  var feed = document.getElementById('alert-feed');
  var badge = document.getElementById('alert-count');

  if (!alerts || alerts.length === 0) {
    feed.innerHTML = '<div class="alert-feed-loading">No active alerts</div>';
    badge.textContent = '0';
    return;
  }

  badge.textContent = alerts.length;
  feed.innerHTML = '';

  alerts.slice(0, 8).forEach(function(alert) {
    var div = document.createElement('div');
    div.className = 'alert-feed-item ' + (alert.severity || 'info').toLowerCase();
    div.innerHTML = '<div class="alert-title">' + escapeHtml(alert.title || '') + '</div>' +
      '<div class="alert-detail">' + escapeHtml((alert.detail || '').substring(0, 100)) + '</div>';
    feed.appendChild(div);
  });
}

function formatNumber(n) {
  if (n == null) return '0';
  return Math.round(n).toLocaleString();
}

function escapeHtml(text) {
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', function() {
  fetchKPIs();
  // Refresh KPIs every 30 seconds
  setInterval(fetchKPIs, 30000);
});
