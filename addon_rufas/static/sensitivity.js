// Sensitivity panel: tornado of every input, then the curve and ration of the clicked one. Data comes in SENS.
(() => {
  if (typeof SENS === "undefined" || !SENS.items.length) return;

  const FALL = "#3987e5";  // cost falls (diverging blue pole)
  const RISE = "#e66767";  // cost rises (diverging red pole)
  const INK = "#e4eee7", MUTED = "#a7b9ad", GRID = "#30483a", SURFACE = "#18231e";
  // Categorical slots in fixed order (dark steps, validated on the panel surface).
  const FEED_COLORS = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"];
  const OTHER = "#7a8a80";

  const esc = (text) => String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const num = (x, d = 2) => x == null ? "—" : x.toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });
  const signed = (x, d = 2) => x == null ? "—" : (x > 0 ? "+" : x < 0 ? "−" : "") + num(Math.abs(x), d);
  const val = (x) => x == null ? "—" : x.toLocaleString("pt-BR", { maximumFractionDigits: Math.abs(x) >= 100 ? 1 : 4 });
  const pct = (x) => x == null ? "inviável" : signed(x) + "%";
  const level = (p) => (p > 0 ? "+" : p < 0 ? "−" : "") + num(Math.abs(p), 0) + "%";

  const color = {}, name = {};
  SENS.feeds.forEach((f, i) => { color[f.id] = i < FEED_COLORS.length ? FEED_COLORS[i] : OTHER; name[f.id] = f.name; });

  const tip = document.getElementById("sens-tip");
  function showTip(event, html) {
    tip.innerHTML = html;
    tip.hidden = false;
    const box = tip.getBoundingClientRect(), pad = 14;
    let x = event.clientX + pad, y = event.clientY + pad;
    if (x + box.width > innerWidth - 8) x = event.clientX - box.width - pad;
    if (y + box.height > innerHeight - 8) y = event.clientY - box.height - pad;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }
  const hideTip = () => { tip.hidden = true; };

  let item = SENS.items.find((i) => i.key === SENS.selected) || SENS.items[0];

  const pointAt = (it, p) => it.curve.find((c) => c.percent === p);
  const base = (it) => pointAt(it, 0);
  // Feeds that leave or enter compared with the current ration (0%): what a farmer would change.
  function swap(it, p) {
    if (!p.feasible) return "";
    const now = Object.keys(base(it).amounts), then = Object.keys(p.amounts);
    return [...now.filter((id) => !then.includes(id)).map((id) => `sai ${name[id]}`),
            ...then.filter((id) => !now.includes(id)).map((id) => `entra ${name[id]}`)].join(", ");
  }
  // Validity range: how far the item moves keeping the feeds of the current ration (bisection on the server).
  const edge = (v, dir) => v.change == null ? (dir < 0 ? "abaixo de −30%" : "acima de +30%") : signed(v.same, 1) + "%";
  const range = (it) => it.valid_down.change == null && it.valid_up.change == null
    ? "em toda a faixa de ±30%" : `de ${edge(it.valid_down, -1)} a ${edge(it.valid_up, 1)}`;
  // Start on the level closest to the current ration where the feeds differ; otherwise on +step.
  function startLevel(it) {
    const differ = it.curve.filter((p) => p.percent !== 0 && swap(it, p));
    return differ.length ? differ.reduce((a, b) => Math.abs(b.percent) < Math.abs(a.percent) ? b : a).percent : SENS.step;
  }
  let chosen = startLevel(item);

  function select(key) {
    item = SENS.items.find((i) => i.key === key);
    chosen = startLevel(item);
    const remembered = document.getElementById("sens-param");  // a new run starts on the same item
    if (remembered) remembered.value = key;
    draw();
  }

  // ---- Tornado -------------------------------------------------------------------------------------------------
  function drawTornado() {
    const root = document.getElementById("tornado");
    root.innerHTML = "";
    const width = (d) => d == null ? 0 : Math.max(1.5, 100 * Math.abs(d) / SENS.largest);
    const fill = (d) => d == null ? "transparent" : d < 0 ? FALL : RISE;
    SENS.items.forEach((it) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "tor-row" + (it.key === item.key ? " active" : "");
      row.setAttribute("aria-pressed", it.key === item.key);
      row.innerHTML =
        `<span class="tor-label">${esc(it.label)}</span>` +
        `<span class="tor-current" title="Faixa em que a ração mantém os mesmos alimentos">mesma ração ${range(it)}</span>` +
        `<span class="tor-val">${pct(it.down)}</span>` +
        `<span class="tor-half left"><i style="width:${width(it.down)}%;background:${fill(it.down)}"></i></span>` +
        `<span class="tor-half right"><i style="width:${width(it.up)}%;background:${fill(it.up)}"></i></span>` +
        `<span class="tor-val">${pct(it.up)}</span>` +
        `<span class="tor-e">E ${signed(it.elasticity)}</span>`;
      row.addEventListener("click", () => select(it.key));
      row.addEventListener("mousemove", (e) => showTip(e,
        `<b>${esc(it.label)}</b><br>Atual: ${val(it.value)} ${esc(it.unit)}` +
        `<br>${SENS.step}% menor: custo ${pct(it.down)}<br>${SENS.step}% maior: custo ${pct(it.up)}` +
        `<br>Elasticidade: ${signed(it.elasticity)}` +
        `<br><b>Mesma ração ${range(it)}</b>` +
        (it.valid_up.change != null ? `<br>Acima de ${signed(it.valid_up.same, 1)}%: ${esc(it.valid_up.what)}` : "") +
        (it.valid_down.change != null ? `<br>Abaixo de ${signed(it.valid_down.same, 1)}%: ${esc(it.valid_down.what)}` : "") +
        (it.marginal != null ? `<br>Custo marginal: ${signed(it.marginal, 4)} $ por ${esc(it.unit)}` : "") +
        ""));
      row.addEventListener("mouseleave", hideTip);
      root.appendChild(row);
    });
  }

  // ---- Curve ---------------------------------------------------------------------------------------------------
  function drawCurve() {
    const svg = document.getElementById("curve");
    const W = 560, H = 260, L = 64, R = 18, T = 30, B = 38;
    const pts = item.curve;
    const ok = pts.filter((p) => p.feasible);
    const xs = pts.map((p) => p.percent);
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    let y0 = Math.min(...ok.map((p) => p.cost)), y1 = Math.max(...ok.map((p) => p.cost));
    const padY = (y1 - y0) * 0.12 || Math.abs(y1) * 0.02 || 1;
    y0 -= padY; y1 += padY;
    const X = (p) => L + (p - x0) / (x1 - x0) * (W - L - R);
    const Y = (c) => T + (y1 - c) / (y1 - y0) * (H - T - B);
    let g = "";
    for (let k = 0; k <= 4; k++) {  // recessive grid
      const c = y0 + (y1 - y0) * k / 4;
      g += `<line x1="${L}" x2="${W - R}" y1="${Y(c)}" y2="${Y(c)}" stroke="${GRID}" stroke-width="1"/>` +
           `<text x="${L - 8}" y="${Y(c) + 4}" text-anchor="end" fill="${MUTED}" font-size="11">${num(c)}</text>`;
    }
    pts.forEach((p) => {
      g += `<text x="${X(p.percent)}" y="${H - 18}" text-anchor="middle" fill="${p.percent === 0 ? INK : MUTED}" font-size="11">${level(p.percent)}</text>`;
    });
    g += `<text x="${(L + W - R) / 2}" y="${H - 3}" text-anchor="middle" fill="${MUTED}" font-size="11">variação de ${esc(item.label.toLowerCase())}</text>`;
    g += `<text x="12" y="${T - 14}" fill="${MUTED}" font-size="11">custo ($/vaca/dia)</text>`;
    // validity band: the item can move inside it and the ration keeps the same feeds
    const lo = Math.max(x0, item.valid_down.change == null ? x0 : item.valid_down.same);
    const hi = Math.min(x1, item.valid_up.change == null ? x1 : item.valid_up.same);
    g += `<rect x="${X(lo)}" y="${T}" width="${Math.max(0, X(hi) - X(lo))}" height="${H - T - B}" fill="#3eaa64" opacity=".12"/>` +
         `<text x="${(X(lo) + X(hi)) / 2}" y="${T + 13}" text-anchor="middle" fill="${INK}" font-size="10.5">mesma ração</text>`;
    [item.valid_down, item.valid_up].forEach((v, k) => {  // exact points where the feeds change
      if (v.change == null) return;
      const x = X(v.change), right = k === 1;
      g += `<line x1="${x}" x2="${x}" y1="${T}" y2="${H - B}" stroke="${INK}" stroke-width="1" stroke-dasharray="4 4" opacity=".7"/>` +
           `<text x="${x + (right ? 4 : -4)}" y="${H - B - 6}" text-anchor="${right ? "start" : "end"}" fill="${INK}" font-size="10.5">${signed(v.same, 1)}%</text>`;
    });
    let path = "", pen = false;
    pts.forEach((p) => {
      if (!p.feasible) { pen = false; return; }
      path += (pen ? "L" : "M") + X(p.percent) + " " + Y(p.cost);
      pen = true;
    });
    g += `<path d="${path}" fill="none" stroke="${FALL}" stroke-width="2" stroke-linejoin="round"/>`;
    const cur = pointAt(item, chosen);
    if (cur && cur.feasible) g += `<line x1="${X(cur.percent)}" x2="${X(cur.percent)}" y1="${T}" y2="${H - B}" stroke="${INK}" stroke-width="1" opacity=".35"/>`;
    ok.forEach((p) => {
      const big = p.percent === chosen;
      g += `<circle cx="${X(p.percent)}" cy="${Y(p.cost)}" r="${big ? 7 : 4.5}" fill="${p.percent === 0 ? SURFACE : FALL}" stroke="${p.percent === 0 ? INK : SURFACE}" stroke-width="2"/>`;
    });
    pts.filter((p) => !p.feasible).forEach((p) => {
      g += `<text x="${X(p.percent)}" y="${T + 14}" text-anchor="middle" fill="${RISE}" font-size="11">inviável</text>`;
    });
    g += `<line id="cross" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="${MUTED}" stroke-width="1" visibility="hidden"/>`;
    g += `<rect id="hit" x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent" style="cursor:pointer"/>`;
    svg.innerHTML = g;
    svg.setAttribute("aria-label", `Custo da dieta conforme ${item.label} varia de ${level(x0)} a ${level(x1)}`);

    const hit = svg.getElementById("hit"), cross = svg.getElementById("cross");
    const nearest = (event) => {
      const box = svg.getBoundingClientRect();
      const sx = (event.clientX - box.left) / box.width * W;
      return pts.reduce((a, b) => Math.abs(X(b.percent) - sx) < Math.abs(X(a.percent) - sx) ? b : a);
    };
    hit.addEventListener("mousemove", (e) => {
      const p = nearest(e);
      cross.setAttribute("x1", X(p.percent)); cross.setAttribute("x2", X(p.percent)); cross.setAttribute("visibility", "visible");
      const b = base(item);
      showTip(e, `<b>${level(p.percent)}</b> · ${val(p.value)} ${esc(item.unit)}<br>` +
        (p.feasible ? `Custo: ${num(p.cost)} $ (${pct(100 * (p.cost - b.cost) / b.cost)})<br>IOFC: ${num(p.iofc)} $` : "Ração inviável") +
        (swap(item, p) ? `<br><b>Em relação à ração atual: ${esc(swap(item, p))}</b>` : "") + "<br><span class='muted'>clique para ver a ração</span>");
    });
    hit.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); hideTip(); });
    hit.addEventListener("click", (e) => { chosen = nearest(e).percent; drawCurve(); drawStack(); drawDetail(); });
  }

  // ---- Ration at each level (stacked bars) ---------------------------------------------------------------------
  function drawStack() {
    const root = document.getElementById("stack");
    root.innerHTML = "";
    const totals = item.curve.map((p) => Object.values(p.amounts).reduce((a, b) => a + b, 0));
    const most = Math.max(...totals, 1e-9);
    const ids = SENS.feeds.map((f) => f.id).filter((id) => item.curve.some((p) => p.amounts[id]));
    item.curve.forEach((p, i) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "stack-row" + (p.percent === chosen ? " active" : "") + (p.percent === 0 ? " now" : "");
      let bar = "";
      if (p.feasible) {
        ids.forEach((id) => {
          const kg = p.amounts[id];
          if (!kg) return;
          bar += `<i data-id="${id}" style="width:${100 * kg / most}%;background:${color[id]}"></i>`;
        });
      } else {
        bar = `<span class="muted">inviável</span>`;
      }
      row.innerHTML = `<span class="stack-level">${level(p.percent)}${p.percent === 0 ? " (atual)" : ""}</span>` +
        `<span class="stack-bar">${bar}</span><span class="stack-total">${p.feasible ? num(totals[i], 1) + " kg" : ""}</span>` +
        `<span class="stack-change" title="${esc(swap(item, p))}">${swap(item, p) ? "troca" : ""}</span>`;
      row.addEventListener("click", () => { chosen = p.percent; drawCurve(); drawStack(); drawDetail(); });
      row.querySelectorAll("i").forEach((seg) => {
        seg.addEventListener("mousemove", (e) => showTip(e, `<b>${esc(name[seg.dataset.id])}</b><br>${num(p.amounts[seg.dataset.id], 3)} kg MS/dia em ${level(p.percent)}`));
        seg.addEventListener("mouseleave", hideTip);
      });
      root.appendChild(row);
    });
    document.getElementById("feed-legend").innerHTML = ids.map((id) =>
      `<span><i class="swatch" style="background:${color[id]}"></i>${esc(name[id])}</span>`).join("");
  }

  // ---- Detail of the chosen level ------------------------------------------------------------------------------
  function drawDetail() {
    const p = pointAt(item, chosen), b = base(item);
    const root = document.getElementById("detail");
    if (!p.feasible) {
      root.innerHTML = `<h4>${esc(item.label)} ${level(p.percent)}: ração inviável</h4><p class="muted">Nesse nível, nenhuma combinação dos alimentos marcados atende todas as restrições.</p>`;
      return;
    }
    const ids = [...new Set([...Object.keys(b.amounts), ...Object.keys(p.amounts)])].sort((a, c) => (p.amounts[c] || 0) - (p.amounts[a] || 0));
    const rows = ids.map((id) => {
      const now = b.amounts[id] || 0, then = p.amounts[id] || 0, d = then - now;
      const tag = now < 1e-3 && then >= 1e-3 ? " · entra" : then < 1e-3 && now >= 1e-3 ? " · sai" : "";
      return `<tr><td><i class="swatch" style="background:${color[id]}"></i>${esc(name[id])}${tag}</td><td>${num(now, 3)}</td><td>${num(then, 3)}</td><td>${signed(d, 3)}</td></tr>`;
    }).join("");
    root.innerHTML =
      `<h4>${esc(item.label)} ${level(p.percent)} <span class="muted">(${val(b.value)} → ${val(p.value)} ${esc(item.unit)})</span></h4>` +
      `<div class="sens-metrics"><div><span>Custo</span><strong>${num(p.cost)} $</strong><em>${pct(100 * (p.cost - b.cost) / b.cost)}</em></div>` +
      `<div><span>IOFC</span><strong>${num(p.iofc)} $</strong><em>${signed(p.iofc - b.iofc)} $</em></div>` +
      `<div><span>Elasticidade</span><strong>${signed(item.elasticity)}</strong><em>% no custo por 1%</em></div></div>` +
      (swap(item, p) ? `<p><b>Em relação à ração atual:</b> ${esc(swap(item, p))}.</p>`
                     : `<p class="muted">Os alimentos são os mesmos da ração atual; mudam só as quantidades.</p>`) +
      `<table><thead><tr><th>Alimento</th><th>Atual (kg MS)</th><th>${level(p.percent)} (kg MS)</th><th>Diferença</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  // ---- Table view ----------------------------------------------------------------------------------------------
  function drawTable() {
    const head = `<tr><th>Item</th><th>Atual</th><th>Custo −${SENS.step}%</th><th>Custo +${SENS.step}%</th><th>Elasticidade</th><th>Custo marginal</th><th>Mesma ração (faixa de validade)</th><th>O que muda fora da faixa</th></tr>`;
    const body = SENS.items.map((it) => `<tr${it.key === item.key ? ' class="current"' : ""}><td>${esc(it.label)}</td>` +
      `<td>${val(it.value)} ${esc(it.unit)}</td><td>${pct(it.down)}</td><td>${pct(it.up)}</td><td>${signed(it.elasticity)}</td>` +
      `<td>${it.marginal == null ? "—" : signed(it.marginal, 4)}</td><td>${range(it)}</td>` +
      `<td>${[it.valid_down.change != null ? `abaixo: ${esc(it.valid_down.what)}` : "", it.valid_up.change != null ? `acima: ${esc(it.valid_up.what)}` : ""].filter(Boolean).join("; ") || "nada na faixa de ±30%"}</td></tr>`).join("");
    const curve = item.curve.map((p) => `<tr><td>${level(p.percent)}</td><td>${val(p.value)}</td><td>${p.feasible ? num(p.cost, 4) : "inviável"}</td>` +
      `<td>${p.feasible ? num(p.iofc, 4) : "—"}</td><td>${esc(swap(item, p))}</td></tr>`).join("");
    document.getElementById("sens-table").innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>` +
      `<h4>Curva de ${esc(item.label.toLowerCase())}</h4><table><thead><tr><th>Variação</th><th>Valor (${esc(item.unit)})</th><th>Custo ($/dia)</th><th>IOFC ($/dia)</th><th>Alimentos em relação à ração atual</th></tr></thead><tbody>${curve}</tbody></table>`;
  }

  const x0of = (it) => Math.min(...it.curve.map((p) => p.percent));
  const x1of = (it) => Math.max(...it.curve.map((p) => p.percent));

  function draw() {
    const b = base(item);
    document.getElementById("curve-title").textContent = `Curva: ${item.label}`;
    const parts = [`Atual: ${val(b.value)} ${item.unit}. A ração mantém os mesmos alimentos ${range(item)}` +
      (item.valid_down.change != null || item.valid_up.change != null
        ? ` (${val(b.value * (1 + Math.max(x0of(item), item.valid_down.same) / 100))} a ${val(b.value * (1 + Math.min(x1of(item), item.valid_up.same) / 100))} ${item.unit}).` : ".")];
    if (item.valid_up.change != null) parts.push(`Acima de ${signed(item.valid_up.same, 1)}%: ${item.valid_up.what}.`);
    if (item.valid_down.change != null) parts.push(`Abaixo de ${signed(item.valid_down.same, 1)}%: ${item.valid_down.what}.`);
    document.getElementById("curve-sub").textContent = parts.join(" ");
    drawTornado();
    drawCurve();
    drawStack();
    drawDetail();
    drawTable();
  }

  draw();
  document.getElementById("sensitivity").scrollIntoView({ behavior: "smooth", block: "start" });
})();
