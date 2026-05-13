declare global {
  interface Window {
    Kakao?: {
      init: (key: string) => void;
      isInitialized: () => boolean;
      Share: {
        sendDefault: (opts: Record<string, unknown>) => void;
      };
    };
  }
}

export function shareKakao(shareUrl: string, title: string, description: string, imageUrl?: string) {
  if (typeof window === "undefined") return;

  const kakaoKey = process.env.NEXT_PUBLIC_KAKAO_JS_KEY;

  // Try Kakao SDK if available and key provided
  if (kakaoKey && window.Kakao) {
    try {
      if (!window.Kakao.isInitialized()) {
        window.Kakao.init(kakaoKey);
      }
      window.Kakao.Share.sendDefault({
        objectType: "feed",
        content: {
          title,
          description,
          imageUrl: imageUrl ?? `${window.location.origin}/og-default.png`,
          link: {
            mobileWebUrl: shareUrl,
            webUrl: shareUrl,
          },
        },
        buttons: [
          {
            title: "나도 확인하기",
            link: {
              mobileWebUrl: shareUrl,
              webUrl: shareUrl,
            },
          },
        ],
      });
      return;
    } catch {
      // Fall through to Web Share API
    }
  }

  // Web Share API fallback
  if (navigator.share) {
    navigator
      .share({
        title,
        text: description,
        url: shareUrl,
      })
      .catch(() => {
        // User cancelled or error — silently ignore
      });
    return;
  }

  // Last resort: clipboard copy
  navigator.clipboard
    .writeText(shareUrl)
    .then(() => alert("링크가 복사되었습니다."))
    .catch(() => alert(`공유 링크: ${shareUrl}`));
}
