/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: '#0d0d0d',
        card: '#111111',
        border: '#1a2a4a',
        accent: '#3b82f6',
        'accent-hover': '#2563eb',
        'accent-dim': '#1d3a6e',
      },
    },
  },
  plugins: [],
}
