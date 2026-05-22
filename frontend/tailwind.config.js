/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'kkday-blue': '#26cece',
        // Spec tokens — search-audit-batch-ui-spec.md §2
        // Backgrounds
        'page-bg':       '#f5f4f1',
        'amber-status':  '#FAEEDA', // status bar bg (cancelled/interrupted)
        'amber-row':     '#FFFCF5', // 待續跑 row tint
        'amber-border':  '#F0D49B',
        'green-status':  '#EAF7F1', // done status bar bg (lighter sibling of #1D9E75)
        'green-border':  '#B7E2D2',
        // Status dots / accents
        'status-amber':  '#EF9F27',
        'status-green':  '#1D9E75',
        'status-blue':   '#378ADD', // 執行中 dot
        'status-red':    '#E24B4A',
        'cookie-green':  '#639922',
        // Typography
        'text-primary':   '#1a1a1a',
        'text-secondary': '#5f5e5a',
        'text-tertiary':  '#888780',
        'text-amber-dk':  '#854F0B',
        'text-green-dk':  '#0F6E56',
        'text-blue-dk':   '#0C447C',
        'text-purple-dk': '#3C3489',
        'text-red-dk':    '#791F1F',
        // Severity / algo chip backgrounds
        'chip-blue':      '#E6F1FB',
        'chip-purple':    '#EEEDFE',
        'chip-red':       '#FCEBEB',
        'chip-amber':     '#FAEEDA',
        'chip-gray':      '#F2F1ED',
        // Borders
        'border-hair':    'rgba(0,0,0,0.08)',
      },
    },
  },
  plugins: [],
}
