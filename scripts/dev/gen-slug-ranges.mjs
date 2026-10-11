// SPDX-License-Identifier: Apache-2.0
// Development only; never shipped in a distribution and not run in CI.
//
// Emits the code points that github-slugger's generated regex deletes, as sorted
// inclusive ranges in the form packages/core/src/mgtk_repo_utils/slug.py embeds. The regex is a
// UTF-16 expression with surrogate-pair alternatives, so every code point is tested
// the way the slugger applies it: a code point is removed when replacing the regex
// in its own string leaves nothing. Lone surrogates are skipped (Python text holds
// none).
//
// usage: node gen-slug-ranges.mjs <path to github-slugger regex.js>
import { pathToFileURL } from 'node:url'
import { resolve } from 'node:path'

const [, , regexPath] = process.argv
if (!regexPath) {
  console.error('usage: node gen-slug-ranges.mjs <path to github-slugger regex.js>')
  process.exit(2)
}
const { regex } = await import(pathToFileURL(resolve(regexPath)).href)

const ranges = []
let start = -1
for (let cp = 0; cp <= 0x10ffff; cp++) {
  const surrogate = cp >= 0xd800 && cp <= 0xdfff
  const removed = !surrogate && String.fromCodePoint(cp).replace(regex, '') === ''
  if (removed && start < 0) start = cp
  if (!removed && start >= 0) {
    ranges.push([start, cp - 1])
    start = -1
  }
}
if (start >= 0) ranges.push([start, 0x10ffff])

const hex = (n) => '0x' + n.toString(16).toUpperCase().padStart(4, '0')
for (const [low, high] of ranges) console.log(`    (${hex(low)}, ${hex(high)}),`)
console.error(`${ranges.length} ranges`)
