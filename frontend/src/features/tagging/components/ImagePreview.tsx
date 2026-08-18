import { useRef, type PointerEvent } from 'react';
import { ImageOff } from 'lucide-react';

import type { FurnitureObject, UploadedImage } from '@/features/tagging/types';
import { cn } from '@/lib/utils';

interface ImagePreviewProps {
  image?: UploadedImage;
  isEditing?: boolean;
  hoveredObjectId?: string;
  onObjectBboxChange?: (
    updates: Array<Pick<FurnitureObject, 'bbox' | 'id'>>,
  ) => void;
  onObjectHover?: (objectId?: string) => void;
  onObjectToggle?: (object: FurnitureObject) => void;
  objects?: FurnitureObject[];
  selectedObjectIds?: string[];
  showBoxes?: boolean;
  showOnlySelectedBoxes?: boolean;
}

type PointerOperation =
  | {
      kind: 'move';
      objectId: string;
      originX: number;
      originY: number;
      startBboxes: Map<string, FurnitureObject['bbox']>;
    }
  | {
      kind: 'resize';
      objectId: string;
      originX: number;
      originY: number;
      startBbox: FurnitureObject['bbox'];
    };

const MINIMUM_BOX_LENGTH = 45;

const clamp = (value: number, minimum: number, maximum: number): number =>
  Math.min(maximum, Math.max(minimum, value));

const moveBox = (
  bbox: FurnitureObject['bbox'],
  deltaX: number,
  deltaY: number,
): FurnitureObject['bbox'] => {
  const [ymin, xmin, ymax, xmax] = bbox;
  const width = xmax - xmin;
  const height = ymax - ymin;
  const nextXmin = clamp(xmin + deltaX, 0, 1000 - width);
  const nextYmin = clamp(ymin + deltaY, 0, 1000 - height);
  return [nextYmin, nextXmin, nextYmin + height, nextXmin + width];
};

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
          left: `${(-xmin / 1000 / cropWidth) * 100}%`,
          top: `${(-ymin / 1000 / cropHeight) * 100}%`,
          width: `${100 / cropWidth}%`,
        }}
      />
    </div>
  );
};

export const ImagePreview = ({
  image,
  hoveredObjectId,
  isEditing = false,
  onObjectBboxChange,
  onObjectHover,
  onObjectToggle,
  objects = [],
  selectedObjectIds = [],
  showBoxes = false,
  showOnlySelectedBoxes = false,
}: ImagePreviewProps) => {
  const previewRef = useRef<HTMLDivElement>(null);
  const operationRef = useRef<PointerOperation | undefined>(undefined);
  const suppressBoxClickRef = useRef(false);

  const getPointerPosition = (event: PointerEvent<HTMLDivElement>) => {
    const bounds = previewRef.current?.getBoundingClientRect();
    if (!bounds) return null;
    return {
      x: ((event.clientX - bounds.left) / bounds.width) * 1000,
      y: ((event.clientY - bounds.top) / bounds.height) * 1000,
    };
  };

  const handleMoveStart = (
    event: PointerEvent<HTMLDivElement>,
    object: FurnitureObject,
  ) => {
    if (!isEditing || !selectedObjectIds.includes(object.id)) return;
    const point = getPointerPosition(event);
    if (!point) return;
    event.preventDefault();
    event.stopPropagation();
    suppressBoxClickRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    operationRef.current = {
      kind: 'move',
      objectId: object.id,
      originX: point.x,
      originY: point.y,
      startBboxes: new Map(
        objects
          .filter((item) => selectedObjectIds.includes(item.id))
          .map((item) => [item.id, item.bbox]),
      ),
    };
  };

  const handleResizeStart = (
    event: PointerEvent<HTMLButtonElement>,
    object: FurnitureObject,
  ) => {
    if (!isEditing) return;
    const bounds = previewRef.current?.getBoundingClientRect();
    if (!bounds) return;
    event.preventDefault();
    event.stopPropagation();
    suppressBoxClickRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    operationRef.current = {
      kind: 'resize',
      objectId: object.id,
      originX: ((event.clientX - bounds.left) / bounds.width) * 1000,
      originY: ((event.clientY - bounds.top) / bounds.height) * 1000,
      startBbox: object.bbox,
    };
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const operation = operationRef.current;
    const point = getPointerPosition(event);
    if (!operation || !point || !onObjectBboxChange) return;

    if (operation.kind === 'move') {
      const deltaX = point.x - operation.originX;
      const deltaY = point.y - operation.originY;
      onObjectBboxChange(
        [...operation.startBboxes].map(([id, bbox]) => ({
          bbox: moveBox(bbox, deltaX, deltaY),
          id,
        })),
      );
      return;
    }

    const [ymin, xmin] = operation.startBbox;
    onObjectBboxChange([
      {
        bbox: [
          ymin,
          xmin,
          clamp(point.y, ymin + MINIMUM_BOX_LENGTH, 1000),
          clamp(point.x, xmin + MINIMUM_BOX_LENGTH, 1000),
        ],
        id: operation.objectId,
      },
    ]);
  };

  const handlePointerOperationEnd = () => {
    operationRef.current = undefined;
  };

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
    <div className="rounded-xl bg-neutral-100 p-8 sm:p-9">
      <div
        className="relative"
        data-image-preview
        onPointerCancel={handlePointerOperationEnd}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerOperationEnd}
        ref={previewRef}
      >
        <img
          alt={image.name}
          className="block h-auto w-full rounded-lg"
          src={image.previewUrl}
        />
        {showBoxes
          ? objects
              .filter((object) => {
                if (!isEditing && hoveredObjectId) {
                  return object.id === hoveredObjectId;
                }

                return (
                  !showOnlySelectedBoxes ||
                  selectedObjectIds.includes(object.id)
                );
              })
              .map((object) => {
                const [ymin, xmin, ymax, xmax] = object.bbox;
                return (
                  <div
                    className={cn(
                      'detection-box',
                      isEditing &&
                        selectedObjectIds.includes(object.id) &&
                        'detection-box-selected',
                      hoveredObjectId === object.id &&
                        'detection-box-hovered',
                      isEditing && 'detection-box-editing',
                    )}
                    key={object.id}
                    onMouseEnter={() => onObjectHover?.(object.id)}
                    onMouseLeave={() => onObjectHover?.(undefined)}
                    onClick={() => {
                      if (suppressBoxClickRef.current) {
                        suppressBoxClickRef.current = false;
                        return;
                      }
                      onObjectToggle?.(object);
                    }}
                    onPointerDown={(event) => handleMoveStart(event, object)}
                    role="button"
                    tabIndex={0}
                    style={{
                      height: `${Math.max(1, (ymax - ymin) / 10)}%`,
                      left: `${xmin / 10}%`,
                      top: `${ymin / 10}%`,
                      width: `${Math.max(1, (xmax - xmin) / 10)}%`,
                    }}
                  >
                    <span>{object.name}</span>
                    {isEditing && selectedObjectIds.includes(object.id) ? (
                      <button
                        aria-label={`${object.name} 영역 크기 조정`}
                        className="detection-box-resize-handle"
                        onPointerDown={(event) =>
                          handleResizeStart(event, object)
                        }
                        type="button"
                      />
                    ) : null}
                  </div>
                );
              })
          : null}
      </div>
    </div>
  );
};
