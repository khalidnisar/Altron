import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0B0D12',
        panel: '#141821',
        panel2: '#1B2030',
        edge: '#252B3B',
        ink: '#E8EAF2',
        muted: '#8B93A7',
        brand: '#5C7CFA',
        ok: '#22C55E',
        warn: '#F59E0B',
        bad: '#EF4444',
      },
    },
  },
  plugins: [],
};
export default config;
