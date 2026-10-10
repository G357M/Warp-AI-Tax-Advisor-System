#!/usr/bin/env node
// Admin UI styles live in app/admin/admin.module.css. Inline style objects are
// allowed only to pass CSS custom properties (e.g. style={{ '--w': '40%' }}).
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const roots = ['app/admin', 'components/admin'];
const forbidden = /style=\{\{(?!\s*['"]--)/g;
const failures = [];

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path);
    else if (path.endsWith('.tsx')) {
      readFileSync(path, 'utf8').split('\n').forEach((line, index) => {
        if (forbidden.test(line)) failures.push(`${relative('.', path)}:${index + 1}`);
        forbidden.lastIndex = 0;
      });
    }
  }
}

for (const root of roots) {
  try { walk(root); } catch (error) { if (error.code !== 'ENOENT') throw error; }
}
if (failures.length) {
  console.error(`Inline styles are not allowed in the admin UI:\n${failures.join('\n')}`);
  process.exit(1);
}
console.log('Admin UI has no inline style objects.');
