(function (global) {
  var network = null;
  var schema = [];
  var enabledTypes = {};
  var parseJson = global.parseJsonResponse;

  function $(id) {
    return document.getElementById(id);
  }

  function relColor(type) {
    for (var i = 0; i < schema.length; i++) {
      if (schema[i].type === type) return schema[i].color;
    }
    return "#6b7280";
  }

  function buildLegend() {
    var box = $("graphLegend");
    if (!box) return;
    var html =
      '<div class="graph-legend-title">关系类型（勾选显示）</div><div class="graph-legend-grid">';
    schema.forEach(function (r) {
      var on = enabledTypes[r.type] !== false;
      html +=
        '<label class="graph-legend-item" style="--rel-color:' +
        r.color +
        '">' +
        '<input type="checkbox" data-rel="' +
        r.type +
        '" ' +
        (on ? "checked" : "") +
        " />" +
        "<span class=\"rel-swatch\"></span>" +
        "<span class=\"rel-name\">" +
        r.label_zh +
        "</span>" +
        '<span class="rel-meta">' +
        r.type +
        (r.count ? " · " + r.count : "") +
        (r.weight != null ? " · w" + r.weight : "") +
        "</span></label>";
    });
    html += "</div>";
    box.innerHTML = html;
    box.querySelectorAll("input[data-rel]").forEach(function (cb) {
      cb.addEventListener("change", function () {
        enabledTypes[cb.getAttribute("data-rel")] = cb.checked;
        loadSubgraph();
      });
    });
  }

  async function loadSchema() {
    try {
      var res = await fetch("/graph/schema");
      var data = parseJson ? await parseJson(res) : await res.json();
      schema = data.relations || [];
      schema.forEach(function (r) {
        if (enabledTypes[r.type] === undefined) enabledTypes[r.type] = true;
      });
      buildLegend();
    } catch (e) {
      console.warn("graph schema", e);
    }
  }

  function selectedRelationTypes() {
    var types = [];
    Object.keys(enabledTypes).forEach(function (t) {
      if (enabledTypes[t]) types.push(t);
    });
    return types;
  }

  async function loadSubgraph() {
    var meta = $("graphMeta");
    var center = ($("graphCenterId") && $("graphCenterId").value.trim()) || "";
    var hops = parseInt(($("graphHops") && $("graphHops").value) || "2", 10);
    var maxNodes = parseInt(($("graphMaxNodes") && $("graphMaxNodes").value) || "80", 10);
    var rels = selectedRelationTypes();
    var url =
      "/graph/subgraph?hops=" +
      hops +
      "&max_nodes=" +
      maxNodes +
      "&max_edges=300";
    if (center) url += "&center=" + encodeURIComponent(center);
    if (rels.length && rels.length < schema.length) {
      url += "&relations=" + encodeURIComponent(rels.join(","));
    }
    if (meta) meta.textContent = "加载中…";
    try {
      var res = await fetch(url);
      var data = parseJson ? await parseJson(res) : await res.json();
      if (!res.ok) {
        if (meta) meta.textContent = data.detail || "加载失败";
        return;
      }
      renderNetwork(data);
      if (meta) {
        meta.textContent =
          "节点 " +
          (data.node_count || 0) +
          " · 边 " +
          (data.edge_count || 0) +
          (data.truncated ? " · 已截断（缩小范围或提高上限）" : "") +
          (data.center_id ? " · 中心: " + data.center_id : " · 高度数采样视图");
      }
    } catch (e) {
      if (meta) meta.textContent = "加载失败: " + e.message;
    }
  }

  function renderNetwork(data) {
    var container = $("graphNetwork");
    if (!container || !global.vis) {
      if (container) container.innerHTML = "<p class=\"meta\">无法加载 vis-network</p>";
      return;
    }
    var nodes = new global.vis.DataSet(
      (data.nodes || []).map(function (n) {
        return {
          id: n.id,
          label: n.label,
          title:
            n.name +
            "\n" +
            n.path +
            (n.summary ? "\n" + n.summary : ""),
          color: {
            background: n.is_center ? "#4f8cff" : "#1c2433",
            border: n.is_center ? "#93c5fd" : "#2a3548",
            highlight: { background: "#2d4a7a", border: "#4f8cff" },
          },
          font: { color: "#e8edf5", size: 12 },
          borderWidth: n.is_center ? 3 : 1,
          shape: "dot",
          size: n.is_center ? 22 : 14,
        };
      })
    );
    var edges = new global.vis.DataSet(
      (data.edges || []).map(function (e) {
        var c = relColor(e.type);
        return {
          id: e.id,
          from: e.from,
          to: e.to,
          label: e.label,
          title: e.type + " (w=" + e.weight + ")",
          color: { color: c, highlight: c, opacity: 0.85 },
          font: { color: "#a8b8d0", size: 10, strokeWidth: 0 },
          arrows: e.directed ? { to: { enabled: true, scaleFactor: 0.6 } } : undefined,
          smooth: { type: "continuous" },
          width: 1 + Math.min(3, e.weight || 0),
        };
      })
    );
    var options = {
      nodes: { shape: "dot" },
      edges: { font: { align: "middle" } },
      physics: {
        enabled: true,
        stabilization: { iterations: 120 },
        barnesHut: { gravitationalConstant: -3500, springLength: 120 },
      },
      interaction: {
        hover: true,
        tooltipDelay: 120,
        navigationButtons: true,
        keyboard: true,
      },
      layout: { improvedLayout: true },
    };
    if (!network) {
      network = new global.vis.Network(container, { nodes: nodes, edges: edges }, options);
      network.on("click", function (params) {
        if (params.nodes.length) showNodeDetail(params.nodes[0], data.nodes);
      });
    } else {
      network.setData({ nodes: nodes, edges: edges });
    }
    network.once("stabilizationIterationsDone", function () {
      network.fit({ animation: { duration: 400 } });
    });
  }

  function showNodeDetail(nodeId, nodes) {
    var el = $("graphDetail");
    if (!el) return;
    var n = null;
    (nodes || []).forEach(function (x) {
      if (x.id === nodeId) n = x;
    });
    if (!n) {
      el.innerHTML = "";
      return;
    }
    el.innerHTML =
      "<h4>" +
      escapeHtml(n.name) +
      "</h4>" +
      "<p class=\"meta\">" +
      escapeHtml(n.path) +
      "</p>" +
      "<p>" +
      escapeHtml(n.summary || "") +
      "</p>" +
      '<button type="button" class="btn secondary graph-use-center">设为中心</button> ' +
      '<button type="button" class="btn secondary graph-open-search">检索相关</button>';
    var btnC = el.querySelector(".graph-use-center");
    if (btnC) {
      btnC.addEventListener("click", function () {
        setCenter(n.file_id, n.name);
        loadSubgraph();
      });
    }
    var btnS = el.querySelector(".graph-open-search");
    if (btnS) {
      btnS.addEventListener("click", function () {
        if (global.filekgSetSearchCenter) global.filekgSetSearchCenter(n.file_id, n.name);
      });
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function setCenter(fileId, name) {
    var input = $("graphCenterId");
    if (input) input.value = fileId || "";
    var hint = $("graphCenterHint");
    if (hint) hint.textContent = name ? "当前: " + name : "";
  }

  function bindUi() {
    var btn = $("graphLoadBtn");
    if (btn) btn.addEventListener("click", loadSubgraph);
    var sample = $("graphSampleBtn");
    if (sample) {
      sample.addEventListener("click", function () {
        if ($("graphCenterId")) $("graphCenterId").value = "";
        loadSubgraph();
      });
    }
    ["graphHops", "graphMaxNodes"].forEach(function (id) {
      var el = $(id);
      if (el) el.addEventListener("change", loadSubgraph);
    });
  }

  function onShow() {
    if (!schema.length) loadSchema();
    else loadSubgraph();
  }

  function init() {
    bindUi();
    loadSchema();
  }

  global.FilekgGraph = {
    init: init,
    onShow: onShow,
    setCenter: setCenter,
    load: loadSubgraph,
  };
})(window);
