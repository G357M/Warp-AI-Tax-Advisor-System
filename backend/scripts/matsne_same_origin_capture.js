/*
 * Matsne same-origin publication collector.
 *
 * Run this file as a Chrome/Edge DevTools Snippet while the active page is on
 * https://matsne.gov.ge. It asks once for the pre-created capture-packet
 * directory, reads capture_plan.json, and stores exact response bodies plus a
 * receipt per publication. It never sends cookies or response bodies anywhere
 * except matsne.gov.ge and the directory selected by the operator.
 *
 * Optional configuration before running:
 *   window.__MATSNE_CAPTURE_OPTIONS__ = {
 *     startPublication: 0,
 *     maxNewCaptures: 246,
 *     delayMs: 1000
 *   };
 * Abort between publications:
 *   window.__MATSNE_CAPTURE_ABORT__ = true;
 */

void (async () => {
  "use strict";

  const CONTRACT = "matsne-publication-capture-plan-v1";
  const RECEIPT_CONTRACT = "matsne-browser-capture-receipt-v1";
  const CAPTURE_METHOD = "same_origin_browser_fetch";
  const EXPECTED_ORIGIN = "https://matsne.gov.ge";
  const MAX_SOURCE_BYTES = 64 * 1024 * 1024;
  const BLOCK_MARKERS = [
    "access denied",
    "human verification",
    "captcha",
    "just a moment",
    "cf-chl-",
  ];

  const fail = (message) => {
    throw new Error(message);
  };

  const assert = (condition, message) => {
    if (!condition) fail(message);
  };

  const isPlainObject = (value) =>
    value !== null && typeof value === "object" && !Array.isArray(value);

  const exactKeys = (value, expected, label) => {
    assert(isPlainObject(value), `${label} must be an object`);
    const actual = Object.keys(value).sort();
    const wanted = [...expected].sort();
    assert(JSON.stringify(actual) === JSON.stringify(wanted), `${label} fields mismatch`);
  };

  const sha256 = async (bytes) => {
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(digest)]
      .map((value) => value.toString(16).padStart(2, "0"))
      .join("");
  };

  const encodeJson = (value) =>
    new TextEncoder().encode(`${JSON.stringify(value, null, 2)}\n`);

  const decodeUtf8 = (bytes, label) => {
    try {
      return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch (_error) {
      fail(`${label} is not UTF-8`);
    }
  };

  const sleep = (milliseconds) =>
    new Promise((resolve) => window.setTimeout(resolve, milliseconds));

  const chooseCaptureDirectory = () =>
    new Promise((resolve, reject) => {
      const previous = document.getElementById("tax-advisor-matsne-capture-start");
      if (previous) previous.remove();
      const button = document.createElement("button");
      button.id = "tax-advisor-matsne-capture-start";
      button.type = "button";
      button.textContent = "Start verified Matsne capture";
      Object.assign(button.style, {
        position: "fixed",
        top: "16px",
        right: "16px",
        zIndex: "2147483647",
        padding: "12px 18px",
        border: "2px solid #ffffff",
        borderRadius: "8px",
        background: "#1358d0",
        color: "#ffffff",
        font: "600 14px/1.2 system-ui, sans-serif",
        boxShadow: "0 4px 18px rgba(0, 0, 0, 0.28)",
        cursor: "pointer",
      });
      button.addEventListener(
        "click",
        async () => {
          try {
            const directory = await window.showDirectoryPicker({ mode: "readwrite" });
            button.remove();
            resolve(directory);
          } catch (error) {
            button.remove();
            reject(error);
          }
        },
        { once: true },
      );
      document.documentElement.appendChild(button);
      console.info(
        "Click 'Start verified Matsne capture' on the page to select the packet directory.",
      );
    });

  const getDirectory = async (root, parts) => {
    let current = root;
    for (const part of parts) {
      current = await current.getDirectoryHandle(part, { create: false });
    }
    return current;
  };

  const readOptionalFile = async (root, relativePath) => {
    const parts = relativePath.split("/");
    const filename = parts.pop();
    const directory = await getDirectory(root, parts);
    try {
      const handle = await directory.getFileHandle(filename, { create: false });
      const file = await handle.getFile();
      return new Uint8Array(await file.arrayBuffer());
    } catch (error) {
      if (error && error.name === "NotFoundError") return null;
      throw error;
    }
  };

  const writeNewOrMatch = async (root, relativePath, bytes, expectedSha) => {
    const parts = relativePath.split("/");
    const filename = parts.pop();
    const directory = await getDirectory(root, parts);
    let handle;
    try {
      handle = await directory.getFileHandle(filename, { create: false });
      const existing = new Uint8Array(await (await handle.getFile()).arrayBuffer());
      const existingSha = await sha256(existing);
      assert(
        existing.length === bytes.length && existingSha === expectedSha,
        `${relativePath} already exists with different bytes; nothing was overwritten`,
      );
      return "matched_existing";
    } catch (error) {
      if (!error || error.name !== "NotFoundError") throw error;
    }
    handle = await directory.getFileHandle(filename, { create: true });
    const writable = await handle.createWritable({ keepExistingData: false });
    try {
      await writable.write(bytes);
      await writable.close();
    } catch (error) {
      await writable.abort().catch(() => undefined);
      throw error;
    }
    const stored = new Uint8Array(await (await handle.getFile()).arrayBuffer());
    assert(
      stored.length === bytes.length && (await sha256(stored)) === expectedSha,
      `${relativePath} failed post-write verification`,
    );
    return "written_new";
  };

  const canonicalItem = (documentId, publication) => {
    const directory = `editions/${String(publication).padStart(6, "0")}`;
    return {
      publication,
      page_url: `${EXPECTED_ORIGIN}/ka/document/view/${documentId}?publication=${publication}`,
      page_file: `${directory}/page.html`,
      tree_url: `${EXPECTED_ORIGIN}/ka/document/tree/${documentId}/${publication}`,
      tree_file: `${directory}/tree.json`,
    };
  };

  const validatePlan = (plan) => {
    exactKeys(plan, ["contract", "act", "range", "items", "plan_sha256"], "plan");
    assert(plan.contract === CONTRACT, "capture plan contract mismatch");
    assert(/^[0-9a-f]{64}$/.test(plan.plan_sha256), "capture plan identity is invalid");
    exactKeys(
      plan.act,
      ["act_key", "document_id", "title_ka", "language", "official_document_url"],
      "act",
    );
    assert(/^[1-9]\d*$/.test(plan.act.document_id), "document id is invalid");
    assert(plan.act.language === "ka", "only the Georgian official source is accepted");
    assert(
      plan.act.official_document_url ===
        `${EXPECTED_ORIGIN}/ka/document/view/${plan.act.document_id}`,
      "official document URL mismatch",
    );
    exactKeys(
      plan.range,
      ["first_publication", "last_publication", "publication_count"],
      "range",
    );
    const { first_publication: first, last_publication: last, publication_count: count } =
      plan.range;
    assert(Number.isInteger(first) && first >= 0, "first publication is invalid");
    assert(Number.isInteger(last) && last >= first, "last publication is invalid");
    assert(Number.isInteger(count) && count === last - first + 1, "range is inconsistent");
    assert(count <= 2000, "capture range exceeds the safety bound");
    assert(Array.isArray(plan.items) && plan.items.length === count, "plan coverage mismatch");
    plan.items.forEach((item, index) => {
      exactKeys(
        item,
        ["publication", "page_url", "page_file", "tree_url", "tree_file"],
        `item ${index}`,
      );
      const expected = canonicalItem(plan.act.document_id, first + index);
      for (const [field, value] of Object.entries(expected)) {
        assert(item[field] === value, `item ${index} ${field} is not canonical`);
      }
    });
    return plan;
  };

  const validateBody = (kind, bytes, contentType) => {
    assert(bytes.length > 0 && bytes.length <= MAX_SOURCE_BYTES, `${kind} size is invalid`);
    const mediaType = contentType.split(";", 1)[0].trim().toLowerCase();
    const allowed =
      kind === "page"
        ? new Set(["text/html", "application/xhtml+xml"])
        : new Set(["application/json", "text/json", "text/plain"]);
    assert(allowed.has(mediaType), `${kind} content type is unexpected: ${contentType}`);
    const decoded = decodeUtf8(bytes, kind);
    const prefix = decoded.slice(0, 200000).toLowerCase();
    assert(!BLOCK_MARKERS.some((marker) => prefix.includes(marker)), `${kind} is a challenge page`);
    if (kind === "page") {
      assert(/<html[\s>]/i.test(decoded), "page response is not an HTML document");
    } else {
      let parsed;
      try {
        parsed = JSON.parse(decoded.replace(/^\uFEFF/, ""));
      } catch (_error) {
        fail("tree response is not JSON");
      }
      assert(isPlainObject(parsed), "tree JSON root is not an object");
    }
  };

  const validateSourcePair = (pageBytes, treeBytes) => {
    const pageText = decodeUtf8(pageBytes, "page");
    const tree = JSON.parse(
      decodeUtf8(treeBytes, "tree").replace(/^\uFEFF/, ""),
    );
    const anchors = [];
    const visit = (value) => {
      if (Array.isArray(value)) {
        value.forEach(visit);
        return;
      }
      if (!isPlainObject(value)) return;
      const title = typeof value.Title === "string" ? value.Title.trim() : "";
      const anchor = typeof value.Anchor === "string" ? value.Anchor.trim() : "";
      if (/^მუხლი\s+\d/.test(title) && anchor) anchors.push(anchor);
      Object.values(value).forEach(visit);
    };
    visit(tree);
    assert(anchors.length > 0 && anchors.length <= 5000, "tree article count is invalid");
    const parsedPage = new DOMParser().parseFromString(pageText, "text/html");
    const idCounts = new Map();
    parsedPage.querySelectorAll("[id]").forEach((element) => {
      idCounts.set(element.id, (idCounts.get(element.id) || 0) + 1);
    });
    assert(
      anchors.some((anchor) => idCounts.get(anchor) === 1),
      "page and tree have no matching unique article anchor",
    );
  };

  const fetchOfficial = async (kind, url, file) => {
    const requested = new URL(url);
    assert(requested.origin === EXPECTED_ORIGIN, `${kind} request is not same-origin Matsne`);
    const response = await fetch(requested.href, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      redirect: "follow",
      referrerPolicy: "strict-origin-when-cross-origin",
      headers: {
        Accept:
          kind === "page"
            ? "text/html,application/xhtml+xml"
            : "application/json,text/plain;q=0.9,*/*;q=0.1",
      },
    });
    const fetchedAt = new Date().toISOString();
    assert(response.status === 200, `${kind} returned HTTP ${response.status}`);
    assert(response.url === requested.href, `${kind} final URL changed to ${response.url}`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    const contentType = response.headers.get("content-type") || "";
    validateBody(kind, bytes, contentType);
    return {
      bytes,
      receipt: {
        requested_url: requested.href,
        response_url: response.url,
        file,
        status: response.status,
        content_type: contentType,
        etag: response.headers.get("etag") || "",
        last_modified: response.headers.get("last-modified") || "",
        byte_length: bytes.length,
        sha256: await sha256(bytes),
        fetched_at_utc: fetchedAt,
      },
    };
  };

  const validateCompletedReceipt = async (root, item, raw, planSha) => {
    let receipt;
    try {
      receipt = JSON.parse(decodeUtf8(raw, "existing receipt").replace(/^\uFEFF/, ""));
    } catch (_error) {
      fail(`publication ${item.publication} has an invalid existing receipt`);
    }
    assert(receipt.contract === RECEIPT_CONTRACT, "existing receipt contract mismatch");
    assert(receipt.capture_method === CAPTURE_METHOD, "existing capture method mismatch");
    assert(receipt.plan_sha256 === planSha, "existing receipt plan pin mismatch");
    assert(receipt.publication === item.publication, "existing receipt publication mismatch");
    for (const kind of ["page", "tree"]) {
      const expectedFile = item[`${kind}_file`];
      const expectedUrl = item[`${kind}_url`];
      const evidence = receipt[kind];
      assert(isPlainObject(evidence), `existing ${kind} receipt is missing`);
      assert(evidence.file === expectedFile, `existing ${kind} file mismatch`);
      assert(evidence.requested_url === expectedUrl, `existing ${kind} request URL mismatch`);
      assert(evidence.response_url === expectedUrl, `existing ${kind} response URL mismatch`);
      assert(evidence.status === 200, `existing ${kind} status mismatch`);
      const source = await readOptionalFile(root, expectedFile);
      assert(source !== null, `existing receipt has no ${expectedFile}`);
      assert(source.length === evidence.byte_length, `existing ${kind} byte length mismatch`);
      assert((await sha256(source)) === evidence.sha256, `existing ${kind} hash mismatch`);
    }
  };

  assert(
    location.origin === EXPECTED_ORIGIN,
    `open ${EXPECTED_ORIGIN} before running this snippet`,
  );
  assert(window.isSecureContext, "the collector requires a secure browser context");
  assert(typeof window.showDirectoryPicker === "function", "use current Chrome or Edge");

  const configured = window.__MATSNE_CAPTURE_OPTIONS__ || {};
  const options = {
    startPublication:
      configured.startPublication === undefined ? null : configured.startPublication,
    maxNewCaptures:
      configured.maxNewCaptures === undefined ? 2000 : configured.maxNewCaptures,
    delayMs: configured.delayMs === undefined ? 1000 : configured.delayMs,
  };
  assert(
    options.startPublication === null ||
      (Number.isInteger(options.startPublication) && options.startPublication >= 0),
    "startPublication is invalid",
  );
  assert(
    Number.isInteger(options.maxNewCaptures) &&
      options.maxNewCaptures >= 1 &&
      options.maxNewCaptures <= 2000,
    "maxNewCaptures must be 1..2000",
  );
  assert(
    Number.isInteger(options.delayMs) && options.delayMs >= 500 && options.delayMs <= 10000,
    "delayMs must be 500..10000",
  );

  window.__MATSNE_CAPTURE_ABORT__ = false;
  const root = await chooseCaptureDirectory();
  const planHandle = await root.getFileHandle("capture_plan.json", { create: false });
  const planBytes = new Uint8Array(
    await (await planHandle.getFile()).arrayBuffer(),
  );
  assert(
    planBytes.length > 0 && planBytes.length <= 8 * 1024 * 1024,
    "plan size is invalid",
  );
  const plan = validatePlan(
    JSON.parse(decodeUtf8(planBytes, "capture plan").replace(/^\uFEFF/, "")),
  );

  const result = {
    contract: "matsne-same-origin-capture-run-v1",
    plan_sha256: plan.plan_sha256,
    started_at_utc: new Date().toISOString(),
    completed_at_utc: null,
    existing_receipts_verified: 0,
    new_receipts_written: 0,
    stopped: false,
    next_publication: null,
    database_writes_allowed: false,
    public_answer_routing_changed: false,
  };
  window.__MATSNE_CAPTURE_RESULT__ = result;

  const eligible = plan.items.filter(
    (item) => options.startPublication === null || item.publication >= options.startPublication,
  );
  console.info(
    `Matsne capture started: ${eligible.length} planned publications, ` +
      `${options.delayMs} ms minimum delay`,
  );

  for (const item of eligible) {
    if (window.__MATSNE_CAPTURE_ABORT__) {
      result.stopped = true;
      result.next_publication = item.publication;
      break;
    }
    const receiptFile =
      `editions/${String(item.publication).padStart(6, "0")}` +
      "/browser_capture_receipt.json";
    const existingReceipt = await readOptionalFile(root, receiptFile);
    if (existingReceipt !== null) {
      await validateCompletedReceipt(root, item, existingReceipt, plan.plan_sha256);
      result.existing_receipts_verified += 1;
      continue;
    }
    if (result.new_receipts_written >= options.maxNewCaptures) {
      result.stopped = true;
      result.next_publication = item.publication;
      break;
    }

    const page = await fetchOfficial("page", item.page_url, item.page_file);
    const tree = await fetchOfficial("tree", item.tree_url, item.tree_file);
    validateSourcePair(page.bytes, tree.bytes);
    await writeNewOrMatch(root, item.page_file, page.bytes, page.receipt.sha256);
    await writeNewOrMatch(root, item.tree_file, tree.bytes, tree.receipt.sha256);
    const receipt = {
      contract: RECEIPT_CONTRACT,
      capture_method: CAPTURE_METHOD,
      plan_sha256: plan.plan_sha256,
      publication: item.publication,
      browser_origin: location.origin,
      completed_at_utc: new Date().toISOString(),
      page: page.receipt,
      tree: tree.receipt,
      database_writes_allowed: false,
      public_answer_routing_changed: false,
    };
    const receiptBytes = encodeJson(receipt);
    await writeNewOrMatch(root, receiptFile, receiptBytes, await sha256(receiptBytes));
    result.new_receipts_written += 1;
    if (result.new_receipts_written % 10 === 0) {
      console.info(
        `Captured ${result.new_receipts_written} new editions; ` +
          `latest publication ${item.publication}`,
      );
    }
    await sleep(options.delayMs);
  }

  result.completed_at_utc = new Date().toISOString();
  console.table(result);
  if (!result.stopped) {
    console.info("Matsne source capture pass completed. Run the offline receipt audit next.");
  }
})().catch((error) => {
  window.__MATSNE_CAPTURE_RESULT__ = {
    ...(window.__MATSNE_CAPTURE_RESULT__ || {}),
    completed_at_utc: new Date().toISOString(),
    stopped: true,
    error: String(error && error.message ? error.message : error),
    database_writes_allowed: false,
    public_answer_routing_changed: false,
  };
  console.error("Matsne capture stopped safely:", error);
});
