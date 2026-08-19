import { useMemo, useState } from 'react';
import {
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react';

import { Button } from '@/commons/components/Button';
import { ImagePreview } from '@/features/tagging/components/ImagePreview';
import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';
import { cn } from '@/lib/utils';

const CATEGORY_SUGGESTIONS = [
  '소파',
  '의자',
  '테이블·식탁·책상',
  '수납장',
  '침대',
  '조명',
  '기타 가구',
];
const RESULTS_PER_PAGE = 5;

export const DetectionPanel = () => {
  const [page, setPage] = useState(1);
  const {
    addObject,
    deleteObject,
    detectedObjects,
    finishEditing,
    focusObjectForEditing,
    isEditing,
    isRecommendationLoading,
    loadSelectedObjectRecommendations,
    selectedObjectIds,
    startEditing,
    toggleObjectSelection,
    updateObjectBboxes,
    updateObjectCategory,
    uploadedImage,
  } = useTaggingWorkflow();
  const totalPages = Math.max(
    1,
    Math.ceil(detectedObjects.length / RESULTS_PER_PAGE),
  );
  const currentPage = Math.min(page, totalPages);
  const visibleObjects = useMemo(() => {
    const start = (currentPage - 1) * RESULTS_PER_PAGE;
    return detectedObjects.slice(start, start + RESULTS_PER_PAGE);
  }, [currentPage, detectedObjects]);

  const handleObjectCardClick = (object: (typeof visibleObjects)[number]) => {
    if (isEditing) focusObjectForEditing(object);
  };

  const handleObjectToggle = (object: (typeof visibleObjects)[number]) => {
    toggleObjectSelection(object);
  };

  const handleCategoryChange = (
    object: (typeof visibleObjects)[number],
    category: string,
  ) => {
    focusObjectForEditing(object);
    updateObjectCategory(object.id, category);
  };

  const handlePreviousPage = (): void => {
    setPage(currentPage - 1);
  };

  const handleNextPage = (): void => {
    setPage(currentPage + 1);
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_380px]">
      <section className="studio-surface p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-extrabold text-neutral-800">
              탐지된 가구 영역
            </h2>
            <p className="mt-1 text-xs leading-5 text-neutral-400">
              {isEditing
                ? '편집할 객체를 고르면 해당 박스만 표시됩니다. 박스를 드래그하거나 오른쪽 아래 원으로 크기를 조정하세요.'
                : '박스나 목록을 눌러 여러 객체를 선택할 수 있습니다.'}
            </p>
          </div>
          {isEditing ? (
            <Button
              onClick={finishEditing}
              size="sm"
              startDecorator={<Check size={15} />}
            >
              편집 완료
            </Button>
          ) : (
            <Button
              onClick={startEditing}
              size="sm"
              startDecorator={<Pencil size={15} />}
            >
              편집
            </Button>
          )}
        </div>
        <ImagePreview
          image={uploadedImage}
          isEditing={isEditing}
          objects={detectedObjects}
          onObjectBboxChange={updateObjectBboxes}
          onObjectToggle={toggleObjectSelection}
          selectedObjectIds={selectedObjectIds}
          showBoxes
          showOnlySelectedBoxes={isEditing}
        />
      </section>

      <section className="studio-surface flex min-h-0 flex-col p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-extrabold text-neutral-800">
              탐지 결과
            </h2>
            <p className="mt-1.5 text-sm text-neutral-500">
              {isEditing
                ? '객체별 카테고리를 수정하거나 불필요한 박스를 삭제할 수 있습니다.'
                : '탐지 근거와 신뢰도를 확인해 편집할 객체를 선택하세요.'}
            </p>
          </div>
        </div>

        {isEditing ? (
          <Button
            className="mt-4"
            fullWidth
            onClick={addObject}
            size="sm"
            startDecorator={<Plus size={15} />}
            variant="primary-outlined"
          >
            새 박스 추가
          </Button>
        ) : null}

        <div className="mt-4 min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {visibleObjects.map((object) => {
            const isSelected = selectedObjectIds.includes(object.id);
            return (
              <article
                className={cn(
                  'rounded-lg border p-4 transition-colors',
                  isEditing && 'cursor-pointer',
                  isSelected
                    ? 'border-blue-500 bg-blue-50 shadow-[0_0_0_2px_#dbeafe]'
                    : 'border-border bg-bg-primary hover:border-blue-300 hover:bg-bg-hover',
                )}
                key={object.id}
                onClick={() => handleObjectCardClick(object)}
              >
                <button
                  aria-pressed={isSelected}
                  className="w-full text-left"
                  onClick={() => handleObjectToggle(object)}
                  type="button"
                >
                  <span className="flex items-start justify-between gap-3">
                    <span>
                      <span className="block text-sm font-extrabold text-neutral-800">
                        {object.name}
                      </span>
                      <span className="mt-1 block text-xs text-neutral-500">
                        {object.description ?? '탐지 근거 정보가 없습니다.'}
                      </span>
                    </span>
                    <span className="shrink-0 rounded-full bg-success-50 px-2 py-1 text-[11px] font-bold text-success-600">
                      {object.confidence === null
                        ? '신뢰도 미제공'
                        : `${object.confidence}%`}
                    </span>
                  </span>
                </button>

                {!isEditing ? (
                  <details className="mt-3 border-t border-neutral-100 pt-3 text-xs text-text-secondary">
                    <summary className="cursor-pointer font-semibold text-blue-700">
                      탐지 근거 · 신뢰도 확인
                    </summary>
                    <p className="mt-2 leading-5">
                      {object.description ??
                        '탐지 API가 근거 설명을 제공하지 않았습니다.'}
                    </p>
                    <p className="mt-1 text-text-tertiary">
                      신뢰도:{' '}
                      {object.confidence === null
                        ? '제공되지 않음'
                        : `${object.confidence}%`}
                    </p>
                  </details>
                ) : null}

                {isEditing ? (
                  <div className="mt-3 grid grid-cols-[minmax(0,1fr)_auto] gap-2 border-t border-blue-100 pt-3">
                    <label
                      className="sr-only"
                      htmlFor={`category-${object.id}`}
                    >
                      {object.name} 카테고리
                    </label>
                    <select
                      className="min-w-0 rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm font-semibold text-text-primary outline-none focus:border-blue-500"
                      id={`category-${object.id}`}
                      onChange={(event) =>
                        handleCategoryChange(object, event.target.value)
                      }
                      onFocus={() => focusObjectForEditing(object)}
                      value={object.category ?? object.name}
                    >
                      {!CATEGORY_SUGGESTIONS.includes(
                        object.category ?? object.name,
                      ) ? (
                        <option value={object.category ?? object.name}>
                          {object.category ?? object.name}
                        </option>
                      ) : null}
                      {CATEGORY_SUGGESTIONS.map((category) => (
                        <option key={category} value={category}>
                          {category}
                        </option>
                      ))}
                    </select>
                    <Button
                      aria-label={`${object.name} 삭제`}
                      onClick={() => deleteObject(object.id)}
                      size="sm"
                      variant="neutral-outlined"
                    >
                      <Trash2 size={15} />
                      삭제
                    </Button>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>

        {totalPages > 1 ? (
          <nav
            aria-label="탐지 결과 페이지"
            className="mt-4 flex items-center justify-center gap-2"
          >
            <Button
              aria-label="이전 탐지 결과 페이지"
              disabled={currentPage === 1}
              onClick={handlePreviousPage}
              size="sm"
              variant="neutral-outlined"
            >
              <ChevronLeft size={16} />
            </Button>
            <span className="min-w-14 text-center text-xs font-bold text-text-secondary">
              {currentPage} / {totalPages}
            </span>
            <Button
              aria-label="다음 탐지 결과 페이지"
              disabled={currentPage === totalPages}
              onClick={handleNextPage}
              size="sm"
              variant="neutral-outlined"
            >
              <ChevronRight size={16} />
            </Button>
          </nav>
        ) : null}

        <Button
          className="mt-5"
          disabled={
            isEditing || detectedObjects.length === 0 || isRecommendationLoading
          }
          endDecorator={<ArrowRight size={17} />}
          fullWidth
          onClick={() => void loadSelectedObjectRecommendations()}
          size="lg"
        >
          {isEditing
            ? '편집 완료 후 유사 SKU 찾기'
            : isRecommendationLoading
              ? '수정 객체 저장 및 SKU 조회 중'
              : '유사 SKU 찾기'}
        </Button>
      </section>
    </div>
  );
};
