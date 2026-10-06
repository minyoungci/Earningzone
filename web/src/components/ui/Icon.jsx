const paths = {
  book: 'M12 5C8 3 5 3 3 4v16c3-1 6-1 9 1 M12 5c4-2 7-2 9-1v16c-3-1-6-1-9 1 M12 5v16',
  grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  globe: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M3 12h18 M12 3c5 5 5 13 0 18 M12 3c-5 5-5 13 0 18',
  zap: 'm13 2-9 12h7l-1 8 10-12h-7z',
  chart: 'M3 3v18h18 M6 15l5-5 4 3 6-7 M17 6h4v4',
  wallet: 'M20 7H5a2 2 0 0 1 0-4h14v4 M3 5v14a2 2 0 0 0 2 2h15V7 M20 11h-5v6h5 M16 14h1',
  bot: 'M12 3v3 M8 3h8 M5 7h14v13H5z M8 11h1 M15 11h1 M9 16h6 M2 11v5 M22 11v5',
  flask: 'M9 3h6 M10 3v7L4 20h16l-6-10V3 M7 15h10',
  briefcase: 'M8 7V3h8v4 M3 7h18v14H3z M3 12l9 4 9-4 M12 13v5',
  search: 'M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0 M15 15l6 6',
  arrow: 'M4 12h16 M14 6l6 6-6 6',
  chevron: 'm9 5 7 7-7 7',
  plus: 'M12 4v16 M4 12h16',
  sun: 'M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M12 2v2 M12 20v2 M2 12h2 M20 12h2 M5 5l1 1 M18 18l1 1 M5 19l1-1 M18 6l1-1',
  moon: 'M20 15A9 9 0 0 1 9 3a9 9 0 1 0 11 12z',
  settings: 'M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  lock: 'M7 10V7a5 5 0 0 1 10 0v3 M5 10h14v11H5z M12 14v3',
  refresh: 'M20 7V3l-4 4 M20 7a9 9 0 1 0 1 8 M20 7h-5',
}

export default function Icon({ name, size = 20, className = '' }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" className={className}><path d={paths[name] || paths.grid} /></svg>
}
