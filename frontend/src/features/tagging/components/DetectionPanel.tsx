import { ArrowRight, CheckCircle2, Sparkles } from 'lucide-react';

import { Button } from '@/commons/components/Button';
import { ImagePreview } from '@/features/tagging/components/ImagePreview';
import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';
import { cn } from '@/lib/utils';

export const DetectionPanel = () => {
  const {
    changeStage,
    detectedObjects,
    selectObject,
    selectedObject,
    uploadedImage,
  } = useTaggingWorkflow();

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_380px]">
      <section className="studio-surface p-5">
        <h2 className="mb-3 text-base font-extrabold text-neutral-800">
          탐지된 가구 영역
        </h2>
        <ImagePreview
          image={uploadedImage}
          objects={detectedObjects}
          selectedObject={selectedObject}
          showBoxes
        />
        <p className="mt-2.5 text-xs leading-5 text-neutral-400">
          파란 테두리는 AI가 감지한 객체입니다. 목록을 선택하면 해당 객체가
          강조됩니다.
        </p>
      </section>
      <section className="studio-surface p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-extrabold text-neutral-800">
            탐지 결과
          </h2>
          <span className="rounded-full bg-success-50 px-2 py-1 text-xs font-bold text-success-600">
            {detectedObjects.length}개
          </span>
        </div>
        <p className="mt-1.5 text-sm text-neutral-500">
          신뢰도 50% 이상인 가구만 표시합니다.
        </p>
        <div className="mt-4 space-y-3">
          {detectedObjects.map((object) => {
            const isSelected = selectedObject?.id === object.id;
            return (
              <button
                className={cn(
                  'w-full rounded-lg border p-4 text-left transition-colors',
                  isSelected
                    ? 'border-blue-500 bg-blue-50 shadow-[0_0_0_2px_#dbeafe]'
                    : 'border-border bg-bg-primary hover:border-blue-300 hover:bg-bg-hover',
                )}
                key={object.id}
                onClick={() => selectObject(object)}
                type="button"
              >
                <span className="flex items-start justify-between gap-3">
                  <span>
                    <span className="block text-sm font-extrabold text-neutral-800">
                      {object.name}
                    </span>
                    <span className="mt-1 block text-xs text-neutral-500">
                      {object.description}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-1 rounded-full bg-success-50 px-2 py-1 text-[11px] font-bold text-success-600">
                    {isSelected ? (
                      <CheckCircle2 size={12} />
                    ) : (
                      <Sparkles size={12} />
                    )}
                    {object.confidence}%
                  </span>
                </span>
              </button>
            );
          })}
        </div>
        <Button
          className="mt-5"
          disabled={!selectedObject}
          endDecorator={<ArrowRight size={17} />}
          fullWidth
          onClick={() => changeStage('recommend')}
          size="lg"
        >
          유사 SKU 찾기
        </Button>
      </section>
    </div>
  );
};
