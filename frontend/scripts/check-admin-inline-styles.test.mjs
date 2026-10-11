import { test } from 'node:test';
import assert from 'node:assert/strict';
import { findViolations } from './check-admin-inline-styles.mjs';

const ok = (name, src) => test(`ok: ${name}`, () => assert.deepEqual(findViolations(src), []));
const bad = (name, src, lines = [1]) => test(`violation: ${name}`, () => assert.deepEqual(findViolations(src), lines));

ok('custom property object', `<div style={{ '--w': '40%' }} />`);
ok('vars() helper', `<div style={vars({ '--w': x, '--c': c })} />`);
ok('multi-line object', `<div style={{\n  '--w': x,\n}} />`);
ok('double-quoted key and template value', '<div style={{ "--c": `hsl(${h}, 50%, 50%)` }} />');
ok('no style attribute', `<div className={styles.a} />`);
bad('mixed keys', `<div style={{ '--w': x, color: 'red' }} />`);
bad('plain property', `<div style={{ padding: 4 }} />`);
bad('identifier expression', `<div style={obj} />`);
bad('empty object', `<div style={{}} />`);
bad('function call other than vars', `<div style={make()} />`);
bad('violation line number', `<a>\n<b />\n<div style={{ padding: 4 }} />`, [3]);
