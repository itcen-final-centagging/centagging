import { useMemo, useState } from 'react';
import {
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  Search,
  Sparkles,
} from 'lucide-react';

import { Button } from '@/commons/components/Button';
import { FurnitureArtwork } from '@/features/tagging/components/FurnitureArtwork';
import { ObjectCropPreview } from '@/features/tagging/components/ImagePreview';
import { ATTRIBUTE_LABELS } from '@/features/tagging/constants/skuAttributes';
import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';
import {
  buildSkuAttributeRows,
  formatAttributeValue,
} from '@/features/tagging/utils/skuAttributes';
import { cn } from '@/lib/utils';

const VERDICT_LABELS = {
  MATCH: '일치',
  MISMATCH: '불일치',
  UNKNOWN: '판단 불가',
} as const;

const VERDICT_STYLES = {
  MATCH: 'bg-emerald-50 text-emerald-700',
  MISMATCH: 'bg-rose-50 text-rose-700',
  UNKNOWN: 'bg-amber-50 text-amber-700',
} as const;

export const RecommendationPanel = () => {
  const {
    changeStage,
    confirmedSelections,
    detectedObjects,
    selectObject,
    selectSku,
    selectedObject,
    selectedSku,
    uploadedImage,
  } = useTaggingWorkflow();
  const recommendationObjects = useMemo(
    () => detectedObjects.filter((object) => object.candidates.length > 0),
    [detectedObjects],
  );
  const objectPage = Math.max(
    0,
    recommendationObjects.findIndex(
      (object) => object.id === selectedObject?.id,
    ),
  );
  const candidates = useMemo(
    () => selectedObject?.candidates ?? [],
    [selectedObject],
  );
  const [focusedSku, setFocusedSku] = useState(
    selectedSku?.sku ?? candidates[0]?.sku,
  );
  const focusedCandidate = useMemo(
    () =>
      candidates.find((candidate) => candidate.sku === focusedSku) ??
      candidates[0],
    [candidates, focusedSku],
  );

  if (!focusedCandidate) return null;

  const isConfirmed = selectedSku?.sku === focusedCandidate.sku;
  const metadataCriteria = (focusedCandidate.xaiResult?.criteria ?? []).filter(
    (criterion) => criterion.key,
  );
  const cropReadings = new Map(
    (selectedObject?.xaiReadings ?? []).map((reading) => [
      reading.key,
      reading,
    ]),
  );
  const verdictCounts = metadataCriteria.reduce(
    (counts, criterion) => {
      if (criterion.verdict) counts[criterion.verdict] += 1;
      return counts;
    },
    { MATCH: 0, MISMATCH: 0, UNKNOWN: 0 },
  );
  const similarity =
    focusedCandidate.metadataScore ?? focusedCandidate.score;
  const comparisonCount = metadataCriteria.length;
  const hasSimilarityResult =
    similarity !== null || comparisonCount > 0;
  const verdictPercentage = (
    verdict: keyof typeof VERDICT_LABELS,
  ): number =>
    comparisonCount === 0
      ? 0
      : (verdictCounts[verdict] / comparisonCount) * 100;

  // 소규모 배열 조합이라 useMemo 없이 매 렌더마다 계산해도 무방합니다.
  // (아래 return null 분기 뒤라 훅으로 두면 훅 규칙에 걸립니다.)
  const attributeRows = buildSkuAttributeRows(
    focusedCandidate,
    selectedObject?.category ?? null,
  );

  const completedObjectCount = confirmedSelections.filter(({ object }) =>
    recommendationObjects.some(
      (recommendationObject) => recommendationObject.id === object.id,
    ),
  ).length;
  const isFirstObject = objectPage === 0;
  const isLastObject = objectPage === recommendationObjects.length - 1;

  const handleObjectPageMove = (offset: number): void => {
    const nextObject = recommendationObjects[objectPage + offset];
    if (!nextObject) return;
    selectObject(nextObject);
    const nextSelection = confirmedSelections.find(
      ({ object }) => object.id === nextObject.id,
    );
    setFocusedSku(nextSelection?.sku.sku ?? nextObject.candidates[0]?.sku);
  };

  const handleCandidateFocus = (sku: string): void => {
    setFocusedSku(sku);
  };

  const handleCatalogSearchOpen = (): void => {
    changeStage('catalog');
  };

  const handlePreviousStage = (): void => {
    if (isFirstObject) {
      changeStage('detect');
      return;
    }
    handleObjectPageMove(-1);
  };

  const handleSkuConfirmation = (): void => {
    selectSku(focusedCandidate);
  };

  const handleNextObject = (): void => {
    if (isLastObject) {
      changeStage('review');
      return;
    }
    handleObjectPageMove(1);
  };

  return (
    <section>
      <div className="mb-4 flex flex-col gap-4 rounded-xl border border-border bg-bg-primary px-5 py-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-base font-extrabold text-neutral-800">
            SKU 처리 {objectPage + 1} / {recommendationObjects.length} ·{' '}
            {selectedObject?.category ?? '선택 객체'}
          </p>
          <p className="mt-1 text-xs leading-5 text-neutral-500">
            현재 객체의 후보를 확정하면 다음 객체의 SKU를 순서대로 처리합니다.{' '}
            후보 {candidates.length}건
          </p>
        </div>
        <span className="rounded-full bg-success-50 px-2.5 py-1 text-xs font-bold text-success-600">
          {completedObjectCount} / {recommendationObjects.length}개 확정
        </span>
      </div>

      <div className="grid overflow-hidden rounded-2xl border border-border bg-bg-primary shadow-[0_1px_3px_rgba(15,23,42,0.08)] xl:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="border-b border-border bg-bg-tertiary/70 p-3 xl:border-b-0 xl:border-r">
          <div className="mb-3 rounded-xl border border-primary-200 bg-primary-20 p-3">
            <p className="text-xs font-bold text-primary-700">
              원하는 SKU가 후보에 없나요?
            </p>
            <p className="mt-1 text-[11px] leading-4 text-primary-700/70">
              전체 카탈로그에서 직접 검색해 추가할 수 있어요.
            </p>
            <Button
              className="mt-2.5"
              fullWidth
              onClick={handleCatalogSearchOpen}
              size="md"
              startDecorator={<Search size={16} />}
              variant="primary-outlined"
            >
              전체 카탈로그 검색
            </Button>
          </div>
          <p className="px-2 pb-2 text-xs font-bold text-text-secondary">
            후보 목록
          </p>
          <div className="flex gap-2 overflow-x-auto pb-1 xl:flex-col xl:overflow-visible">
            {candidates.map((candidate, index) => {
              const isFocused = focusedCandidate.sku === candidate.sku;
              return (
                <button
                  aria-pressed={isFocused}
                  className={cn(
                    'min-w-[245px] rounded-xl border p-3 text-left transition-all xl:min-w-0',
                    isFocused
                      ? 'border-blue-600 bg-white shadow-[0_0_0_1px_#2563eb]'
                      : 'border-border bg-white hover:border-blue-300',
                  )}
                  key={candidate.sku}
                  onClick={() => handleCandidateFocus(candidate.sku)}
                  type="button"
                >
                  <div className="flex items-start gap-3">
                    <FurnitureArtwork
                      className="h-14 w-14 shrink-0"
                      imageUrl={candidate.imageUrl}
                      kind={candidate.kind}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="font-mono text-[10px] font-bold text-text-tertiary">
                          {candidate.sku}
                        </span>
                        <span className="text-[10px] font-bold text-text-quaternary">
                          {index + 1}위
                        </span>
                      </span>
                      <span className="mt-1 block truncate text-xs font-extrabold text-text-primary">
                        {candidate.name}
                      </span>
                      {/* 카탈로그 검색으로 추가한 SKU는 최상단 위치로 구분되므로
                          점수 막대 대신 브랜드·가격 등 참고 정보를 보여줍니다. */}
                      {candidate.score !== null ? (
                        <span className="mt-2 flex items-center gap-2">
                          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-neutral-100">
                            <span
                              className="block h-full rounded-full bg-emerald-600"
                              style={{ width: `${candidate.score}%` }}
                            />
                          </span>
                          <span className="text-[11px] font-extrabold text-emerald-700">
                            {candidate.score}%
                          </span>
                        </span>
                      ) : null}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        <article className="min-w-0 p-5 sm:p-6">
          <div className="flex flex-col gap-4 border-b border-neutral-100 pb-5 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <h2 className="text-lg font-extrabold text-text-primary">
                  {focusedCandidate.name}
                </h2>
                {focusedCandidate.score !== null && (
                  <span className="rounded-full bg-success-50 px-2 py-0.5 text-[11px] font-bold text-success-600">
                    추천
                  </span>
                )}
              </div>
              {/* 사이즈(attrs.size)는 카테고리에 따라 없을 수 있어, 값이 있을 때만 잇습니다. */}
              <p className="mt-1 font-mono text-xs text-text-tertiary">
                {focusedCandidate.size
                  ? `${focusedCandidate.sku} · ${focusedCandidate.size}`
                  : focusedCandidate.sku}
              </p>
            </div>
          </div>

          <div
            className={cn(
              'mt-5 grid gap-4',
              hasSimilarityResult &&
                'lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.92fr)]',
            )}
          >
            <div className="rounded-xl bg-bg-tertiary/75 p-5">
              <div className="flex min-h-44 items-center justify-center gap-3 sm:gap-6">
                <div className="w-28 text-center sm:w-36">
                  <ObjectCropPreview
                    image={uploadedImage}
                    object={selectedObject}
                  />
                  <p className="mt-2 text-[11px] font-semibold text-text-secondary">
                    탐지 객체 크롭
                  </p>
                </div>
                <ChevronRight
                  className="shrink-0 text-text-quaternary"
                  size={20}
                />
                <div className="w-28 text-center sm:w-36">
                  <FurnitureArtwork
                    imageUrl={focusedCandidate.imageUrl}
                    kind={focusedCandidate.kind}
                  />
                  <p className="mt-2 text-[11px] font-semibold text-text-secondary">
                    SKU 대표 이미지
                  </p>
                </div>
              </div>
            </div>
            {hasSimilarityResult && (
              <div className="rounded-xl border border-border p-4">
                <p className="text-xs font-bold text-text-secondary">
                  유사도
                </p>
                <div className="mt-3 flex items-end gap-2">
                  <span className="text-4xl font-extrabold tracking-[-0.05em] text-blue-700">
                    {similarity === null ? '—' : `${similarity}%`}
                  </span>
                  <span className="pb-1 text-xs font-semibold text-text-tertiary">
                    {comparisonCount}개 비교 중 {verdictCounts.MATCH}개 일치
                  </span>
                </div>
                {comparisonCount > 0 ? (
                  <>
                    <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-neutral-100">
                      <span
                        className="bg-emerald-600"
                        style={{ width: `${verdictPercentage('MATCH')}%` }}
                      />
                      <span
                        className="bg-rose-500"
                        style={{ width: `${verdictPercentage('MISMATCH')}%` }}
                      />
                      <span
                        className="bg-amber-500"
                        style={{ width: `${verdictPercentage('UNKNOWN')}%` }}
                      />
                    </div>
                    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] font-bold text-text-secondary">
                      {(Object.keys(VERDICT_LABELS) as Array<
                        keyof typeof VERDICT_LABELS
                      >).map((verdict) => (
                        <span className="flex items-center gap-1" key={verdict}>
                          <span
                            className={cn(
                              'h-2 w-2 rounded-full',
                              verdict === 'MATCH' && 'bg-emerald-600',
                              verdict === 'MISMATCH' && 'bg-rose-500',
                              verdict === 'UNKNOWN' && 'bg-amber-500',
                            )}
                          />
                          {VERDICT_LABELS[verdict]} {verdictCounts[verdict]}
                        </span>
                      ))}
                    </div>
                  </>
                ) : null}
              </div>
            )}
          </div>

          {metadataCriteria.length > 0 ? (
            <div className="mt-5">
              <p className="text-xs font-bold text-text-secondary">
                메타데이터 단위 검증
              </p>
              <div className="mt-2 overflow-x-auto rounded-xl border border-neutral-100">
                <table className="w-full min-w-[720px] text-left text-xs">
                  <thead className="bg-bg-tertiary text-text-tertiary">
                    <tr>
                      <th className="px-3 py-2 font-bold">메타데이터</th>
                      <th className="px-3 py-2 font-bold">Crop 이미지 판독</th>
                      <th className="px-3 py-2 font-bold">SKU 이미지 판독</th>
                      <th className="px-3 py-2 font-bold">판정</th>
                      <th className="px-3 py-2 font-bold">판단 근거</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-100">
                    {metadataCriteria.map((criterion) => {
                      const key = criterion.key as string;
                      const reading = cropReadings.get(key);
                      const verdict = criterion.verdict ?? 'UNKNOWN';
                      return (
                        <tr key={key}>
                          <td className="px-3 py-3 font-bold text-text-primary">
                            {ATTRIBUTE_LABELS[key] ?? key}
                          </td>
                          <td className="px-3 py-3 text-text-secondary">
                            {reading?.value
                              ? formatAttributeValue(reading.value)
                              : reading?.note || '판단 불가'}
                          </td>
                          <td className="px-3 py-3 text-text-secondary">
                            {criterion.value
                              ? formatAttributeValue(criterion.value)
                              : '판단 불가'}
                          </td>
                          <td className="px-3 py-3">
                            <span
                              className={cn(
                                'inline-flex whitespace-nowrap rounded-full px-2 py-1 text-[11px] font-bold',
                                VERDICT_STYLES[verdict],
                              )}
                            >
                              {VERDICT_LABELS[verdict]}
                            </span>
                          </td>
                          <td className="px-3 py-3 leading-5 text-text-secondary">
                            {criterion.comment || '판단 근거가 없습니다.'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3">
                  <p className="text-xs font-bold text-emerald-700">공통점</p>
                  <p className="mt-1 text-xs leading-5 text-emerald-900">
                    {focusedCandidate.xaiResult?.common || '확인된 공통점이 없습니다.'}
                  </p>
                </div>
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
                  <p className="text-xs font-bold text-amber-700">차이점 · 확인 필요</p>
                  <p className="mt-1 text-xs leading-5 text-amber-900">
                    {focusedCandidate.xaiResult?.difference || '확인된 차이점이 없습니다.'}
                  </p>
                </div>
              </div>
            </div>
          ) : null}

          {metadataCriteria.length === 0 ? (
            <div className="mt-5">
              <p className="text-xs font-bold text-text-secondary">
                SKU 카탈로그 속성
              </p>
              <dl className="mt-2 divide-y divide-neutral-100 border-y border-neutral-100">
                {attributeRows.map(([label, value]) => (
                  <div
                    className="grid grid-cols-[92px_minmax(0,1fr)] gap-3 px-2 py-3"
                    key={label}
                  >
                    <dt className="text-xs text-text-tertiary">{label}</dt>
                    <dd className="text-xs font-bold text-text-primary">
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : null}

          <div className="mt-6 flex flex-col-reverse gap-3 border-t border-neutral-100 pt-5 sm:flex-row sm:justify-between">
            <Button
              onClick={handlePreviousStage}
              startDecorator={<ChevronLeft size={16} />}
              variant="neutral-outlined"
            >
              {isFirstObject ? '탐지 단계로' : '이전 객체 처리'}
            </Button>
            <div className="grid gap-3 sm:flex">
              <Button
                onClick={handleSkuConfirmation}
                startDecorator={
                  isConfirmed ? <Check size={16} /> : <Sparkles size={16} />
                }
                variant={isConfirmed ? 'neutral-outlined' : 'primary-solid'}
              >
                {isConfirmed
                  ? '이 SKU로 확정됨'
                  : selectedSku
                    ? '이 SKU로 변경'
                    : '이 SKU 확정'}
              </Button>
              <Button
                disabled={!isConfirmed}
                endDecorator={<ArrowRight size={16} />}
                onClick={handleNextObject}
              >
                {isLastObject ? '전체 검수로 이동' : '다음 객체 처리'}
              </Button>
            </div>
          </div>
        </article>
      </div>
    </section>
  );
};
