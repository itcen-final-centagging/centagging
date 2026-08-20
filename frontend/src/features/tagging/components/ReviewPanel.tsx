import { useState } from 'react';
import { ArrowLeft, ArrowRight, Check, Save, Sparkles } from 'lucide-react';

import { Button } from '@/commons/components/Button';
import { FurnitureArtwork } from '@/features/tagging/components/FurnitureArtwork';
import { ImagePreview } from '@/features/tagging/components/ImagePreview';
import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';
import type {
  FurnitureObject,
  SkuCandidate,
  TaggingValues,
} from '@/features/tagging/types';
import { cn } from '@/lib/utils';

const CATEGORIES = ['소파', '의자', '테이블·식탁·책상', '서랍·수납장', '침대'];
const COLORS = ['그레이', '베이지', '화이트', '블랙', '브라운'];
const MATERIALS = ['패브릭', '가죽', '원목', '메탈', '플라스틱'];
const STYLE_TAGS = [
  'null',
  '모던',
  '미니멀',
  '내추럴',
  '컨템포러리',
  '라운드',
  '패브릭',
];

interface MetadataRowProps {
  label: string;
  value: string;
}

const MetadataRow = ({ label, value }: MetadataRowProps) => (
  <div className="flex items-center justify-between border-b border-neutral-100 py-3 last:border-b-0">
    <span className="text-xs text-neutral-500">{label}</span>
    <span className="max-w-[65%] text-right text-xs font-bold text-neutral-700">
      {value}
    </span>
  </div>
);

const getMetadataText = (
  attributes: Record<string, unknown> | undefined,
  key: string,
  fallback: string,
): string => {
  const value = attributes?.[key];
  return typeof value === 'string' && value ? value : fallback;
};

/** 아직 검수하지 않은 객체에 보여줄 초기 태깅 값을 만듭니다. */
const buildDefaultValues = (
  object: FurnitureObject,
  sku: SkuCandidate,
): TaggingValues => ({
  category: object.metadata.category ?? sku.category ?? 'null',
  color: getMetadataText(
    object.metadata.attributes,
    'color',
    sku.color ?? 'null',
  ),
  material: getMetadataText(
    object.metadata.attributes,
    'material',
    sku.material ?? 'null',
  ),
  mood: object.metadata.description ?? 'null',
  styleTags: object.metadata.keyFeatures.length
    ? object.metadata.keyFeatures.slice(0, 3)
    : ['null'],
});

export const ReviewPanel = () => {
  const {
    changeStage,
    confirmedSelections,
    saveTagging,
    selectObject,
    uploadedImage,
  } = useTaggingWorkflow();

  // 추천 단계에서 마지막으로 선택된 객체가 아니라 항상 첫 객체부터 검수합니다.
  const [currentObjectId, setCurrentObjectId] = useState<string>();

  // 검수 값은 객체별로 보관해, 목록에서 객체를 오가도 입력이 유지됩니다.
  const [valuesByObject, setValuesByObject] = useState<
    Record<string, TaggingValues>
  >({});
  // 객체별 검수 완료 여부입니다. 전부 완료해야 저장할 수 있습니다.
  const [reviewedIds, setReviewedIds] = useState<Record<string, boolean>>({});

  if (confirmedSelections.length === 0) return null;

  const currentIndex = Math.max(
    confirmedSelections.findIndex(
      ({ object }) => object.id === currentObjectId,
    ),
    0,
  );
  const { object: currentObject, sku: currentSku } =
    confirmedSelections[currentIndex];
  const values =
    valuesByObject[currentObject.id] ??
    buildDefaultValues(currentObject, currentSku);
  const isReviewed = reviewedIds[currentObject.id] === true;
  const reviewedCount = confirmedSelections.filter(
    ({ object }) => reviewedIds[object.id],
  ).length;
  const isAllReviewed = reviewedCount === confirmedSelections.length;
  const isLastObject = currentIndex === confirmedSelections.length - 1;

  const handleChangeValue = <Key extends keyof TaggingValues>(
    key: Key,
    value: TaggingValues[Key],
  ): void => {
    setValuesByObject((currentValues) => {
      const base =
        currentValues[currentObject.id] ??
        buildDefaultValues(currentObject, currentSku);
      return {
        ...currentValues,
        [currentObject.id]: { ...base, [key]: value },
      };
    });
  };

  const handleToggleTag = (tag: string): void => {
    handleChangeValue(
      'styleTags',
      values.styleTags.includes(tag)
        ? values.styleTags.filter((currentTag) => currentTag !== tag)
        : [...values.styleTags, tag],
    );
  };

  const handleSkuSelectionReturn = (): void => {
    changeStage('recommend');
  };

  const handleToggleReviewed = (): void => {
    setReviewedIds((current) => ({
      ...current,
      [currentObject.id]: !current[currentObject.id],
    }));
  };

  const handleSelectObject = (object: FurnitureObject): void => {
    setCurrentObjectId(object.id);
    selectObject(object);
  };

  const handleNextObject = (): void => {
    const nextSelection = confirmedSelections[currentIndex + 1];
    if (nextSelection) handleSelectObject(nextSelection.object);
  };

  const handleTaggingSave = (): void => {
    if (!isAllReviewed) return;
    void saveTagging(
      Object.fromEntries(
        confirmedSelections.map(({ object, sku }) => [
          object.id,
          valuesByObject[object.id] ?? buildDefaultValues(object, sku),
        ]),
      ),
    );
  };

  return (
    <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(320px,1.12fr)]">
      <article className="col-span-full studio-surface p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-extrabold text-neutral-800">
              확정한 객체 · SKU
            </h2>
            <p className="mt-1.5 text-sm text-neutral-500">
              객체를 하나씩 선택해 태깅 정보를 확인하고 검수를 완료해 주세요.
            </p>
          </div>
          <span
            className={cn(
              'rounded-full px-2.5 py-1 text-xs font-bold',
              isAllReviewed
                ? 'bg-success-50 text-success-600'
                : 'bg-neutral-100 text-neutral-500',
            )}
          >
            검수 {reviewedCount} / {confirmedSelections.length}
          </span>
        </div>
        <ul className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {confirmedSelections.map(({ object, sku }) => {
            const isSelected = object.id === currentObject.id;
            return (
              <li key={object.id}>
                <button
                  aria-current={isSelected}
                  className={cn(
                    'flex w-full min-w-0 items-center gap-3 rounded-lg border p-3 text-left transition-colors',
                    isSelected
                      ? 'border-primary-300 bg-primary-20 ring-3 ring-primary-50'
                      : 'border-border bg-bg-primary hover:bg-neutral-50',
                  )}
                  onClick={() => handleSelectObject(object)}
                  type="button"
                >
                  <FurnitureArtwork
                    className="h-12 w-12 shrink-0"
                    imageUrl={sku.imageUrl}
                    kind={sku.kind}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <span className="truncate text-sm font-bold text-text-primary">
                        {object.name}
                      </span>
                      {reviewedIds[object.id] ? (
                        <Check
                          className="shrink-0 text-success-600"
                          size={14}
                        />
                      ) : null}
                    </span>
                    <span className="mt-1 block truncate font-mono text-[11px] font-bold text-text-tertiary">
                      {sku.sku}
                    </span>
                    <span className="mt-1 block truncate text-xs text-text-secondary">
                      {sku.name}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </article>
      <article className="studio-surface p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-base font-extrabold text-neutral-800">
            현재 선택 객체
          </h2>
          <span className="shrink-0 rounded-full bg-neutral-100 px-2.5 py-1 text-xs font-bold text-neutral-500">
            {currentIndex + 1} / {confirmedSelections.length}
          </span>
        </div>
        <p className="mt-4 text-xs font-bold text-neutral-500">원본 이미지</p>
        <div className="mt-2">
          <ImagePreview
            image={uploadedImage}
            objects={[currentObject]}
            selectedObjectIds={[currentObject.id]}
            showBoxes
          />
        </div>
        <p className="mt-4 text-xs font-bold text-neutral-500">
          AI가 추출한 객체
        </p>
        <FurnitureArtwork
          className="mt-2"
          imageUrl={currentSku.imageUrl}
          kind={currentSku.kind}
        />
        <p className="mt-2 text-sm font-bold text-neutral-700">
          {currentObject.name}
        </p>
      </article>
      <article className="studio-surface p-5">
        <h2 className="text-base font-extrabold text-neutral-800">선택 SKU</h2>
        <FurnitureArtwork
          className="mt-4"
          imageUrl={currentSku.imageUrl}
          kind={currentSku.kind}
        />
        <p className="mt-4 font-mono text-xs font-bold text-neutral-400">
          {currentSku.sku}
        </p>
        <p className="mt-1 text-base font-extrabold text-neutral-800">
          {currentSku.name}
        </p>
        <dl className="mt-4">
          <MetadataRow label="카테고리" value={values.category} />
          <MetadataRow label="색상" value={currentSku.color ?? 'null'} />
          <MetadataRow label="소재" value={currentSku.material ?? 'null'} />
          <MetadataRow label="규격" value={currentSku.size ?? 'null'} />
        </dl>
      </article>
      <article className="studio-surface p-5">
        <h2 className="text-base font-extrabold text-neutral-800">
          AI 태깅 정보
        </h2>
        <p className="mt-1.5 text-sm text-neutral-500">
          필수 태그를 확인하고 필요한 경우 수정해 주세요.
        </p>
        <div className="mt-5 grid gap-4 sm:grid-cols-3 xl:grid-cols-1">
          <label className="text-sm font-bold text-neutral-700">
            가구 카테고리
            <select
              className="mt-2 h-10 w-full rounded-md border border-neutral-200 bg-white px-3 text-sm font-normal outline-none focus:border-primary focus:ring-3 focus:ring-primary-50"
              onChange={(event) =>
                handleChangeValue('category', event.target.value)
              }
              value={values.category}
            >
              <option value="null">null</option>
              {CATEGORIES.map((category) => (
                <option key={category}>{category}</option>
              ))}
            </select>
          </label>
          <label className="text-sm font-bold text-neutral-700">
            대표 색상
            <select
              className="mt-2 h-10 w-full rounded-md border border-neutral-200 bg-white px-3 text-sm font-normal outline-none focus:border-primary focus:ring-3 focus:ring-primary-50"
              onChange={(event) =>
                handleChangeValue('color', event.target.value)
              }
              value={values.color}
            >
              <option value="null">null</option>
              {COLORS.map((color) => (
                <option key={color}>{color}</option>
              ))}
            </select>
          </label>
          <label className="text-sm font-bold text-neutral-700">
            주요 소재
            <select
              className="mt-2 h-10 w-full rounded-md border border-neutral-200 bg-white px-3 text-sm font-normal outline-none focus:border-primary focus:ring-3 focus:ring-primary-50"
              onChange={(event) =>
                handleChangeValue('material', event.target.value)
              }
              value={values.material}
            >
              <option value="null">null</option>
              {MATERIALS.map((material) => (
                <option key={material}>{material}</option>
              ))}
            </select>
          </label>
        </div>
        <fieldset className="mt-5">
          <legend className="text-sm font-bold text-neutral-700">
            스타일 태그
          </legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {STYLE_TAGS.map((tag) => {
              const isSelected = values.styleTags.includes(tag);
              return (
                <button
                  className={cn(
                    'rounded-full border px-3 py-1.5 text-xs font-bold transition-colors',
                    isSelected
                      ? 'border-primary-300 bg-primary-20 text-primary-700'
                      : 'border-neutral-200 bg-white text-neutral-500 hover:bg-neutral-50',
                  )}
                  key={tag}
                  onClick={() => handleToggleTag(tag)}
                  type="button"
                >
                  {isSelected ? (
                    <Check className="mr-1 inline" size={12} />
                  ) : null}
                  {tag}
                </button>
              );
            })}
          </div>
        </fieldset>
        <label className="mt-5 block text-sm font-bold text-neutral-700">
          공간 분위기
          <textarea
            className="mt-2 min-h-21 w-full resize-y rounded-md border border-neutral-200 bg-white p-3 text-sm font-normal outline-none focus:border-primary focus:ring-3 focus:ring-primary-50"
            maxLength={100}
            onChange={(event) => handleChangeValue('mood', event.target.value)}
            value={values.mood}
          />
        </label>
      </article>
      <div className="col-span-full flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
        <Button
          onClick={handleSkuSelectionReturn}
          startDecorator={<ArrowLeft size={17} />}
          variant="neutral-outlined"
        >
          SKU 확정 목록으로
        </Button>
        <div className="grid gap-3 sm:flex">
          <Button
            onClick={handleToggleReviewed}
            startDecorator={
              isReviewed ? <Check size={17} /> : <Sparkles size={17} />
            }
            variant={isReviewed ? 'neutral-outlined' : 'primary-solid'}
          >
            {isReviewed ? '검수 완료됨' : '이 객체 검수 완료'}
          </Button>
          {isLastObject ? null : (
            <Button
              disabled={!isReviewed}
              endDecorator={<ArrowRight size={17} />}
              onClick={handleNextObject}
              variant="neutral-outlined"
            >
              다음 객체 검수
            </Button>
          )}
          <Button
            disabled={!isAllReviewed}
            endDecorator={<Save size={17} />}
            onClick={handleTaggingSave}
          >
            {isAllReviewed
              ? `${confirmedSelections.length}개 객체 태깅 저장`
              : `검수 ${reviewedCount} / ${confirmedSelections.length}`}
          </Button>
        </div>
      </div>
    </section>
  );
};
