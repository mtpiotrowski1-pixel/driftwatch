// Injected into the picker browser. Lets a non-technical user pick element(s)
// to monitor and record click/type steps. Results are pushed to the backend
// through the Playwright-exposed binding `window.__driftwatch_emit`, which
// returns the authoritative {stepCount, selectorCount} so the UI stays correct
// across page navigations (the step list lives on the server, not here).
(function () {
  if (window.__driftwatch_overlay_active) return;
  window.__driftwatch_overlay_active = true;

  var MODE_NAVIGATE = "navigate";
  var MODE_SELECT = "select";
  var MODE_RECORD = "record";
  var initMode = window.__driftwatch_init_mode || MODE_SELECT;
  var currentMode = MODE_NAVIGATE;
  var selectedItems = [];
  var selectedBoxes = [];
  var localStepCount = 0;
  var lastTarget = null;
  var trackedInputs = typeof WeakSet !== "undefined" ? new WeakSet() : null;

  function emit(payload) {
    if (typeof window.__driftwatch_emit !== "function") return Promise.resolve(null);
    try {
      return Promise.resolve(window.__driftwatch_emit(payload));
    } catch (err) {
      return Promise.resolve(null);
    }
  }

  function esc(str) {
    return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(value);
    return String(value).replace(/[^a-zA-Z0-9_-]/g, function (ch) {
      return "\\" + ch;
    });
  }

  function isOverlayElement(target) {
    return (
      target &&
      ((target.id && target.id.indexOf("__driftwatch") === 0) ||
        (bar && bar.contains(target)) ||
        (bottomBar && bottomBar.contains(target)) ||
        (recordBar && recordBar.contains(target)))
    );
  }

  function button(label, title, color) {
    var btn = document.createElement("button");
    btn.textContent = label;
    btn.title = title || "";
    btn.style.cssText =
      "padding:10px 16px;border:none;cursor:pointer;font:13px/1.4 Arial,sans-serif;color:#fff;background:" +
      (color || "transparent") + ";border-radius:0;";
    return btn;
  }

  var styleEl = document.createElement("style");
  styleEl.textContent =
    "@keyframes __dw_blink{0%,100%{opacity:1}50%{opacity:.35}}" +
    "#__driftwatch_bar button:disabled{opacity:.45;cursor:not-allowed}";
  document.head.appendChild(styleEl);

  var bar = document.createElement("div");
  bar.id = "__driftwatch_bar";
  bar.style.cssText =
    "position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#3f6dff;color:#fff;" +
    "display:flex;align-items:center;box-shadow:0 2px 12px rgba(0,0,0,.28);font:13px/1.4 Arial,sans-serif;user-select:none;";

  var btnNav = button("Navigate", "Click around and move between pages normally.");
  var btnSelect = button("Select area", "Click the HTML element(s) you want to monitor.");
  var btnRecord = button("Record clicks", "Click and type. Steps are replayed before each capture.");
  var statusText = document.createElement("span");
  statusText.style.cssText = "flex:1;padding:0 14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
  var btnSave = button("Save", "Save the selected area(s) and recorded steps.", "#38d9a0");
  var btnCancel = button("Cancel", "Close without saving.", "#ff6f91");
  bar.appendChild(btnNav);
  bar.appendChild(btnSelect);
  bar.appendChild(btnRecord);
  bar.appendChild(statusText);
  bar.appendChild(btnSave);
  bar.appendChild(btnCancel);
  document.body.appendChild(bar);

  var bottomBar = document.createElement("div");
  bottomBar.id = "__driftwatch_bottom_bar";
  bottomBar.style.cssText =
    "position:fixed;bottom:0;left:0;right:0;z-index:2147483646;background:#fff;color:#111827;" +
    "padding:14px 22px;box-shadow:0 -4px 18px rgba(0,0,0,.22);border-top:3px solid #3f6dff;" +
    "display:flex;align-items:center;gap:12px;font:13px/1.5 Arial,sans-serif;";
  var bottomText = document.createElement("div");
  bottomText.style.cssText = "flex:1;";
  var bottomHint = document.createElement("div");
  bottomHint.style.cssText = "color:#64748b;font-size:12px;";
  bottomBar.appendChild(bottomText);
  bottomBar.appendChild(bottomHint);
  document.body.appendChild(bottomBar);

  var recordBar = document.createElement("div");
  recordBar.id = "__driftwatch_record_bar";
  recordBar.style.cssText =
    "position:fixed;right:18px;bottom:64px;z-index:2147483646;width:300px;background:#fff;color:#111827;" +
    "padding:14px;border-radius:8px;box-shadow:0 8px 26px rgba(0,0,0,.25);border:1px solid #ffd9a0;display:none;font:13px/1.5 Arial,sans-serif;";
  var recordTitle = document.createElement("div");
  recordTitle.style.cssText = "font-weight:bold;color:#b45309;margin-bottom:6px;";
  recordTitle.innerHTML =
    '<span style="display:inline-block;width:9px;height:9px;background:#ff6f91;border-radius:50%;animation:__dw_blink 1s infinite;margin-right:6px;"></span>Recording clicks';
  var recordInfo = document.createElement("div");
  recordInfo.style.cssText = "color:#475569;font-size:12px;";
  var btnRecordClear = document.createElement("button");
  btnRecordClear.textContent = "Clear steps";
  btnRecordClear.style.cssText =
    "margin-top:10px;padding:8px 10px;border:1px solid #cbd5e1;background:#fff;border-radius:6px;cursor:pointer;";
  recordBar.appendChild(recordTitle);
  recordBar.appendChild(recordInfo);
  recordBar.appendChild(btnRecordClear);
  document.body.appendChild(recordBar);

  var highlight = document.createElement("div");
  highlight.id = "__driftwatch_highlight";
  highlight.style.cssText =
    "position:absolute;pointer-events:none;z-index:2147483644;border:3px solid #3f6dff;background:rgba(63,109,255,.10);border-radius:4px;display:none;";
  document.body.appendChild(highlight);

  function buildSelector(el) {
    if (!el || el === document.documentElement) return "html";
    if (el === document.body) return "body";
    if (el.id && el.id.indexOf("__driftwatch") !== 0) return "#" + cssEscape(el.id);

    var parts = [];
    var current = el;
    while (current && current !== document.body && current !== document.documentElement) {
      var part = current.tagName.toLowerCase();
      if (current.id && current.id.indexOf("__driftwatch") !== 0) {
        parts.unshift("#" + cssEscape(current.id));
        break;
      }
      if (current.className && typeof current.className === "string") {
        var classes = current.className
          .trim()
          .split(/\s+/)
          .filter(function (c) {
            return c && c.indexOf("__driftwatch") !== 0;
          })
          .slice(0, 3);
        if (classes.length) {
          part += classes
            .map(function (c) {
              return "." + cssEscape(c);
            })
            .join("");
        }
      }
      var parent = current.parentElement;
      if (parent) {
        var siblings = Array.prototype.filter.call(parent.children, function (s) {
          return s.tagName === current.tagName;
        });
        if (siblings.length > 1) part += ":nth-of-type(" + (siblings.indexOf(current) + 1) + ")";
      }
      parts.unshift(part);
      current = parent;
    }
    return parts.join(" > ");
  }

  function positionOverlay(box, el) {
    var rect = el.getBoundingClientRect();
    box.style.top = rect.top + window.scrollY + "px";
    box.style.left = rect.left + window.scrollX + "px";
    box.style.width = rect.width + "px";
    box.style.height = rect.height + "px";
    box.style.display = "block";
  }

  function makeSelectedBox(index, el) {
    var box = document.createElement("div");
    box.style.cssText =
      "position:absolute;pointer-events:none;z-index:2147483643;border:3px solid #38d9a0;background:rgba(56,217,160,.12);border-radius:4px;";
    var label = document.createElement("div");
    label.textContent = String(index + 1);
    label.style.cssText =
      "position:absolute;top:-18px;left:-3px;background:#38d9a0;color:#06281d;font:12px/16px Arial,sans-serif;font-weight:bold;min-width:18px;text-align:center;border-radius:4px 4px 0 0;";
    box.appendChild(label);
    document.body.appendChild(box);
    positionOverlay(box, el);
    return box;
  }

  function refreshSelectionUi() {
    btnSave.disabled = selectedItems.length === 0 && localStepCount === 0;
    var selector = selectedItems
      .map(function (item) {
        return item.selector;
      })
      .join(", ");
    if (selectedItems.length === 0) {
      bottomText.innerHTML = "No area selected yet.";
    } else {
      bottomText.innerHTML =
        "Selected <strong>" + selectedItems.length + "</strong>: <code>" + esc(selector) + "</code>";
    }
    bottomHint.textContent = "Select one or more areas, switch mode, or click Save.";
    recordInfo.textContent = localStepCount + " step(s) recorded. Steps are kept across pages.";
  }

  function syncSelection() {
    refreshSelectionUi();
    emit({
      type: "select",
      selectors: selectedItems.map(function (item) {
        return item.selector;
      }),
    });
  }

  function pushStep(step) {
    localStepCount++;
    refreshSelectionUi();
    emit({ type: "step", step: step });
  }

  function flashElement(el) {
    var flash = document.createElement("div");
    flash.style.cssText =
      "position:absolute;pointer-events:none;z-index:2147483642;border:3px solid #ffb454;background:rgba(255,180,84,.18);border-radius:4px;transition:opacity .45s ease;";
    positionOverlay(flash, el);
    document.body.appendChild(flash);
    setTimeout(function () {
      flash.style.opacity = "0";
    }, 250);
    setTimeout(function () {
      if (flash.parentNode) flash.remove();
    }, 800);
  }

  function setMode(mode) {
    currentMode = mode;
    [btnNav, btnSelect, btnRecord].forEach(function (b) {
      b.style.background = "transparent";
      b.style.fontWeight = "normal";
    });
    highlight.style.display = "none";
    document.body.style.cursor = "";
    recordBar.style.display = "none";
    bar.style.background = "#3f6dff";

    if (mode === MODE_NAVIGATE) {
      btnNav.style.background = "#2d50dd";
      btnNav.style.fontWeight = "bold";
      statusText.textContent = "Navigate: click normally. Switch mode any time.";
    } else if (mode === MODE_SELECT) {
      btnSelect.style.background = "#2d50dd";
      btnSelect.style.fontWeight = "bold";
      document.body.style.cursor = "crosshair";
      statusText.textContent = "Select: click one or more HTML elements to monitor.";
    } else if (mode === MODE_RECORD) {
      btnRecord.style.background = "#b45309";
      btnRecord.style.fontWeight = "bold";
      bar.style.background = "#c2410c";
      recordBar.style.display = "block";
      statusText.textContent = "Record: click and type. You can also navigate between pages.";
    }
    refreshSelectionUi();
  }

  function saveAndClose() {
    if (document.activeElement && typeof document.activeElement.blur === "function") {
      document.activeElement.blur();
    }
    setTimeout(function () {
      statusText.textContent = "Saved.";
      bar.style.background = "#38d9a0";
      emit({ type: "save" });
      cleanup();
    }, 80);
  }

  btnNav.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); setMode(MODE_NAVIGATE); }, true);
  btnSelect.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); setMode(MODE_SELECT); }, true);
  btnRecord.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); setMode(MODE_RECORD); }, true);
  btnSave.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); saveAndClose(); }, true);
  btnCancel.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); emit({ type: "cancel" }); cleanup(); }, true);
  btnRecordClear.addEventListener("click", function (e) {
    e.preventDefault();
    e.stopPropagation();
    localStepCount = 0;
    refreshSelectionUi();
    emit({ type: "clear" });
  }, true);

  function onMouseMove(e) {
    if (currentMode !== MODE_SELECT || isOverlayElement(e.target)) return;
    lastTarget = e.target;
    positionOverlay(highlight, lastTarget);
  }

  function onClick(e) {
    if (isOverlayElement(e.target)) return;
    if (currentMode === MODE_SELECT) {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      var target = lastTarget || e.target;
      var selector = buildSelector(target);
      var existingIndex = selectedItems.findIndex(function (item) {
        return item.selector === selector;
      });
      if (existingIndex >= 0) {
        selectedItems.splice(existingIndex, 1);
        var oldBox = selectedBoxes.splice(existingIndex, 1)[0];
        if (oldBox && oldBox.parentNode) oldBox.remove();
        selectedBoxes.forEach(function (box, index) {
          if (box.firstChild) box.firstChild.textContent = String(index + 1);
        });
      } else {
        selectedItems.push({ element: target, selector: selector });
        selectedBoxes.push(makeSelectedBox(selectedItems.length - 1, target));
      }
      syncSelection();
      return;
    }
    if (currentMode === MODE_RECORD) {
      var tag = e.target && e.target.tagName ? e.target.tagName.toLowerCase() : "";
      if (tag === "input" || tag === "textarea" || tag === "select") return;
      pushStep({ type: "click", selector: buildSelector(e.target), delay_ms: 500 });
      flashElement(e.target);
    }
  }

  function onFocusIn(e) {
    if (currentMode !== MODE_RECORD) return;
    var el = e.target;
    if (!el || !el.tagName) return;
    var tag = el.tagName.toLowerCase();
    if (tag !== "input" && tag !== "textarea") return;
    var inputType = (el.type || "").toLowerCase();
    var autocomplete = (el.getAttribute("autocomplete") || "").toLowerCase();
    if (
      tag === "input" &&
      (["submit", "button", "checkbox", "radio", "file", "image", "reset", "hidden", "password"].indexOf(inputType) !== -1 ||
        autocomplete === "current-password" ||
        autocomplete === "new-password")
    )
      return;
    if (trackedInputs && trackedInputs.has(el)) return;
    if (trackedInputs) trackedInputs.add(el);
    var initialValue = el.value || "";
    el.addEventListener("blur", function onBlur() {
      el.removeEventListener("blur", onBlur);
      if (trackedInputs) trackedInputs.delete(el);
      var finalValue = el.value || "";
      if (!finalValue || finalValue === initialValue) return;
      // Values may be credentials even outside password fields. Record only
      // that this selector needs a fill; the app collects the value into its
      // encrypted vault and never returns it through the picker API.
      pushStep({ type: "type", selector: buildSelector(el), delay_ms: 500 });
      flashElement(el);
    });
  }

  function onKeyDown(e) {
    if (e.key === "Escape") {
      emit({ type: "cancel" });
      cleanup();
    }
    if (currentMode === MODE_RECORD && e.key === "Enter") {
      var focused = document.activeElement;
      if (focused && focused.tagName && ["input", "textarea"].indexOf(focused.tagName.toLowerCase()) >= 0) {
        focused.blur();
      }
    }
  }

  function updatePositions() {
    selectedItems.forEach(function (item, index) {
      if (item.element && selectedBoxes[index]) positionOverlay(selectedBoxes[index], item.element);
    });
    if (currentMode === MODE_SELECT && lastTarget) positionOverlay(highlight, lastTarget);
  }

  function cleanup() {
    document.removeEventListener("mousemove", onMouseMove, true);
    document.removeEventListener("click", onClick, true);
    document.removeEventListener("focusin", onFocusIn, true);
    document.removeEventListener("keydown", onKeyDown, true);
    window.removeEventListener("scroll", updatePositions);
    window.removeEventListener("resize", updatePositions);
    [bar, bottomBar, recordBar, highlight, styleEl].forEach(function (el) {
      if (el && el.parentNode) el.remove();
    });
    selectedBoxes.forEach(function (box) {
      if (box && box.parentNode) box.remove();
    });
    document.body.style.cursor = "";
    window.__driftwatch_overlay_active = false;
  }

  document.addEventListener("mousemove", onMouseMove, true);
  document.addEventListener("click", onClick, true);
  document.addEventListener("focusin", onFocusIn, true);
  document.addEventListener("keydown", onKeyDown, true);
  window.addEventListener("scroll", updatePositions);
  window.addEventListener("resize", updatePositions);

  setMode(initMode === MODE_RECORD ? MODE_RECORD : initMode === MODE_NAVIGATE ? MODE_NAVIGATE : MODE_SELECT);
  // Seed the displayed step count from the server (survives navigation).
  emit({ type: "hello" }).then(function (state) {
    if (state && typeof state.stepCount === "number") {
      localStepCount = state.stepCount;
      refreshSelectionUi();
    }
  });
})();
