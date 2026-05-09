export default function GenorovaLogo({ size = 40, showText = true }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <linearGradient id="dnaGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#00CFFF" />
            <stop offset="50%" stopColor="#7B61FF" />
            <stop offset="100%" stopColor="#00CFFF" />
          </linearGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <path
          d="M35 10 Q25 30 35 50 Q25 70 35 90"
          stroke="#0F2D6E"
          strokeWidth="4"
          fill="none"
          strokeLinecap="round"
        />
        <path
          d="M65 10 Q75 30 65 50 Q75 70 65 90"
          stroke="#0F2D6E"
          strokeWidth="4"
          fill="none"
          strokeLinecap="round"
        />
        {[20, 35, 50, 65, 80].map((y, i) => (
          <line
            key={i}
            x1={i % 2 === 0 ? 38 : 30}
            y1={y}
            x2={i % 2 === 0 ? 62 : 70}
            y2={y}
            stroke={i === 2 ? "url(#dnaGrad)" : "#1a3a8a"}
            strokeWidth={i === 2 ? 3 : 2}
            opacity={0.8}
          />
        ))}
        {[
          [50, 50],
          [22, 50],
          [78, 50],
          [50, 20],
          [50, 80],
        ].map(([x, y], i) => (
          <circle
            key={i}
            cx={x}
            cy={y}
            r={i === 0 ? 6 : 4}
            fill={i === 0 ? "url(#dnaGrad)" : "#0F2D6E"}
            filter={i === 0 ? "url(#glow)" : "none"}
            opacity={0.9}
          />
        ))}
        <line x1="50" y1="50" x2="22" y2="50" stroke="url(#dnaGrad)" strokeWidth="1.5" opacity="0.6" />
        <line x1="50" y1="50" x2="78" y2="50" stroke="url(#dnaGrad)" strokeWidth="1.5" opacity="0.6" />
        <line x1="50" y1="50" x2="50" y2="20" stroke="url(#dnaGrad)" strokeWidth="1.5" opacity="0.6" />
        <line x1="50" y1="50" x2="50" y2="80" stroke="url(#dnaGrad)" strokeWidth="1.5" opacity="0.6" />
        <circle cx="50" cy="50" r="12" fill="none" stroke="url(#dnaGrad)" strokeWidth="1.5" filter="url(#glow)" opacity="0.5" />
      </svg>
      {showText && (
        <span
          style={{
            fontFamily: '"Inter","SF Pro Display",system-ui,sans-serif',
            fontSize: size * 0.55,
            fontWeight: 700,
            color: "#0F2D6E",
            letterSpacing: 0,
          }}
        >
          Genorova
        </span>
      )}
    </div>
  );
}
