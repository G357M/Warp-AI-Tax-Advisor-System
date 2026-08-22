import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        success: 'hsl(var(--success))',
        error: {
          DEFAULT: 'hsl(var(--error))',
          foreground: 'hsl(var(--error-foreground))',
          border: 'hsl(var(--error-border))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      fontFamily: {
        heading: [
          'var(--font-instrument)',
          'var(--font-georgian-serif)',
          'Instrument Serif Fallback',
          'Georgia',
          'serif',
        ],
        body: [
          'var(--font-barlow)',
          'var(--font-inter)',
          'var(--font-georgian)',
          'Inter Fallback',
          'Barlow Fallback',
          'system-ui',
          'sans-serif',
        ],
        sans: [
          'var(--font-barlow)',
          'var(--font-inter)',
          'var(--font-georgian)',
          'Inter Fallback',
          'Barlow Fallback',
          'system-ui',
          'sans-serif',
        ],
      },
      letterSpacing: {
        display: '-0.02em',
      },
      maxWidth: {
        page: '1120px',
      },
    },
  },
  plugins: [],
}

export default config
