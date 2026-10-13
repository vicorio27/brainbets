import colors from 'tailwindcss/colors'

// Green brand: every `blue-*` / `indigo-*` utility in the app is the accent colour, so the
// theme is set here instead of renaming classes. Emerald is shifted one step darker
// (blue-600 -> emerald-700) so white text on buttons and links on white keep WCAG AA contrast.
const e = colors.emerald
const brand = {
  50: e[50],
  100: e[100],
  200: e[200],
  300: e[300],
  400: e[500],
  500: e[600],
  600: e[700],
  700: e[800],
  800: e[900],
  900: e[950],
  950: e[950]
}

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{vue,js}'
  ],
  theme: {
    extend: {
      colors: {
        blue: brand,
        indigo: colors.teal,
        brand: { surface: '#f7fbf8' }
      }
    }
  },
  plugins: []
}
