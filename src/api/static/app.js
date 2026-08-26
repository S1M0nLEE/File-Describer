(function () {
  var navSeedId = null;
  var navRel = null;
  var appConfig = {};

  function $(id) {
    return document.getElementById(id);
  }

  async function parseJsonResponse(res) {
    var text = await res.text();
    if (!text) return {};
    try {
      return JSON.parse(text);
    } catch (e) {
      return { detail: text };
    }
  }

  function formatApiError(data) {
    if (!data) return "失败";
    if (typeof data.detail === "string") return data.detail;
    if (data.code === "graph_not_loaded") return "请先在弹窗中加载全局索引";
    if (data.detail && typeof data.detail === "object") {
      return data.detail.message || data.detail.detail || "请先加载全局索引";
    }
    return String(data.detail || "失败");
  }

  function showPanel(name) {
    document.querySelectorAll(".panel").forEach(function (p) {
      p.classList.toggle("active", p.dataset.panel === name);
    });
    document.querySelectorAll(".nav-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.tab === name);
    });
    if (name === "visual") {
      loadRelationBars();
    }
    if (name === "system") {
      loadDiagnostics();
      loadFeatureGrid();
    }
    if (name === "rag") {
      loadRagStatus();
      loadRagTopKPref();
    }
    if (name === "index" || name === "rag") {
      loadIndexMultimodalPref();
    }
    if (name === "graph" && window.FilekgGraph) {
      window.FilekgGraph.onShow();
    }
  }

  function clearNav() {
    navSeedId = null;
    navRel = null;
    $("relationFilter").value = "";
    $("centerBanner").style.display = "none";
  }

  function setLog(el, text, isError) {
    el.textContent = text;
    el.style.color = isError ? "#f87171" : "#a8b8d0";
  }

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function confClass(level) {
    if (!level) return "";
    var l = String(level).toUpperCase();
    if (l === "HIGH") return "conf-high";
    if (l === "MED") return "conf-med";
    return "conf-low";
  }

  function relBadge(rel) {
    if (rel === "VISUALLY_SIMILAR_TO") return "tag tag-visual";
    if (rel === "NEAR_DUPLICATE") return "tag tag-dup";
    return "tag";
  }

  function formatExplain(ep) {
    var parts = [ep.rel_label || ep.rel_type || "关系"];
    if (ep.confidence) parts.push(ep.confidence);
    if (ep.relation_subtype) parts.push(ep.relation_subtype);
    var scores = [];
    if (ep.s_visual != null) scores.push("视觉 " + ep.s_visual);
    if (ep.s_text != null) scores.push("文本 " + ep.s_text);
    if (ep.s_doc != null) scores.push("文档 " + ep.s_doc);
    var extra = scores.length ? " · " + scores.join(" | ") : "";
    return parts.join(" · ") + extra;
  }

  var loadPollTimer = null;
  var graphReady = false;

  function loadingLabel(health) {
    if (!health) return "连接中…";
    if (health.error) return "加载失败";
    var lp = health.load || {};
    if (lp.state === "running" || health.load_running) return "加载中…";
    if (health.manual_load && !health.graph_ready) return "未加载索引";
    if (health.loading || health.phase === "graph") return "加载索引…";
    if (health.phase === "search") return "初始化检索…";
    if (!health.search_ready && health.graph_ready) return "图已就绪";
    return "就绪";
  }

  function showLoadOverlay(show) {
    var el = $("loadOverlay");
    if (!el) return;
    el.classList.toggle("hidden", !show);
    el.setAttribute("aria-hidden", show ? "false" : "true");
  }

  function updateLoadProgress(data) {
    var wrap = $("loadProgressWrap");
    var fill = $("loadProgressFill");
    var pct = $("loadProgressPct");
    var txt = $("loadProgressText");
    var err = $("loadError");
    var actions = $("loadActions");
    if (!wrap) return;
    var percent = data.percent != null ? data.percent : 0;
    var running = data.state === "running" || data.load_running;
    if (running || data.state === "done") {
      wrap.classList.remove("hidden");
      if (actions) actions.classList.add("hidden");
    }
    if (fill) fill.style.width = percent + "%";
    if (pct) pct.textContent = percent + "%";
    if (txt) {
      var extra = "";
      if (data.total > 0) {
        extra = " (" + data.current + "/" + data.total + ")";
      }
      txt.textContent = (data.message || "") + extra;
    }
    if (err) {
      if (data.state === "error") {
        err.textContent = data.message || "加载失败";
        err.classList.remove("hidden");
      } else {
        err.classList.add("hidden");
      }
    }
  }

  async function pollLoadStatus() {
    try {
      var data = await fetch("/load/status").then(function (r) {
        return r.json();
      });
      updateLoadProgress(data);
      graphReady = !!data.graph_ready;
      if (data.state === "running" || data.load_running) {
        return;
      }
      if (loadPollTimer) {
        clearInterval(loadPollTimer);
        loadPollTimer = null;
      }
      if (data.state === "done" || data.graph_ready) {
        showLoadOverlay(false);
        loadHealth();
        return;
      }
      if (data.state === "error") {
        var actions = $("loadActions");
        if (actions) actions.classList.remove("hidden");
      }
    } catch (e) {
      /* ignore */
    }
  }

  function startLoadPoll() {
    if (loadPollTimer) clearInterval(loadPollTimer);
    pollLoadStatus();
    loadPollTimer = setInterval(pollLoadStatus, 400);
  }

  async function startGlobalLoad() {
    var buildCorpus = $("loadBuildCorpus") && $("loadBuildCorpus").checked;
    updateLoadProgress({
      state: "running",
      percent: 0,
      message: "正在请求加载…",
      load_running: true,
    });
    $("loadProgressWrap").classList.remove("hidden");
    $("loadActions").classList.add("hidden");
    try {
      var res = await fetch("/load/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ build_search: true, build_corpus: buildCorpus }),
      });
      var data = await parseJsonResponse(res);
      if (!res.ok) {
        $("loadError").textContent = data.detail || "启动失败";
        $("loadError").classList.remove("hidden");
        $("loadActions").classList.remove("hidden");
        return;
      }
      startLoadPoll();
    } catch (e) {
      $("loadError").textContent = String(e);
      $("loadError").classList.remove("hidden");
      $("loadActions").classList.remove("hidden");
    }
  }

  function bindLoadUi() {
    var startBtn = $("loadStartBtn");
    var laterBtn = $("loadLaterBtn");
    var openBtn = $("openLoadBtn");
    if (startBtn) startBtn.addEventListener("click", startGlobalLoad);
    if (laterBtn) {
      laterBtn.addEventListener("click", function () {
        sessionStorage.setItem("filekg_load_dismissed", "1");
        showLoadOverlay(false);
        loadHealth();
      });
    }
    if (openBtn) {
      openBtn.addEventListener("click", function () {
        sessionStorage.removeItem("filekg_load_dismissed");
        showLoadOverlay(true);
        $("loadActions").classList.remove("hidden");
        $("loadProgressWrap").classList.add("hidden");
        $("loadError").classList.add("hidden");
      });
    }
  }

  function maybeShowLoadPrompt(health) {
    if (!health || !health.manual_load) return;
    graphReady = !!health.graph_ready;
    if (health.graph_ready) {
      showLoadOverlay(false);
      return;
    }
    if (health.load_running || (health.load && health.load.state === "running")) {
      showLoadOverlay(true);
      startLoadPoll();
      return;
    }
    if (sessionStorage.getItem("filekg_load_dismissed") === "1") {
      showLoadOverlay(false);
      return;
    }
    showLoadOverlay(true);
  }

  function requireGraphReady() {
    if (graphReady) return true;
    if (appConfig.manual_load) {
      showLoadOverlay(true);
    }
    return false;
  }

  async function loadHealth() {
    var pill = $("statusPill");
    try {
      var health = await fetch("/health").then(function (r) {
        return r.json();
      });
      var cfg = await fetch("/config")
        .then(function (r) {
          return r.ok ? r.json() : {};
        })
        .catch(function () {
          return {};
        });
      appConfig = cfg;

      graphReady = !!health.search_ready || !!health.graph_ready;
      maybeShowLoadPrompt(health);

      var lp = health.load || {};
      var stillLoading =
        health.load_running ||
        lp.state === "running" ||
        ((health.loading || health.phase === "graph" || health.phase === "search") &&
          !health.manual_load);

      if (stillLoading) {
        pill.className = "status-pill loading";
        if (lp.state === "running" || health.load_running) {
          updateLoadProgress(
            Object.assign({ load_running: true }, lp, {
              graph_ready: health.graph_ready,
            })
          );
        }
        pill.innerHTML =
          '<span class="dot"></span>' +
          esc(loadingLabel(health)) +
          (lp.message
            ? "<br><small>" + esc(lp.message) + "</small>"
            : health.phase
              ? "<br><small>" + esc(health.phase) + "</small>"
              : "");
        return;
      }

      if (health.error) {
        pill.className = "status-pill";
        pill.innerHTML =
          '<span class="dot"></span>错误<br><small>' + esc(health.error) + "</small>";
        return;
      }

      var stats = {};
      if (health.graph_ready) {
        stats = await fetch("/stats")
          .then(function (r) {
            return r.ok ? r.json() : {};
          })
          .catch(function () {
            return {};
          });
      }

      var openBtn = $("openLoadBtn");
      if (openBtn) {
        openBtn.style.display = health.graph_ready ? "none" : "block";
      }

      pill.className = "status-pill ok";
      var lines = [
        '<span class="dot"></span>' + esc(loadingLabel(health)),
        stats.local_file_count != null
          ? stats.local_file_count + " 本机"
          : stats.file_count != null
            ? stats.file_count + " 文件"
            : "",
        stats.benchmark_file_count != null && stats.benchmark_file_count > 0
          ? stats.benchmark_file_count + " 评测样例"
          : "",
        health.embedding_backend || "",
      ];
      if (stats.visual_edges != null && stats.visual_edges > 0) {
        lines.push("视觉边 " + stats.visual_edges);
      }
      if (stats.near_duplicate_edges != null && stats.near_duplicate_edges > 0) {
        lines.push("近重复 " + stats.near_duplicate_edges);
      }
      if (cfg.multimodal_enabled) lines.push("多模态开");
      if (cfg.visual_enabled) lines.push("视觉融合");
      if (health.visual_encoder_ready) lines.push("CLIP✓");
      if (health.disk_cache) lines.push("磁盘缓存");
      if (health.heartbeat_running) lines.push("同步中…");
      else if (health.last_heartbeat_at) {
        var hb = health.last_heartbeat_at.slice(0, 19).replace("T", " ");
        lines.push("心跳 " + hb);
      }
      pill.innerHTML = lines.filter(Boolean).join("<br>");
    } catch (e) {
      pill.className = "status-pill";
      pill.innerHTML = '<span class="dot"></span>未连接';
    }
  }

  function startHealthPoll() {
    loadHealth();
    setInterval(loadHealth, 2500);
  }

  async function loadSampleQueries() {
    var box = $("sampleQueries");
    if (!box) return;
    try {
      var data = await fetch("/visual/sample-queries").then(function (r) {
        return r.json();
      });
      box.innerHTML = "";
      (data.queries || []).slice(0, 8).forEach(function (item) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "chip";
        b.textContent = item.text.length > 28 ? item.text.slice(0, 28) + "…" : item.text;
        b.title = item.text;
        b.addEventListener("click", function () {
          $("q").value = item.text;
          doSearch();
        });
        box.appendChild(b);
      });
    } catch (e) {
      box.innerHTML = "";
    }
  }

  async function doSearch() {
    var q = $("q").value.trim();
    if (!q) return;
    if (!requireGraphReady()) {
      $("meta").textContent = "请先加载全局索引";
      return;
    }
    $("meta").textContent = "检索中（首次可能需加载模型）…";
    $("results").innerHTML = "";
    $("edges").innerHTML = "";

    var expand = $("expandGraph").checked;
    var visualOnly = $("visualOnly").checked;
    var relFilter = $("relationFilter").value;

    var url =
      "/search?q=" +
      encodeURIComponent(q) +
      "&expand=" +
      (expand ? "true" : "false") +
      "&visual_only=" +
      (visualOnly ? "true" : "false");
    if (navSeedId) {
      url += "&seed_file_id=" + encodeURIComponent(navSeedId);
      var useRel = navRel || relFilter;
      if (useRel) url += "&relation=" + encodeURIComponent(useRel);
    }

    try {
      var res = await fetch(url);
      var data = await parseJsonResponse(res);
      if (!res.ok) {
        $("meta").textContent = data.detail || "检索失败";
        return;
      }
      var p = data.parsed || {};
      var flags = [];
      if (visualOnly) flags.push("仅视觉边");
      if (!expand) flags.push("无图扩展");
      $("meta").textContent =
        "关键词: " +
        (p.keywords || q) +
        " | 类型: " +
        ((p.extensions || []).join(", ") || "无") +
        " | 种子 " +
        (data.seed_count || 0) +
        " | 结果 " +
        (data.results || []).length +
        (flags.length ? " | " + flags.join(" · ") : "");

      var container = $("results");
      (data.results || []).forEach(function (r, i) {
        var hasVisual = (r.explanation_paths || []).some(function (ep) {
          return (
            ep.rel_type === "VISUALLY_SIMILAR_TO" || ep.rel_type === "NEAR_DUPLICATE"
          );
        });
        var div = document.createElement("div");
        div.className =
          "card" +
          (r.is_seed ? " seed" : "") +
          (hasVisual ? " card-visual" : "");

        var explain = "";
        if (r.explanation) {
          explain +=
            '<div class="explain explain-native">' +
            esc(r.explanation) +
            (r.fidelity != null
              ? ' <span class="tag">保真度 ' + esc(String(r.fidelity)) + "</span>"
              : "") +
            "</div>";
        }
        (r.explanation_paths || []).forEach(function (ep) {
          var rel = ep.rel_type || "";
          var cc = confClass(ep.confidence);
          explain +=
            '<div class="explain ' +
            cc +
            '"><span class="' +
            relBadge(rel) +
            '">' +
            esc(rel.replace(/_/g, " ")) +
            "</span> " +
            esc(formatExplain(ep)) +
            "（" +
            esc(ep.from_name || "种子") +
            '）<button type="button" class="btn secondary nav-rel" data-fid="' +
            esc(r.file_id) +
            '" data-rel="' +
            esc(rel) +
            '">沿此关系</button></div>';
        });

        var tags = "";
        if (r.is_seed) tags += '<span class="tag">种子</span>';
        if (r.bm25_score) tags += '<span class="tag">BM25</span>';
        if (hasVisual) tags += '<span class="tag tag-visual">视觉路径</span>';

        div.innerHTML =
          '<div class="name">' +
          tags +
          (i + 1) +
          ". " +
          esc(r.name) +
          "</div>" +
          '<div class="path">' +
          esc(r.path) +
          "</div>" +
          '<div class="scores">综合 ' +
          r.score +
          " | 语义 " +
          (r.semantic_score ?? "-") +
          " | 图 " +
          (r.graph_weight ?? "-") +
          (r.bm25_score ? " | BM25 " + r.bm25_score : "") +
          "</div>" +
          '<div class="summary">' +
          esc(r.summary || "") +
          "</div>" +
          explain +
          '<div class="card-actions">' +
          '<button type="button" class="btn secondary" data-nav="' +
          esc(r.file_id) +
          '">以此为中心</button>' +
          '<button type="button" class="btn secondary" data-neighbors="' +
          esc(r.file_id) +
          '">查看邻居</button>' +
          '<button type="button" class="btn secondary" data-graph="' +
          esc(r.file_id) +
          '" data-graph-name="' +
          esc(r.name || "") +
          '">图谱视图</button></div>';
        container.appendChild(div);
      });
      bindSearchActions(container);

      (data.graph_edges || []).forEach(function (e) {
        var d = document.createElement("div");
        d.className = "edge";
        d.textContent = e.source + " —[" + e.relation + "]→ " + e.target;
        $("edges").appendChild(d);
      });
    } catch (e) {
      $("meta").textContent = "请求失败: " + e.message;
    }
  }

  function bindSearchActions(container) {
    container.querySelectorAll(".nav-rel").forEach(function (btn) {
      btn.addEventListener("click", function () {
        navSeedId = btn.getAttribute("data-fid");
        navRel = btn.getAttribute("data-rel") || null;
        $("centerBanner").style.display = "block";
        $("centerBanner").textContent =
          "导航：种子 + 关系 " + (navRel || "");
        doSearch();
      });
    });
    container.querySelectorAll("[data-nav]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        navSeedId = btn.getAttribute("data-nav");
        navRel = null;
        $("centerBanner").style.display = "block";
        $("centerBanner").textContent = "导航：以选中文件为种子";
        doSearch();
      });
    });
    container.querySelectorAll("[data-graph]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var fid = btn.getAttribute("data-graph");
        var name = btn.getAttribute("data-graph-name") || "";
        if (window.FilekgGraph) {
          window.FilekgGraph.setCenter(fid, name);
          showPanel("graph");
        }
      });
    });
    container.querySelectorAll("[data-neighbors]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var fid = btn.getAttribute("data-neighbors");
        $("navFileId").value = fid;
        showPanel("visual");
        loadNeighbors(fid, "VISUALLY_SIMILAR_TO,NEAR_DUPLICATE");
      });
    });
  }

  async function loadNeighbors(fileId, relation) {
    if (!fileId) return;
    $("navNeighbors").innerHTML = '<p class="meta">加载中…</p>';
    var url = "/navigate/" + encodeURIComponent(fileId);
    if (relation) url += "?relation=" + encodeURIComponent(relation);
    try {
      var data = await fetch(url).then(function (r) {
        return r.json();
      });
      var center = data.center || {};
      $("navCenter").innerHTML =
        "<strong>" +
        esc(center.name || fileId) +
        '</strong><br><span class="path">' +
        esc(center.path || "") +
        "</span>";
      var grid = $("navNeighbors");
      grid.innerHTML = "";
      var list = data.neighbors || [];
      if (!list.length) {
        grid.innerHTML = '<p class="meta">无邻居（请先索引并建立视觉关系）</p>';
        return;
      }
      list.forEach(function (nb) {
        var card = document.createElement("div");
        card.className = "neighbor-card " + relBadge(nb.rel_type).replace("tag ", "");
        var props = nb.props || {};
        var conf = props.confidence || "";
        card.innerHTML =
          '<div class="nb-rel ' +
          relBadge(nb.rel_type) +
          '">' +
          esc(nb.rel_type || "") +
          "</div>" +
          (conf
            ? '<span class="conf-pill ' + confClass(conf) + '">' + esc(conf) + "</span>"
            : "") +
          '<div class="nb-name">' +
          esc(nb.name) +
          "</div>" +
          '<div class="path">' +
          esc(nb.path) +
          "</div>" +
          (props.relation_subtype
            ? '<div class="nb-meta">' + esc(props.relation_subtype) + "</div>"
            : "") +
          (props.s_visual != null
            ? '<div class="nb-meta">s_visual ' + props.s_visual + "</div>"
            : "") +
          '<button type="button" class="btn secondary" data-goto="' +
          esc(nb.file_id) +
          '">设为种子检索</button>';
        card.querySelector("[data-goto]").addEventListener("click", function () {
          navSeedId = nb.file_id;
          navRel = nb.rel_type;
          showPanel("search");
          $("centerBanner").style.display = "block";
          $("centerBanner").textContent = "从邻居 " + nb.name + " 出发";
          doSearch();
        });
        grid.appendChild(card);
      });
    } catch (e) {
      $("navNeighbors").innerHTML = '<p class="meta">失败: ' + esc(e.message) + "</p>";
    }
  }

  async function loadRelationBars() {
    var el = $("relationBars");
    if (!el) return;
    try {
      var data = await fetch("/graph/relations").then(function (r) {
        return r.json();
      });
      var rel = data.relations || {};
      var total = data.total_edges || 1;
      var sorted = Object.keys(rel).sort(function (a, b) {
        return rel[b] - rel[a];
      });
      el.innerHTML = "";
      sorted.forEach(function (type) {
        var n = rel[type];
        var row = document.createElement("div");
        row.className = "rel-bar-row";
        var pct = Math.round((100 * n) / total);
        var highlight =
          type === "VISUALLY_SIMILAR_TO" || type === "NEAR_DUPLICATE" ? " highlight" : "";
        row.innerHTML =
          '<span class="rel-label' +
          highlight +
          '">' +
          esc(type) +
          '</span><div class="rel-bar"><div class="rel-fill' +
          highlight +
          '" style="width:' +
          pct +
          '%"></div></div><span class="rel-count">' +
          n +
          "</span>";
        el.appendChild(row);
      });
      if (!sorted.length) el.innerHTML = '<p class="meta">暂无关系边，请先索引目录</p>';
    } catch (e) {
      el.innerHTML = '<p class="meta">无法加载</p>';
    }
  }

  async function loadDiagnostics() {
    var grid = $("diagnosticsGrid");
    var banner = $("diagnosticsBanner");
    if (!grid) return;
    try {
      var diag = await fetch("/health/diagnostics?probe_network=true").then(function (r) {
        return r.json();
      });
      if (banner) {
        if (!diag.ok) {
          banner.className = "diag-banner diag-error";
          banner.textContent =
            "存在关键问题，检索质量可能不可用。请查看下方自检项并参考 docs/TROUBLESHOOTING.md。";
          banner.classList.remove("hidden");
        } else if (diag.warnings) {
          banner.className = "diag-banner diag-warn";
          banner.textContent = "系统可运行，但尚未建立索引或存在警告项。可先索引示例数据。";
          banner.classList.remove("hidden");
        } else {
          banner.className = "diag-banner hidden";
          banner.textContent = "";
        }
      }
      grid.innerHTML = (diag.checks || [])
        .map(function (c) {
          var cls = c.ok ? "diag-ok" : c.severity === "critical" ? "diag-critical" : "diag-warn";
          return (
            '<div class="feature-item ' +
            cls +
            '"><span>' +
            esc(c.id) +
            '</span><strong title="' +
            esc(c.hint || "") +
            '">' +
            esc(c.detail) +
            "</strong></div>"
          );
        })
        .join("");
    } catch (e) {
      grid.innerHTML =
        '<div class="feature-item diag-warn"><span>diagnostics</span><strong>无法加载</strong></div>';
    }
  }

  async function loadFeatureGrid() {
    var el = $("featureGrid");
    if (!el) return;
    try {
      var cfg = await fetch("/config").then(function (r) {
        return r.json();
      });
      appConfig = cfg;
      var items = [
        ["视觉融合", cfg.visual_enabled ? "开启" : "关闭"],
        ["融合模式", cfg.visual_fusion_mode || "-"],
        ["多模态索引", cfg.multimodal_enabled ? "开启" : "关闭"],
        ["moondream 描述", cfg.multimodal_vision_caption ? "开启" : "关闭"],
        ["专利视觉专例", cfg.patent_visual_only ? "是（无 WORKFLOW）" : "否"],
        ["近重复合并展示", cfg.merge_near_duplicate_results ? "是" : "否"],
        ["图扩展跳数", cfg.graph_hops],
      ];
      el.innerHTML = items
        .map(function (pair) {
          return (
            '<div class="feature-item"><span>' +
            esc(pair[0]) +
            '</span><strong>' +
            esc(pair[1]) +
            "</strong></div>"
          );
        })
        .join("");
    } catch (e) {
      el.innerHTML = "";
    }
  }

  function renderIndexStats(data) {
    var el = $("indexStats");
    if (!el || !data) return;
    var rel = data.relation_stats || {};
    var vf = rel.visual_fusion != null ? rel.visual_fusion : rel.visual_similar;
    var html = '<div class="stat-cards">';
    html +=
      '<div class="stat-card"><b>' +
      (data.file_count || 0) +
      "</b><span>文件</span></div>";
    if (vf != null)
      html += '<div class="stat-card accent"><b>' + vf + '</b><span>视觉融合边</span></div>';
    var keys = Object.keys(rel).filter(function (k) {
      return k !== "visual_fusion" && k !== "visual_similar";
    });
    keys.slice(0, 4).forEach(function (k) {
      html +=
        '<div class="stat-card"><b>' +
        rel[k] +
        "</b><span>" +
        esc(k) +
        "</span></div>";
    });
    html += "</div>";
    el.innerHTML = html;
  }

  async function doIndex() {
    var path = $("indexPath").value.trim();
    if (!path) {
      setLog($("indexLog"), "请填写目录", true);
      return;
    }
    var btn = $("indexBtn");
    btn.disabled = true;
    $("indexStats").innerHTML = "";
    var mmOn = isIndexMultimodalEnabled();
    setLog(
      $("indexLog"),
      mmOn ? "索引中（多模态已开，媒体描述较慢）…" : "索引中（快速文本模式）…"
    );
    var body = {
      path: path,
      clear: $("indexClear").checked,
      multimodal: isIndexMultimodalEnabled(),
    };
    var max = parseInt($("indexMax").value, 10);
    if (max > 0) body.max_files = max;
    try {
      var res = await fetch("/index", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      var data = await parseJsonResponse(res);
      if (!res.ok) setLog($("indexLog"), data.detail || JSON.stringify(data), true);
      else {
        renderIndexStats(data);
        setLog($("indexLog"), JSON.stringify(data, null, 2));
        loadHealth();
        loadFiles();
        loadRelationBars();
      }
    } catch (e) {
      setLog($("indexLog"), e.message, true);
    } finally {
      btn.disabled = false;
    }
  }

  async function loadFiles() {
    if (!requireGraphReady()) {
      $("fileMeta").textContent = "请先加载全局索引";
      return;
    }
    var filter = ($("fileFilter") && $("fileFilter").value.trim()) || "";
    var extF = ($("fileExtFilter") && $("fileExtFilter").value) || "";
    var scope = ($("fileScope") && $("fileScope").value) || "local";
    var url = "/files?limit=300&scope=" + encodeURIComponent(scope);
    if (filter) url += "&q=" + encodeURIComponent(filter);
    $("fileMeta").textContent = "加载中…";
    $("fileTableBody").innerHTML = "";
    try {
      var res = await fetch(url);
      var data = await res.json();
      if (!res.ok) {
        $("fileMeta").textContent = formatApiError(data);
        return;
      }
      var files = data.files || [];
      if (extF) {
        files = files.filter(function (f) {
          return (f.name || "").toLowerCase().endsWith(extF);
        });
      }
      var scopeLabel =
        scope === "benchmark"
          ? "评测数据集"
          : scope === "all"
            ? "全部"
            : "本机索引";
      $("fileMeta").textContent =
        scopeLabel +
        " 共 " +
        data.total +
        " · 显示 " +
        files.length +
        (extF ? "（已筛 " + extF + "）" : "");
      var tbody = $("fileTableBody");
      files.forEach(function (f) {
        var tr = document.createElement("tr");
        tr.className = "clickable";
        var ext = (f.name || "").split(".").pop().toLowerCase();
        var icon = [".png", ".jpg", ".jpeg", ".gif", ".webp"].some(function (e) {
          return (f.name || "").toLowerCase().endsWith(e);
        })
          ? "🖼"
          : (f.name || "").toLowerCase().endsWith(".pdf")
            ? "📄"
            : "";
        tr.innerHTML =
          "<td>" +
          icon +
          " " +
          esc(f.name) +
          "</td><td>" +
          esc(f.path) +
          '</td><td style="color:var(--muted)">' +
          esc(f.status || "") +
          '</td><td><button type="button" class="btn secondary btn-xs" data-nb="' +
          esc(f.file_id) +
          '">邻居</button> <button type="button" class="btn secondary btn-xs" data-gv="' +
          esc(f.file_id) +
          '">图谱</button></td>';
        tr.addEventListener("click", function (ev) {
          if (ev.target.closest("[data-nb]") || ev.target.closest("[data-gv]")) return;
          navSeedId = f.file_id;
          navRel = null;
          $("q").value = f.name || "";
          showPanel("search");
          $("centerBanner").style.display = "block";
          $("centerBanner").textContent = "已选: " + (f.name || f.file_id);
        });
        tr.querySelector("[data-nb]").addEventListener("click", function (ev) {
          ev.stopPropagation();
          $("navFileId").value = f.file_id;
          showPanel("visual");
          loadNeighbors(f.file_id, "VISUALLY_SIMILAR_TO,NEAR_DUPLICATE");
        });
        tr.querySelector("[data-gv]").addEventListener("click", function (ev) {
          ev.stopPropagation();
          if (window.FilekgGraph) {
            window.FilekgGraph.setCenter(f.file_id, f.name);
            showPanel("graph");
          }
        });
        tbody.appendChild(tr);
      });
    } catch (e) {
      $("fileMeta").textContent = e.message;
    }
  }

  async function runAction(url, logEl) {
    setLog(logEl, "执行中…");
    try {
      var res = await fetch(url, { method: "POST" });
      var data = await res.json();
      setLog(logEl, JSON.stringify(data, null, 2), !res.ok);
    } catch (e) {
      setLog(logEl, e.message, true);
    }
  }

  function bindUi() {
    document.querySelectorAll(".nav-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        showPanel(btn.dataset.tab);
        if (btn.dataset.tab === "files") loadFiles();
        if (btn.dataset.tab === "index") {
          var log = $("indexLog");
          if (log && !log.textContent.trim()) {
            log.textContent = "填写目录后点击「开始索引」";
          }
        }
      });
    });

    var el;
    el = $("searchBtn");
    if (el) el.addEventListener("click", doSearch);
    el = $("clearNavBtn");
    if (el) el.addEventListener("click", clearNav);
    el = $("q");
    if (el) {
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter") doSearch();
      });
    }
    el = $("visualOnly");
    if (el) {
      el.addEventListener("change", function () {
        if ($("visualOnly").checked && $("expandGraph")) {
          $("expandGraph").checked = true;
        }
      });
    }
    el = $("indexBtn");
    if (el) el.addEventListener("click", doIndex);
    el = $("fileRefresh");
    if (el) el.addEventListener("click", loadFiles);
    el = $("fileFilter");
    if (el) {
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter") loadFiles();
      });
    }
    el = $("fileExtFilter");
    if (el) el.addEventListener("change", loadFiles);
    el = $("fileScope");
    if (el) el.addEventListener("change", loadFiles);
    el = $("consistencyBtn");
    if (el) {
      el.addEventListener("click", function () {
        runAction("/consistency/check", $("sysLog"));
      });
    }
    el = $("lifecycleBtn");
    if (el) {
      el.addEventListener("click", function () {
        runAction("/lifecycle/run", $("sysLog"));
      });
    }
    el = $("navVisualBtn");
    if (el) {
      el.addEventListener("click", function () {
        loadNeighbors(
          $("navFileId").value.trim(),
          "VISUALLY_SIMILAR_TO,NEAR_DUPLICATE"
        );
      });
    }
    el = $("navAllBtn");
    if (el) {
      el.addEventListener("click", function () {
        loadNeighbors($("navFileId").value.trim(), null);
      });
    }
    el = $("ragSendBtn");
    if (el) el.addEventListener("click", sendRag);
    el = $("ragQuestion");
    if (el) {
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          sendRag();
        }
      });
    }
    el = $("ragStatusBtn");
    if (el) el.addEventListener("click", loadRagStatus);
    el = $("ragIndexBtn");
    if (el) el.addEventListener("click", runRagIndex);
    el = $("ragPreviewBtn");
    if (el) el.addEventListener("click", previewRagRetrieve);
    el = $("ragTopK");
    if (el) {
      el.addEventListener("change", function () {
        setRagTopKInput(getRagTopK());
      });
    }
    bindMultimodalToggles();
  }

  var ragHistory = [];
  var indexMultimodalPref = false;
  var LS_MM_KEY = "filekg_index_multimodal";
  var LS_RAG_TOP_K = "filekg_rag_top_k";
  var ragTopKMax = 50;

  function getRagTopK() {
    var el = $("ragTopK");
    var n = el ? parseInt(el.value, 10) : 10;
    if (isNaN(n) || n < 1) n = 10;
    if (n > ragTopKMax) n = ragTopKMax;
    return n;
  }

  function setRagTopKInput(n) {
    var el = $("ragTopK");
    if (!el) return;
    el.value = String(n);
    el.min = "1";
    el.max = String(ragTopKMax);
    localStorage.setItem(LS_RAG_TOP_K, String(n));
    var hint = $("ragTopKHint");
    if (hint) {
      hint.textContent =
        "将按 Description 检索并排序，取前 " + n + " 个节点送入 DeepSeek";
    }
  }

  function loadRagTopKPref() {
    var saved = localStorage.getItem(LS_RAG_TOP_K);
    if (saved !== null && saved !== "") {
      var n = parseInt(saved, 10);
      if (!isNaN(n) && n >= 1) {
        setRagTopKInput(Math.min(n, ragTopKMax));
        return;
      }
    }
    setRagTopKInput(10);
  }

  function isIndexMultimodalEnabled() {
    var boxes = document.querySelectorAll(".indexMultimodalToggle");
    if (boxes.length) return boxes[0].checked;
    return indexMultimodalPref;
  }

  function syncMultimodalToggles(checked) {
    indexMultimodalPref = !!checked;
    document.querySelectorAll(".indexMultimodalToggle").forEach(function (cb) {
      cb.checked = indexMultimodalPref;
    });
    updateMultimodalHint();
  }

  function updateMultimodalHint() {
    var on = isIndexMultimodalEnabled();
    var text = on
      ? "已开启：将用 moondream / faster-whisper 处理媒体，索引较慢"
      : "已关闭：仅文本 BGE + 快速模式（推荐默认）";
    ["indexMultimodalHint", "ragMultimodalHint"].forEach(function (id) {
      var el = $(id);
      if (el) el.textContent = text;
    });
  }

  async function loadIndexMultimodalPref() {
    var fromLs = localStorage.getItem(LS_MM_KEY);
    if (fromLs === "true" || fromLs === "false") {
      syncMultimodalToggles(fromLs === "true");
      return;
    }
    try {
      var data = await fetch("/settings/index-options").then(function (r) {
        return r.json();
      });
      syncMultimodalToggles(!!data.multimodal);
    } catch (e) {
      syncMultimodalToggles(false);
    }
  }

  async function saveIndexMultimodalPref(checked) {
    syncMultimodalToggles(checked);
    localStorage.setItem(LS_MM_KEY, checked ? "true" : "false");
    try {
      await fetch("/settings/index-options", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ multimodal: checked, persist: true }),
      });
    } catch (e) {
      /* 仅本地偏好亦可 */
    }
  }

  function bindMultimodalToggles() {
    document.querySelectorAll(".indexMultimodalToggle").forEach(function (cb) {
      cb.addEventListener("change", function () {
        saveIndexMultimodalPref(cb.checked);
      });
    });
  }

  function appendRagMsg(role, text, sources) {
    var box = $("ragChat");
    if (!box) return;
    var div = document.createElement("div");
    div.className = "rag-msg " + role;
    div.textContent = text;
    if (sources && sources.length) {
      var s = document.createElement("div");
      s.className = "rag-sources";
      s.textContent =
        "来源: " +
        sources
          .map(function (x) {
            return x.name + " (" + x.path + ")";
          })
          .join(" · ");
      div.appendChild(s);
    }
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  async function loadRagStatus() {
    var meta = $("ragStatusMeta");
    if (!meta) return;
    meta.textContent = "检查中…";
    try {
      var data = await fetch("/rag/status").then(function (r) {
        return r.json();
      });
      if (data.top_k_max != null) ragTopKMax = data.top_k_max;
      if (data.default_top_k != null && localStorage.getItem(LS_RAG_TOP_K) == null) {
        setRagTopKInput(data.default_top_k);
      }
      var topEl = $("ragTopK");
      if (topEl) topEl.max = String(ragTopKMax);
      meta.textContent =
        (data.deepseek_available ? "DeepSeek 已连接" : "DeepSeek 未就绪") +
        " | 已索引 " +
        (data.indexed_files || 0) +
        " 个文件 | 模型 " +
        (data.model || "") +
        " | 默认 Top-K " +
        (data.default_top_k || 10);
    } catch (e) {
      meta.textContent = "状态获取失败";
    }
  }

  async function runRagIndex() {
    var meta = $("ragStatusMeta");
    if (meta) meta.textContent = "本机索引进行中（可能需数小时）…";
    var clear = $("ragIndexClear") && $("ragIndexClear").checked;
    try {
      var mm = isIndexMultimodalEnabled();
      var res = await fetch(
        "/rag/index-local?clear=" +
          (clear ? "true" : "false") +
          "&multimodal=" +
          (mm ? "true" : "false"),
        { method: "POST" }
      );
      var data = await res.json();
      if (meta) meta.textContent = "索引完成: " + (data.roots || []).join(", ");
      loadHealth();
      loadRagStatus();
    } catch (e) {
      if (meta) meta.textContent = "索引失败: " + e.message;
    }
  }

  function renderRagPreview(nodes, topK) {
    var box = $("ragPreview");
    if (!box) return;
    if (!nodes || !nodes.length) {
      box.classList.remove("visible");
      box.innerHTML = "";
      return;
    }
    box.classList.add("visible");
    var html =
      "<div class=\"meta\" style=\"margin-bottom:0.5rem\">预览 Top-" +
      topK +
      " 排序（共 " +
      nodes.length +
      " 条）</div>";
    nodes.forEach(function (n) {
      html +=
        '<div class="rag-preview-item">' +
        "<strong>#" +
        (n.rank != null ? n.rank : "-") +
        "</strong> " +
        esc(n.name) +
        " <span class=\"meta\">score=" +
        (n.score != null ? n.score : "-") +
        " sim=" +
        (n.similarity != null ? n.similarity : "-") +
        "</span><br/><span class=\"meta\">" +
        esc(n.path) +
        "</span></div>";
    });
    box.innerHTML = html;
  }

  async function previewRagRetrieve() {
    var q = $("ragQuestion").value.trim();
    if (!q) {
      setLog($("ragPreview"), "请先输入问题", true);
      return;
    }
    if (!requireGraphReady()) return;
    var topK = getRagTopK();
    var box = $("ragPreview");
    if (box) {
      box.classList.add("visible");
      box.innerHTML = "<span class=\"meta\">检索排序中（Top-" + topK + "）…</span>";
    }
    try {
      var res = await fetch("/rag/retrieve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, top_k: topK }),
      });
      var data = await parseJsonResponse(res);
      if (!res.ok) {
        if (box) box.innerHTML = esc(data.detail || "预览失败");
        return;
      }
      renderRagPreview(data.nodes || [], data.top_k || topK);
    } catch (e) {
      if (box) box.innerHTML = "预览失败: " + esc(e.message);
    }
  }

  async function sendRag() {
    var q = $("ragQuestion").value.trim();
    if (!q) return;
    if (!requireGraphReady()) return;
    var topK = getRagTopK();
    setRagTopKInput(topK);
    $("ragSendBtn").disabled = true;
    appendRagMsg("user", q);
    $("ragQuestion").value = "";
    appendRagMsg("assistant", "思考中…");
    var chat = $("ragChat");
    var pending = chat.lastChild;
    try {
      var res = await fetch("/rag/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q,
          history: ragHistory,
          stream: false,
          top_k: topK,
        }),
      });
      var data = await parseJsonResponse(res);
      if (!res.ok) {
        pending.textContent = data.detail || "请求失败";
      } else if (data.error) {
        pending.textContent = data.error;
      } else {
        pending.textContent = data.answer || "（无回复）";
        if (data.sources && data.sources.length) {
          var s = document.createElement("div");
          s.className = "rag-sources";
          var kUsed = data.top_k != null ? data.top_k : topK;
          s.textContent =
            "检索 Top-" +
            kUsed +
            " · 来源: " +
            data.sources
              .map(function (x) {
                var r = x.rank != null ? "#" + x.rank + " " : "";
                return r + x.name;
              })
              .join(" · ");
          pending.appendChild(s);
        }
        ragHistory.push({ role: "user", content: q });
        ragHistory.push({ role: "assistant", content: data.answer || "" });
      }
    } catch (e) {
      pending.textContent = "请求失败: " + e.message;
    } finally {
      $("ragSendBtn").disabled = false;
      chat.scrollTop = chat.scrollHeight;
    }
  }

  window.parseJsonResponse = parseJsonResponse;
  window.filekgSetSearchCenter = function (fileId, name) {
    navSeedId = fileId;
    navRel = null;
    showPanel("search");
    if ($("centerBanner")) {
      $("centerBanner").style.display = "block";
      $("centerBanner").textContent = "导航：以选中文件为种子" + (name ? " · " + name : "");
    }
    doSearch();
  };

  bindLoadUi();
  bindUi();
  if (window.FilekgGraph) window.FilekgGraph.init();
  showPanel("search");
  startHealthPoll();
  loadSampleQueries();
  loadRagTopKPref();
  loadIndexMultimodalPref();
})();
