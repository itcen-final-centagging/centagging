import { ImageOff } from 'lucide-react';

import type { FurnitureObject, UploadedImage } from '@/features/tagging/types';
import { cn } from '@/lib/utils';

interface ImagePreviewProps {
  image?: UploadedImage;
  objects?: FurnitureObject[];
  selectedObject?: FurnitureObject;
  showBoxes?: boolean;
}

interface ObjectCropPreviewProps {
  image?: UploadedImage;
  object?: FurnitureObject;
}

export const ObjectCropPreview = ({
  image,
  object,
}: ObjectCropPreviewProps) => {
  if (!image || !object) {
    return (
      <div className="flex aspect-square items-center justify-center rounded-lg bg-white text-xs text-text-quaternary">
        크롭 이미지 없음
      </div>
    );
  }

  const [ymin, xmin, ymax, xmax] = object.bbox;
  const cropWidth = Math.max(1, xmax - xmin) / 1000;
  const cropHeight = Math.max(1, ymax - ymin) / 1000;
  const aspectRatio = (cropWidth * image.width) / (cropHeight * image.height);

  return (
    <div
      className="relative overflow-hidden rounded-lg bg-white"
      style={{ aspectRatio: `${aspectRatio}` }}
    >
      <img
        alt={`${object.name} 크롭`}
        className="absolute max-w-none"
        src={image.previewUrl}
        style={{
          left: `${(-xmin / cropWidth) * 100}%`,
          top: `${(-ymin / cropHeight) * 100}%`,
          width: `${100 / cropWidth}%`,
        }}
      />
    </div>
  );
};

export const ImagePreview = ({
  image,
  objects = [],
  selectedObject,
  showBoxes = false,
}: ImagePreviewProps) => {
  if (!image) {
    return (
      <div className="flex min-h-[320px] flex-col items-center justify-center rounded-xl bg-gradient-to-br from-[#e8edf3] to-[#f8fafc] text-neutral-400">
        <ImageOff size={28} strokeWidth={1.75} />
        <p className="mt-3 text-sm">
          업로드한 연출 이미지가 이곳에 표시됩니다.
        </p>
      </div>
    );
  }

  return (
    <div className="relative overflow-hidden rounded-xl bg-neutral-100">
      <img
        alt={image.name}
        className="block max-h-[510px] min-h-[360px] w-full object-contain"
        src={image.previewUrl}
      />
      {showBoxes
        ? objects.map((object) => {
            const [ymin, xmin, ymax, xmax] = object.bbox;
            return (
              <div
                className={cn(
                  'detection-box',
                  selectedObject?.id === object.id && 'detection-box-selected',
                )}
                key={object.id}
                style={{
                  height: `${Math.max(1, (ymax - ymin) / 10)}%`,
                  left: `${xmin / 10}%`,
                  top: `${ymin / 10}%`,
                  width: `${Math.max(1, (xmax - xmin) / 10)}%`,
                }}
              >
                <span>{object.name}</span>
              </div>
            );
          })
        : null}
    </div>
  );
};
