import { ImageResponse } from "next/og";

export const runtime = "edge";

export const alt = "사주캔들 투자 체질";
export const size = {
  width: 1200,
  height: 630,
};
export const contentType = "image/png";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function Image({ params }: Props) {
  const { id } = await params;
  const investorType = decodeURIComponent(id);

  return new ImageResponse(
    (
      <div
        style={{
          background: "linear-gradient(135deg, #18181b 0%, #27272a 50%, #18181b 100%)",
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "sans-serif",
          gap: "24px",
        }}
      >
        {/* Logo */}
        <div style={{ fontSize: 80 }}>🕯️</div>

        {/* Type label */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <div
            style={{
              fontSize: 20,
              color: "#a1a1aa",
              letterSpacing: "0.2em",
              textTransform: "uppercase",
            }}
          >
            투자 체질
          </div>
          <div
            style={{
              fontSize: 72,
              fontWeight: 800,
              color: "#f59e0b",
              letterSpacing: "-0.02em",
            }}
          >
            {investorType}
          </div>
        </div>

        {/* Divider */}
        <div
          style={{
            width: 80,
            height: 2,
            background: "#52525b",
          }}
        />

        {/* Brand */}
        <div
          style={{
            fontSize: 28,
            color: "#71717a",
            letterSpacing: "0.1em",
          }}
        >
          사주캔들
        </div>

        {/* Subtitle */}
        <div
          style={{
            fontSize: 22,
            color: "#52525b",
          }}
        >
          사주로 읽는 나의 투자 체질
        </div>
      </div>
    ),
    { ...size }
  );
}
