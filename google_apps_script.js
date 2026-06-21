// PS5 FFPFSC PRO - Community Compatibility Sheet
// Paste into Google Apps Script editor, then Deploy -> Manage deployments -> Edit -> New version -> Deploy.
//
// POST  -> receives a new report from the app
// GET   -> returns all data as JSON for the in-app community list viewer

var SHEET_NAME = "Compatibility";

var STATUS_COLORS = {
  "Working":         { bg: "#14532d", fg: "#4ade80" },
  "Partial":         { bg: "#713f12", fg: "#fbbf24" },
  "Not Working":     { bg: "#450a0a", fg: "#f87171" },
  "Not Tested Yet":  { bg: "#1e293b", fg: "#94a3b8" }
};

// Used ONLY for tie-breaking when two statuses have equal vote counts.
var STATUS_PRIORITY = { "Working": 4, "Partial": 3, "Not Working": 2, "Not Tested Yet": 1 };

// Column definitions. Working/Partial/Not Working/Not Tested Yet store per-status vote counts.
var COLS = [
  "Title ID",
  "Game Title",
  "Status",
  "Original Size",
  "Compressed Size",
  "Storage",
  "ShadowMount Ver.",
  "Notes",
  "Submitted",
  "Reports",
  "Working",
  "Partial",
  "Not Working",
  "Not Tested Yet"
];

function getOrCreateSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    writeHeader(sheet);
  }
  return sheet;
}

function writeHeader(sheet) {
  var hdr = sheet.getRange(1, 1, 1, COLS.length);
  hdr.setValues([COLS]);
  hdr.setBackground("#0f172a");
  hdr.setFontColor("#4ade80");
  hdr.setFontWeight("bold");
  hdr.setFontSize(11);
  sheet.setFrozenRows(1);
  var existing = sheet.getFilter();
  if (existing) existing.remove();
  sheet.getRange(1, 1, 1, COLS.length).createFilter();
}

function colIndex(name) {
  var idx = COLS.indexOf(name);
  if (idx === -1) throw new Error("Unknown column: " + name);
  return idx + 1;
}

function applyRowColor(sheet, row, status) {
  var colors = STATUS_COLORS[status] || STATUS_COLORS["Not Tested Yet"];
  var range = sheet.getRange(row, 1, 1, COLS.length);
  range.setBackground(colors.bg);
  range.setFontColor(colors.fg);
  sheet.getRange(row, colIndex("Status")).setFontWeight("bold");
}

// Highest vote count wins; ties broken by STATUS_PRIORITY.
function consensusStatus(wC, pC, nwC, ntC) {
  var candidates = [
    { s: "Working",        n: wC  },
    { s: "Partial",        n: pC  },
    { s: "Not Working",    n: nwC },
    { s: "Not Tested Yet", n: ntC }
  ];
  candidates.sort(function(a, b) {
    if (b.n !== a.n) return b.n - a.n;
    return (STATUS_PRIORITY[b.s] || 0) - (STATUS_PRIORITY[a.s] || 0);
  });
  return candidates[0].s;
}

// Returns true if a value looks like a PS5/PS4 title ID (e.g. PPSA01234, CUSA56789).
function isValidTitleId(val) {
  return /^[A-Z]{4}\d{5}$/i.test((val || "").toString().trim());
}

// Only called manually - NOT on every POST (too slow for large sheets).
function sortAndFormat(sheet) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;
  sheet.getRange(2, 1, lastRow - 1, COLS.length).sort({ column: 1, ascending: true });
  for (var r = 2; r <= lastRow; r++) {
    var status = sheet.getRange(r, colIndex("Status")).getValue();
    applyRowColor(sheet, r, status);
  }
  for (var c = 1; c <= COLS.length; c++) {
    sheet.autoResizeColumn(c);
  }
}

function doPost(e) {
  try {
    var data   = JSON.parse(e.postData.contents);
    var sheet  = getOrCreateSheet();
    var titleId = (data.title_id || "").toString().trim().toUpperCase();
    var status  = (data.status   || "Not Tested Yet").toString().trim();

    var lastRow = sheet.getLastRow();
    var existingRow = -1;
    if (titleId && lastRow >= 2) {
      var ids = sheet.getRange(2, colIndex("Title ID"), lastRow - 1, 1).getValues();
      for (var i = 0; i < ids.length; i++) {
        if ((ids[i][0] || "").toString().trim().toUpperCase() === titleId) {
          existingRow = i + 2;
          break;
        }
      }
    }

    var now = new Date().toISOString().slice(0, 16).replace("T", " ");

    if (existingRow > 0) {
      var total = parseInt(sheet.getRange(existingRow, colIndex("Reports")).getValue()) || 0;
      var wC    = parseInt(sheet.getRange(existingRow, colIndex("Working")).getValue())        || 0;
      var pC    = parseInt(sheet.getRange(existingRow, colIndex("Partial")).getValue())        || 0;
      var nwC   = parseInt(sheet.getRange(existingRow, colIndex("Not Working")).getValue())    || 0;
      var ntC   = parseInt(sheet.getRange(existingRow, colIndex("Not Tested Yet")).getValue()) || 0;

      // Auto-migrate old rows that have no vote counts yet.
      if (wC + pC + nwC + ntC === 0 && total > 0) {
        var oldStatus = sheet.getRange(existingRow, colIndex("Status")).getValue();
        if      (oldStatus === "Working")        wC  = total;
        else if (oldStatus === "Partial")        pC  = total;
        else if (oldStatus === "Not Working")    nwC = total;
        else                                     ntC = total;
      }

      if      (status === "Working")        wC++;
      else if (status === "Partial")        pC++;
      else if (status === "Not Working")    nwC++;
      else                                  ntC++;

      var newStatus = consensusStatus(wC, pC, nwC, ntC);
      sheet.getRange(existingRow, colIndex("Status")).setValue(newStatus);
      sheet.getRange(existingRow, colIndex("Reports")).setValue(total + 1);
      sheet.getRange(existingRow, colIndex("Working")).setValue(wC);
      sheet.getRange(existingRow, colIndex("Partial")).setValue(pC);
      sheet.getRange(existingRow, colIndex("Not Working")).setValue(nwC);
      sheet.getRange(existingRow, colIndex("Not Tested Yet")).setValue(ntC);
      sheet.getRange(existingRow, colIndex("Submitted")).setValue(now);
      if (data.shadowmount_ver) sheet.getRange(existingRow, colIndex("ShadowMount Ver.")).setValue(data.shadowmount_ver);
      if (data.notes)           sheet.getRange(existingRow, colIndex("Notes")).setValue(data.notes);
      applyRowColor(sheet, existingRow, newStatus);

    } else {
      var initW  = (status === "Working")        ? 1 : 0;
      var initP  = (status === "Partial")        ? 1 : 0;
      var initNW = (status === "Not Working")    ? 1 : 0;
      var initNT = (status === "Not Tested Yet") ? 1 : 0;
      var newRow = sheet.getLastRow() + 1;
      sheet.getRange(newRow, 1, 1, COLS.length).setValues([[
        titleId,
        data.game_title      || data.title_id || "",
        status,
        data.original_size   || "",
        data.compressed_size || "",
        data.storage         || "",
        data.shadowmount_ver || "",
        data.notes           || "",
        now,
        1,
        initW, initP, initNW, initNT
      ]]);
      applyRowColor(sheet, newRow, status);
      var total2 = sheet.getLastRow();
      if (total2 >= 3) {
        sheet.getRange(2, 1, total2 - 1, COLS.length).sort({ column: 1, ascending: true });
      }
    }

    return ContentService
      .createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  try {
    var sheet   = getOrCreateSheet();
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) {
      return ContentService
        .createTextOutput(JSON.stringify({ ok: true, count: 0, entries: [] }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    var data    = sheet.getRange(2, 1, lastRow - 1, COLS.length).getValues();
    var entries = [];
    for (var i = 0; i < data.length; i++) {
      var r = data[i];
      if (!r[0]) continue;
      entries.push({
        title_id:        r[colIndex("Title ID")         - 1],
        game_title:      r[colIndex("Game Title")       - 1],
        status:          r[colIndex("Status")           - 1],
        original_size:   r[colIndex("Original Size")    - 1],
        compressed_size: r[colIndex("Compressed Size")  - 1],
        storage:         r[colIndex("Storage")          - 1],
        shadowmount_ver: r[colIndex("ShadowMount Ver.") - 1],
        notes:           r[colIndex("Notes")            - 1],
        submitted:       r[colIndex("Submitted")        - 1],
        reports:         r[colIndex("Reports")          - 1],
        votes: {
          working:        r[colIndex("Working")        - 1],
          partial:        r[colIndex("Partial")        - 1],
          not_working:    r[colIndex("Not Working")    - 1],
          not_tested_yet: r[colIndex("Not Tested Yet") - 1]
        }
      });
    }
    return ContentService
      .createTextOutput(JSON.stringify({ ok: true, count: entries.length, entries: entries }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function setupSheet() {
  var ss    = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME);
  if (sheet) { sheet.clear(); } else { sheet = ss.insertSheet(SHEET_NAME); }
  writeHeader(sheet);
  sheet.setColumnWidth(colIndex("Title ID"),          100);
  sheet.setColumnWidth(colIndex("Game Title"),         260);
  sheet.setColumnWidth(colIndex("Status"),             120);
  sheet.setColumnWidth(colIndex("Original Size"),      110);
  sheet.setColumnWidth(colIndex("Compressed Size"),    120);
  sheet.setColumnWidth(colIndex("Notes"),              300);
  sheet.setColumnWidth(colIndex("Reports"),             60);
  sheet.setColumnWidth(colIndex("Working"),             60);
  sheet.setColumnWidth(colIndex("Partial"),             60);
  sheet.setColumnWidth(colIndex("Not Working"),         80);
  sheet.setColumnWidth(colIndex("Not Tested Yet"),     100);
  Logger.log("Sheet ready. Re-deploy the script as a Web App.");
}

function recolorAll() {
  sortAndFormat(getOrCreateSheet());
  Logger.log("Done recoloring.");
}

// Strip embedded/trailing title IDs and junk suffixes from a game title.
// Returns cleaned title, or "" if the whole string was just a title ID.
function cleanGameTitle(raw) {
  var t = (raw || "").toString().trim();
  // If the whole string is a title ID (with optional suffix like -app0), discard it.
  if (/^[A-Z]{4}\d{5}(\S*)?\s*$/i.test(t)) return "";
  // Strip a trailing title ID (e.g. "Astrobot PPSA21564").
  t = t.replace(/\s+[A-Z]{4}\d{5}(\S*)?$/i, "").trim();
  return t;
}

// Normalise a game title for dedup comparison: lowercase + collapse spaces.
function normTitle(t) {
  return (t || "").toLowerCase().replace(/\s+/g, " ").trim();
}

// Run ONCE to collapse all duplicate rows into one per game.
// Pass 1: merge rows that share the same Title ID.
// Pass 2: merge rows that share the same cleaned game title.
// Also fixes old-format rows (swapped title/name columns) and backfills vote counts.
function dedupSheet() {
  var sheet   = getOrCreateSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) { Logger.log("Nothing to dedup."); return; }

  var numCols = COLS.length;
  var raw     = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();

  // ── Pass 1: merge by Title ID ────────────────────────────────────────────
  var byId = {};

  for (var i = 0; i < raw.length; i++) {
    var row       = raw[i];
    var titleId   = (row[colIndex("Title ID")   - 1] || "").toString().trim().toUpperCase();
    var gameTitle = (row[colIndex("Game Title") - 1] || "").toString().trim();

    // Old-format rows had game title in col A and title ID in col B.
    if (!isValidTitleId(titleId) && isValidTitleId(gameTitle)) {
      var tmp = titleId;
      titleId   = gameTitle.toUpperCase();
      gameTitle = tmp;
    }
    if (!titleId) continue;

    var status  = (row[colIndex("Status")  - 1] || "Not Tested Yet").toString().trim();
    var reports = parseInt(row[colIndex("Reports") - 1]) || 1;
    var wC  = parseInt(row[colIndex("Working")        - 1]) || 0;
    var pC  = parseInt(row[colIndex("Partial")        - 1]) || 0;
    var nwC = parseInt(row[colIndex("Not Working")    - 1]) || 0;
    var ntC = parseInt(row[colIndex("Not Tested Yet") - 1]) || 0;

    if (wC + pC + nwC + ntC === 0) {
      if      (status === "Working")        wC  = reports;
      else if (status === "Partial")        pC  = reports;
      else if (status === "Not Working")    nwC = reports;
      else                                  ntC = reports;
    }

    if (byId[titleId]) {
      var m = byId[titleId];
      m.wC += wC; m.pC += pC; m.nwC += nwC; m.ntC += ntC; m.reports += reports;
      var cleaned = cleanGameTitle(gameTitle);
      if (!cleanGameTitle(m.gameTitle) && cleaned) m.gameTitle = cleaned;
      if (!m.originalSize   && row[colIndex("Original Size")    - 1]) m.originalSize   = row[colIndex("Original Size")    - 1];
      if (!m.compressedSize && row[colIndex("Compressed Size")  - 1]) m.compressedSize = row[colIndex("Compressed Size")  - 1];
      if (!m.storage        && row[colIndex("Storage")          - 1]) m.storage        = row[colIndex("Storage")          - 1];
      if (!m.smVer          && row[colIndex("ShadowMount Ver.") - 1]) m.smVer          = row[colIndex("ShadowMount Ver.") - 1];
    } else {
      var ct = cleanGameTitle(gameTitle);
      byId[titleId] = {
        titleId:        titleId,
        gameTitle:      ct || gameTitle || titleId,
        originalSize:   row[colIndex("Original Size")    - 1] || "",
        compressedSize: row[colIndex("Compressed Size")  - 1] || "",
        storage:        row[colIndex("Storage")          - 1] || "",
        smVer:          row[colIndex("ShadowMount Ver.") - 1] || "",
        notes:          row[colIndex("Notes")            - 1] || "",
        submitted:      row[colIndex("Submitted")        - 1] || "",
        reports: reports, wC: wC, pC: pC, nwC: nwC, ntC: ntC
      };
    }
  }

  // ── Pass 2: merge by cleaned game title ──────────────────────────────────
  var byTitle   = {};  // normTitle -> merged entry
  var titleKeys = [];  // insertion-order keys for byTitle

  var ids = Object.keys(byId).sort();
  for (var j = 0; j < ids.length; j++) {
    var e    = byId[ids[j]];
    var norm = normTitle(cleanGameTitle(e.gameTitle));

    if (!norm) {
      // No real title — keep as its own entry keyed by Title ID
      norm = "__id__" + e.titleId;
    }

    if (byTitle[norm]) {
      var mt = byTitle[norm];
      mt.wC += e.wC; mt.pC += e.pC; mt.nwC += e.nwC; mt.ntC += e.ntC; mt.reports += e.reports;
      // Prefer longer/cleaner game title
      if (cleanGameTitle(e.gameTitle).length > cleanGameTitle(mt.gameTitle).length) {
        mt.gameTitle = cleanGameTitle(e.gameTitle);
      }
      if (!mt.originalSize   && e.originalSize)   mt.originalSize   = e.originalSize;
      if (!mt.compressedSize && e.compressedSize) mt.compressedSize = e.compressedSize;
      if (!mt.storage        && e.storage)        mt.storage        = e.storage;
      if (!mt.smVer          && e.smVer)          mt.smVer          = e.smVer;
    } else {
      e.gameTitle = cleanGameTitle(e.gameTitle) || e.gameTitle;
      byTitle[norm] = e;
      titleKeys.push(norm);
    }
  }

  // ── Write back ───────────────────────────────────────────────────────────
  sheet.getRange(2, 1, lastRow - 1, numCols).clear();

  titleKeys.sort(function(a, b) {
    var ga = byTitle[a].gameTitle.toLowerCase();
    var gb = byTitle[b].gameTitle.toLowerCase();
    return ga < gb ? -1 : ga > gb ? 1 : 0;
  });

  if (titleKeys.length === 0) { Logger.log("No valid rows after dedup."); return; }

  var rows = [];
  for (var k = 0; k < titleKeys.length; k++) {
    var ent    = byTitle[titleKeys[k]];
    var status = consensusStatus(ent.wC, ent.pC, ent.nwC, ent.ntC);
    rows.push([
      ent.titleId, ent.gameTitle, status,
      ent.originalSize, ent.compressedSize, ent.storage,
      ent.smVer, ent.notes, ent.submitted,
      ent.reports, ent.wC, ent.pC, ent.nwC, ent.ntC
    ]);
  }

  sheet.getRange(2, 1, rows.length, numCols).setValues(rows);
  for (var r = 0; r < rows.length; r++) {
    applyRowColor(sheet, r + 2, rows[r][colIndex("Status") - 1]);
  }

  Logger.log("Dedup complete. " + titleKeys.length + " unique game(s) from " + raw.length + " rows.");
}

// ── One-time header rename (run once after deploying this script) ──────────
// Renames old short headers W / P / NW / NT to the full column names
// the script expects. Safe to run multiple times.
function migrateHeaders() {
  var ss    = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME) || ss.getSheets()[0];
  var last  = sheet.getLastColumn();
  if (last < 1) { Logger.log("Sheet is empty."); return; }

  var hdr = sheet.getRange(1, 1, 1, last).getValues()[0];
  var renames = { "W": "Working", "P": "Partial", "NW": "Not Working", "NT": "Not Tested Yet" };
  var changed = 0;

  for (var i = 0; i < hdr.length; i++) {
    var newName = renames[String(hdr[i]).trim()];
    if (newName) { hdr[i] = newName; changed++; }
  }

  if (changed > 0) {
    sheet.getRange(1, 1, 1, last).setValues([hdr]);
    Logger.log("Renamed " + changed + " header(s).");
  } else {
    Logger.log("Headers already up to date — nothing changed.");
  }
}
