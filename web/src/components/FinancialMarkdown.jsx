import { Fragment } from 'react'
import { Link } from 'react-router-dom'

// Render public articles as React text, never HTML. Only indexed assets/documents
// and HTTP(S) links are clickable; source file references remain descriptive text.
export function referenceTarget(ref, documents, images, currentPath = '') {
  const value = ref.trim().replace(/\\/g, '/')
  if (/^https?:\/\//i.test(value)) return { href: value, external: true }
  let rel = value.split(/docs\/public\//i)[1]
  if (!rel && !/^(?:[a-z]+:|\/)/i.test(value)) rel = value
  if (!rel || rel.includes('..')) return null
  rel = rel.split('#')[0].replace(/:\d+$/, '')
  const doc = documents.find((d) => d.path === rel)
  if (doc) return { doc: doc.id }
  const img = images.find((i) => `images/${i.id}` === rel)
  return img ? { href: img.url, image: true } : null
}

export default function FinancialMarkdown({ content, documents, images, currentPath }) {
  const inline = (text) => text.split(/(!?\[[^\]]*\]\([^)]*\)|\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    const link = /^(!?)\[([^\]]*)\]\(([^)]*)\)$/.exec(part)
    if (link) {
      const target = referenceTarget(link[3], documents, images, currentPath)
      if (link[1] && target?.image) return <a key={i} href={target.href} target="_blank" rel="noopener noreferrer"><img loading="lazy" src={target.href} alt={link[2].trim() || '차트 학습 그림'} /></a>
      if (target?.doc) return <Link key={i} to={`/learn?doc=${encodeURIComponent(target.doc)}`}>{link[2]}</Link>
      if (target?.href) return <a key={i} href={target.href} target="_blank" rel="noopener noreferrer">{link[2]}</a>
      return <span key={i} title={link[3]}>{link[2]}</span>
    }
    if (part.startsWith('**')) return <strong key={i}>{part.slice(2,-2)}</strong>
    if (part.startsWith('`')) return <code key={i}>{part.slice(1,-1)}</code>
    return <Fragment key={i}>{part}</Fragment>
  })
  const lines = content.split('\n'), blocks = []
  const cells = (s) => s.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
  for (let i = 0; i < lines.length;) {
    const line = lines[i].trim(), key = i
    if (!line) { i++; continue }
    if (line.startsWith('```')) {
      const code = []; i++
      while (i < lines.length && !lines[i].startsWith('```')) code.push(lines[i++])
      i++; blocks.push(<pre key={key}><code>{code.join('\n')}</code></pre>); continue
    }
    const heading = /^(#{1,6})\s+(.+)$/.exec(line)
    if (heading) { const Tag = `h${Math.min(heading[1].length + 1,6)}`; blocks.push(<Tag key={key}>{inline(heading[2])}</Tag>); i++; continue }
    if (/^\|/.test(line) && /^\|?[\s:|-]+\|/.test(lines[i+1]?.trim() || '')) {
      const header = cells(line), rows = []; i += 2
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(cells(lines[i++]))
      blocks.push(<div key={key} className="study-table-wrap"><table><thead><tr>{header.map((c,j) => <th key={j}>{inline(c)}</th>)}</tr></thead><tbody>{rows.map((row,j) => <tr key={j}>{row.map((c,k) => <td key={k}>{inline(c)}</td>)}</tr>)}</tbody></table></div>); continue
    }
    if (/^(?:[-*]|\d+\.)\s/.test(line)) {
      const rows = [], ordered = /^\d+\./.test(line), Tag = ordered ? 'ol' : 'ul'
      while (i < lines.length && (ordered ? /^\d+\.\s/ : /^[-*]\s/).test(lines[i].trim())) rows.push(lines[i++].trim().replace(/^(?:[-*]|\d+\.)\s+/, ''))
      blocks.push(<Tag key={key}>{rows.map((r,j) => <li key={j}>{inline(r)}</li>)}</Tag>); continue
    }
    if (/^---+$/.test(line)) { blocks.push(<hr key={key} />); i++; continue }
    if (line.startsWith('>')) { blocks.push(<blockquote key={key}>{inline(line.replace(/^>\s?/,''))}</blockquote>); i++; continue }
    blocks.push(<p key={key}>{inline(line)}</p>); i++
  }
  return <div className="financial-markdown">{blocks}</div>
}
