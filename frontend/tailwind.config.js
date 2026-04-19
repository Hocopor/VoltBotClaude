/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        voltage: {
          bg:      '#0a0b0e',
          panel:   '#111318',
          border:  '#1e2230',
          hover:   '#1a1f2e',
          accent:  '#f0b90b',
          green:   '#00d395',
          red:     '#f6465d',
          blue:    '#3b82f6',
          muted:   '#8b949e',
          text:    '#e6edf3',
        },
      },
      fontFamily: { mono: ['JetBrains Mono', 'Fira Code', 'monospace'] },
      backgroundImage: {
        'gradient-voltage': 'linear-gradient(135deg, #0a0b0e 0%, #111318 100%)',
      },
    },
  },
  plugins: [],
}
