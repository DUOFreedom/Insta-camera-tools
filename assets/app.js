/* =============================================================================
   影石相机工具 · 文档站交互
   1) 深浅色切换（localStorage 记忆，首屏由 head 内联脚本先行应用，避免闪白）
   2) 移动端抽屉导航
   3) 文档搜索（读取 assets/search-index.json，纯前端过滤）
   4) 右侧目录生成 + 滚动高亮
   无外部依赖，不发起除索引文件以外的任何请求。
   ============================================================================= */
(function () {
  "use strict";

  var THEME_KEY = "instatools-theme";
  var root = document.documentElement;

  /* ---------------------------------------------------------------- 1. 主题 */
  function currentTheme() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    var btn = document.querySelector(".vp-appearance");
    if (btn) btn.setAttribute("aria-checked", theme === "dark" ? "true" : "false");
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", theme === "dark" ? "#1b1b1f" : "#ffffff");
  }

  function initTheme() {
    var saved = null;
    try {
      saved = window.localStorage.getItem(THEME_KEY);
    } catch (e) {}
    if (saved !== "dark" && saved !== "light") {
      saved = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }
    applyTheme(saved);
  }

  initTheme();

  document.addEventListener("click", function (event) {
    var sw = event.target.closest(".vp-appearance");
    if (!sw) return;
    var next = currentTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    try {
      window.localStorage.setItem(THEME_KEY, next);
    } catch (e) {}
  });

  /* -------------------------------------------------------------- 2. 抽屉 */
  var hamburger = document.querySelector(".vp-hamburger");
  var drawer = document.querySelector(".vp-drawer");

  function setDrawer(open) {
    if (!hamburger || !drawer) return;
    hamburger.setAttribute("aria-expanded", open ? "true" : "false");
    hamburger.setAttribute("aria-label", open ? "关闭导航菜单" : "打开导航菜单");
    if (open) drawer.setAttribute("open", "");
    else drawer.removeAttribute("open");
  }

  if (hamburger && drawer) {
    hamburger.addEventListener("click", function () {
      setDrawer(hamburger.getAttribute("aria-expanded") !== "true");
    });
    drawer.addEventListener("click", function (event) {
      if (event.target.closest("a")) setDrawer(false);
    });
    // 点抽屉外面或按 Esc 收起：遮罩是 CSS 画的，接不到点击，只能在文档层判断。
    document.addEventListener("click", function (event) {
      if (drawer.getAttribute("open") === null) return;
      if (drawer.contains(event.target) || hamburger.contains(event.target)) return;
      setDrawer(false);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && drawer.getAttribute("open") !== null) {
        setDrawer(false);
        hamburger.focus();
      }
    });
  }

  /* -------------------------------------------------------------- 3. 搜索 */
  var trigger = document.querySelector(".vp-search");
  var modal = document.querySelector(".vp-search-modal");
  var input = modal && modal.querySelector("input");
  var results = modal && modal.querySelector(".vp-search__results");
  var indexData = null;
  var indexLoading = false;
  var activeIndex = -1;

  function indexUrl() {
    var tag = document.querySelector('script[data-search-index]');
    return tag ? tag.getAttribute("data-search-index") : null;
  }

  // 索引里的 u 是相对站点根的路径（"features/"、"#anchor"），
  // 页面本身可能在子目录里，所以按脚本自身位置算出前缀再拼。
  function searchBase() {
    var url = indexUrl() || "";
    return url.replace(new RegExp("assets/search-index\\.json$"), "");
  }

  function loadIndex(onDone) {
    if (indexData) return onDone(indexData);
    if (indexLoading) return;
    var url = indexUrl();
    if (!url) return;
    indexLoading = true;
    fetch(url)
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (data) {
        indexData = Array.isArray(data) ? data : [];
        indexLoading = false;
        onDone(indexData);
      })
      .catch(function () {
        indexLoading = false;
        indexData = [];
        onDone(indexData);
      });
  }

  function escapeHtml(text) {
    return String(text).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function highlight(text, terms) {
    var out = escapeHtml(text);
    if (!terms.length) return out;
    var pattern = terms.map(function (t) {
      return t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }).join("|");
    return out.replace(new RegExp("(" + pattern + ")", "gi"), "<mark>$1</mark>");
  }

  function render(query) {
    var terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!results) return;
    if (!terms.length) {
      results.innerHTML = '<p class="vp-search__empty">输入关键词，搜索标题与小节名</p>';
      activeIndex = -1;
      return;
    }
    var hits = [];
    (indexData || []).forEach(function (item) {
      var hay = (item.t + " " + item.h + " " + (item.k || "")).toLowerCase();
      var score = 0;
      for (var i = 0; i < terms.length; i++) {
        if (hay.indexOf(terms[i]) === -1) return;
        score += item.t.toLowerCase().indexOf(terms[i]) !== -1 ? 2 : 1;
      }
      hits.push({ item: item, score: score });
    });
    hits.sort(function (a, b) { return b.score - a.score; });
    hits = hits.slice(0, 20);
    if (!hits.length) {
      results.innerHTML = '<p class="vp-search__empty">没有匹配项</p>';
      activeIndex = -1;
      return;
    }
    var html = "";
    var base = searchBase();
    hits.forEach(function (hit, i) {
      var href = base + (hit.item.u || "./");
      html +=
        '<a class="vp-search__hit' + (i === 0 ? " is-active" : "") + '" href="' + href + '">' +
        '<span class="vp-search__hit-title">' + highlight(hit.item.h || hit.item.t, terms) + "</span>" +
        '<span class="vp-search__hit-path">' + escapeHtml(hit.item.p || "") + "</span>" +
        "</a>";
    });
    results.innerHTML = html;
    activeIndex = 0;
  }

  function openSearch() {
    if (!modal) return;
    modal.setAttribute("open", "");
    if (input) {
      input.value = "";
      input.focus();
    }
    loadIndex(function () { render(""); });
  }

  function closeSearch() {
    if (modal) modal.removeAttribute("open");
  }

  if (trigger && modal) {
    trigger.addEventListener("click", openSearch);

    modal.addEventListener("click", function (event) {
      if (event.target === modal) closeSearch();
    });

    if (input) {
      input.addEventListener("input", function () {
        loadIndex(function () { render(input.value); });
      });
    }

    document.addEventListener("keydown", function (event) {
      var isOpen = modal.hasAttribute("open");
      var key = event.key;
      if ((key === "k" || key === "K") && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        if (isOpen) closeSearch();
        else openSearch();
        return;
      }
      if (!isOpen) return;
      if (key === "Escape") {
        closeSearch();
        trigger.focus();
        return;
      }
      if (!results) return;
      var hits = results.querySelectorAll(".vp-search__hit");
      if (!hits.length) return;
      if (key === "ArrowDown" || key === "ArrowUp") {
        event.preventDefault();
        activeIndex = (activeIndex + (key === "ArrowDown" ? 1 : -1) + hits.length) % hits.length;
        for (var i = 0; i < hits.length; i++) hits[i].classList.toggle("is-active", i === activeIndex);
        hits[activeIndex].scrollIntoView({ block: "nearest" });
      } else if (key === "Enter" && hits[activeIndex]) {
        event.preventDefault();
        window.location.href = hits[activeIndex].getAttribute("href");
      }
    });
  }

  /* -------------------------------------------------------------- 4. 目录 */
  var doc = document.querySelector(".vp-doc");
  var tocHolder = document.querySelector(".vp-toc__list");

  function slugify(text) {
    return text
      .trim()
      .toLowerCase()
      .replace(/[\s/]+/g, "-")
      .replace(/[^\w\u4e00-\u9fa5-]/g, "");
  }

  function buildToc() {
    if (!doc || !tocHolder) return [];
    var headings = doc.querySelectorAll("h2, h3");
    var seen = {};
    var items = [];
    Array.prototype.forEach.call(headings, function (h) {
      var title = h.textContent.trim();
      if (!title) return;
      if (!h.id) {
        var base = h.classList.contains("section__title") ? slugify(title) : slugify(title);
        var id = base || "section";
        var n = seen[id] || 0;
        seen[id] = n + 1;
        h.id = n ? id + "-" + (n + 1) : id;
      }
      items.push({ id: h.id, title: title, level: h.tagName === "H3" ? 3 : 2 });
    });
    if (!items.length) {
      var wrap = tocHolder.parentNode;
      if (wrap) wrap.style.display = "none";
      return items;
    }
    var html = "";
    items.forEach(function (item) {
      html +=
        '<li><a class="vp-toc__link' + (item.level === 3 ? " vp-toc__link--h3" : "") +
        '" href="#' + item.id + '">' + escapeHtml(item.title) + "</a></li>";
    });
    tocHolder.innerHTML = html;
    return items;
  }

  var tocItems = buildToc();

  if (tocItems.length) {
    var links = tocHolder.querySelectorAll(".vp-toc__link");
    var byId = {};
    Array.prototype.forEach.call(links, function (link) {
      byId[link.getAttribute("href").slice(1)] = link;
    });
    var ticking = false;

    function updateActive() {
      ticking = false;
      var offset = 120;
      var current = null;
      for (var i = 0; i < tocItems.length; i++) {
        var el = document.getElementById(tocItems[i].id);
        if (!el) continue;
        if (el.getBoundingClientRect().top - offset <= 0) current = tocItems[i].id;
        else break;
      }
      if (!current && tocItems.length) current = tocItems[0].id;
      Array.prototype.forEach.call(links, function (link) {
        link.classList.toggle("is-active", link.getAttribute("href").slice(1) === current);
      });
    }

    window.addEventListener("scroll", function () {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(updateActive);
    }, { passive: true });

    updateActive();
  }

  /* ------------------------------------------------------ 5. FAQ 无障碍同步 */
  Array.prototype.forEach.call(document.querySelectorAll(".faq__item"), function (item) {
    var summary = item.querySelector("summary");
    if (!summary) return;
    summary.setAttribute("aria-expanded", String(item.open));
    item.addEventListener("toggle", function () {
      summary.setAttribute("aria-expanded", String(item.open));
    });
  });

  /* ------------------------------------------------------ 6. 复制 SHA256 */
  Array.prototype.forEach.call(document.querySelectorAll(".copy-btn[data-copy]"), function (btn) {
    var target = document.getElementById(btn.getAttribute("data-copy"));
    var label = document.getElementById(btn.getAttribute("data-label"));
    if (!target) return;
    if (!navigator.clipboard) {
      btn.hidden = true;
      return;
    }
    btn.addEventListener("click", function () {
      navigator.clipboard.writeText(target.textContent.trim()).then(
        function () {
          if (label) {
            label.textContent = "已复制";
            window.setTimeout(function () { label.textContent = "复制"; }, 2000);
          }
        },
        function () {
          if (label) {
            label.textContent = "复制失败";
            window.setTimeout(function () { label.textContent = "复制"; }, 2000);
          }
        }
      );
    });
  });
})();
