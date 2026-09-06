import { useState } from 'react';
import { ImageOff } from 'lucide-react';

type HistorySkuThumbnailProps = {
  alt: string;
  imageUrl: string | null;
};

/** 확정 SKU 이미지를 목록의 태깅 객체 식별용 썸네일로 표시합니다. */
export const HistorySkuThumbnail = ({
  alt,
  imageUrl,
}: HistorySkuThumbnailProps) => {
  const [hasFailed, setHasFailed] = useState(false);

  if (!imageUrl || hasFailed) {
    return (
      <div
        aria-label="SKU 썸네일을 불러올 수 없습니다"
        className="flex size-20 shrink-0 items-center justify-center rounded-lg bg-neutral-100 text-text-secondary"
        role="img"
      >
        <ImageOff size={20} />
      </div>
    );
  }

  return (
    <img
      alt={alt}
      className="size-20 shrink-0 rounded-lg border border-neutral-200 object-cover"
      onError={() => setHasFailed(true)}
      src={imageUrl}
    />
  );
};
