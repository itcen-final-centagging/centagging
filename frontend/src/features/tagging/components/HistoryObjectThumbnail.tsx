import { useEffect, useState } from 'react';
import { ImageOff } from 'lucide-react';

import type { HistoryBoundingBox } from '@/features/tagging/types';

const THUMBNAIL_SIZE = 160;

type HistoryObjectThumbnailProps = {
  alt: string;
  bbox: HistoryBoundingBox | null;
  imageUrl: string | null;
};

/** 연출 이미지의 0~1000 정규화 bbox 영역만 캔버스에 그려 목록 썸네일로 만듭니다. */
export const HistoryObjectThumbnail = ({
  alt,
  bbox,
  imageUrl,
}: HistoryObjectThumbnailProps) => {
  const [thumbnailUrl, setThumbnailUrl] = useState<string>();
  const [hasFailed, setHasFailed] = useState(false);

  useEffect(() => {
    if (!imageUrl || !bbox) {
      setThumbnailUrl(undefined);
      setHasFailed(true);
      return;
    }

    let isActive = true;
    const image = new Image();
    image.onload = () => {
      const sourceWidth = ((bbox.xmax - bbox.xmin) / 1000) * image.naturalWidth;
      const sourceHeight =
        ((bbox.ymax - bbox.ymin) / 1000) * image.naturalHeight;
      if (sourceWidth <= 0 || sourceHeight <= 0) {
        if (isActive) setHasFailed(true);
        return;
      }

      const canvas = document.createElement('canvas');
      canvas.width = THUMBNAIL_SIZE;
      canvas.height = THUMBNAIL_SIZE;
      const context = canvas.getContext('2d');
      if (!context) {
        if (isActive) setHasFailed(true);
        return;
      }

      const scale = Math.min(
        THUMBNAIL_SIZE / sourceWidth,
        THUMBNAIL_SIZE / sourceHeight,
      );
      const width = sourceWidth * scale;
      const height = sourceHeight * scale;
      context.fillStyle = '#f5f5f5';
      context.fillRect(0, 0, THUMBNAIL_SIZE, THUMBNAIL_SIZE);
      context.drawImage(
        image,
        (bbox.xmin / 1000) * image.naturalWidth,
        (bbox.ymin / 1000) * image.naturalHeight,
        sourceWidth,
        sourceHeight,
        (THUMBNAIL_SIZE - width) / 2,
        (THUMBNAIL_SIZE - height) / 2,
        width,
        height,
      );

      try {
        if (isActive) {
          setThumbnailUrl(canvas.toDataURL('image/jpeg', 0.9));
          setHasFailed(false);
        }
      } catch {
        if (isActive) setHasFailed(true);
      }
    };
    image.onerror = () => {
      if (isActive) setHasFailed(true);
    };
    image.src = imageUrl;

    return () => {
      isActive = false;
    };
  }, [bbox, imageUrl]);

  if (hasFailed || !thumbnailUrl) {
    return (
      <div
        aria-label="가구 썸네일을 불러올 수 없습니다"
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
      className="size-20 shrink-0 rounded-lg border border-neutral-200 object-contain"
      src={thumbnailUrl}
    />
  );
};
