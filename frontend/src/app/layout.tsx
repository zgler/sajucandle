import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "사주캔들 — 사주로 읽는 투자 체질",
  description: "명리학 기반 투자 체질 분석. 매일 매매 기운과 월간 시그널을 확인하세요.",
  keywords: ["사주", "투자", "명리", "주식", "코인", "운세"],
  openGraph: {
    title: "사주캔들",
    description: "사주로 읽는 나의 투자 체질",
    type: "website",
    locale: "ko_KR",
  },
  twitter: {
    card: "summary_large_image",
    title: "사주캔들",
    description: "사주로 읽는 나의 투자 체질",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: "#09090b",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" className="h-full">
      <head>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
        />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;700;900&display=swap"
        />
      </head>
      <body className="min-h-full bg-zinc-950 text-zinc-100 antialiased">
        <div className="max-w-md mx-auto min-h-screen">{children}</div>
      </body>
    </html>
  );
}
