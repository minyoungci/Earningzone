/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['Pretendard', 'Inter', 'system-ui', 'sans-serif'] },
      colors: {
        buy: '#34d399',
        sell: '#fb7185',
        up: '#fb7185',   // 한국식: 상승=빨강
        down: '#38bdf8', // 하락=파랑
      },
      // 강한 커스텀 이징을 기본 reach 로 — ease-out 클래스가 빌트인보다 단단하게 감속.
      transitionTimingFunction: {
        out: 'cubic-bezier(0.23, 1, 0.32, 1)',
        'in-out': 'cubic-bezier(0.77, 0, 0.175, 1)',
        drawer: 'cubic-bezier(0.32, 0.72, 0, 1)',
      },
    },
  },
  plugins: [],
}
