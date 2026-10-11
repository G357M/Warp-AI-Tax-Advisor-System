#!/usr/bin/env node
// Admin UI styles live in app/admin/admin.module.css. Inline styles are allowed
// only to pass CSS custom properties: style={{ '--w': '40%' }} or
// style={vars({ '--w': x, '--c': c })}. Every key must be a quoted '--*' string.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { pathToFileURL } from 'node:url';

const roots = ['app/admin', 'components/admin'];
const isQuote = (c) => c === "'" || c === '"' || c === '`';
const isSpace = (c) => c === ' ' || c === '\n' || c === '\r' || c === '\t';

function skipSpace(s, i) {
  while (i < s.length && isSpace(s[i])) i++;
  return i;
}

// s[i] is a quote character; returns the index just after the closing quote.
function skipQuoted(s, i) {
  const q = s[i];
  i++;
  while (i < s.length) {
    const c = s[i];
    if (c === '\\') i += 2;
    else if (q === '`' && c === '$' && s[i + 1] === '{') i = skipBraces(s, i + 1);
    else if (c === q) return i + 1;
    else i++;
  }
  return s.length;
}

// s[i] is '{'; returns the index just after the matching '}'.
function skipBraces(s, i) {
  let depth = 0;
  while (i < s.length) {
    const c = s[i];
    if (isQuote(c)) { i = skipQuoted(s, i); continue; }
    if (c === '{') depth++;
    else if (c === '}' && --depth === 0) return i + 1;
    i++;
  }
  return s.length;
}

// s[i] is '{'. Returns { end, ok }: ok when the literal has at least one key and
// every top-level key is a quoted string starting with '--'.
function checkObject(s, i) {
  const end = skipBraces(s, i);
  const stop = end - 1;
  let pos = i + 1;
  let keys = 0;
  for (;;) {
    pos = skipSpace(s, pos);
    if (pos >= stop) break;
    const c = s[pos];
    if (c !== "'" && c !== '"') return { end, ok: false };
    const close = skipQuoted(s, pos);
    if (!s.slice(pos + 1, close - 1).startsWith('--')) return { end, ok: false };
    pos = skipSpace(s, close);
    if (s[pos] !== ':') return { end, ok: false };
    keys++;
    pos++;
    let depth = 0;
    while (pos < stop) {
      const d = s[pos];
      if (isQuote(d)) { pos = skipQuoted(s, pos); continue; }
      if (d === '(' || d === '[' || d === '{') depth++;
      else if (d === ')' || d === ']' || d === '}') depth--;
      else if (d === ',' && depth === 0) break;
      pos++;
    }
    if (s[pos] === ',') pos++;
  }
  return { end, ok: keys > 0 };
}

/** Returns 1-based line numbers of every disallowed `style={...}` in a source text. */
export function findViolations(source) {
  const violations = [];
  const re = /(?<![\w-])style=\{/g;
  let m;
  while ((m = re.exec(source))) {
    const line = source.slice(0, m.index).split('\n').length;
    let pos = skipSpace(source, m.index + m[0].length);
    let ok = false;
    if (source[pos] === '{') {
      const r = checkObject(source, pos);
      ok = r.ok && source[skipSpace(source, r.end)] === '}';
    } else if (source.startsWith('vars(', pos)) {
      pos = skipSpace(source, pos + 5);
      if (source[pos] === '{') {
        const r = checkObject(source, pos);
        const after = skipSpace(source, r.end);
        ok = r.ok && source[after] === ')' && source[skipSpace(source, after + 1)] === '}';
      }
    }
    if (!ok) violations.push(line);
  }
  return violations;
}

function walk(dir, failures) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, failures);
    else if (path.endsWith('.tsx')) {
      for (const line of findViolations(readFileSync(path, 'utf8'))) {
        failures.push(`${relative('.', path)}:${line}`);
      }
    }
  }
}

function main() {
  const failures = [];
  for (const root of roots) {
    try { walk(root, failures); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  if (failures.length) {
    console.error(`Inline styles are not allowed in the admin UI (only CSS custom properties):\n${failures.join('\n')}`);
    process.exit(1);
  }
  console.log('Admin UI has no inline style objects.');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
